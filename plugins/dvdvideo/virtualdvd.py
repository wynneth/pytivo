# Module:       virtualdvd.py
# Author:       Eric von Bayer
# Updated By:   Luke Broadbent
# Contact:      
# Date:         June 25, 2011
# Description:
#     Model a DVD as a dynamic directory structure of mpegs.
#
# Copyright (c) 2009, Eric von Bayer
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * The names of the contributors may not be used to endorse or promote
#      products derived from this software without specific prior written
#      permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import re
import time
import dvdfolder

import metadata

# Use the LRU Cache if it is available
try:
    from lrucache import LRUCache
    VDVD_Cache = LRUCache(20)
except:
    VDVD_Cache = dict()

# Patterns to match against virtual files
PATTERN_VDVD_FILES = re.compile( "(?i)__T(-?[0-9]+).mpg" )
FORMAT_VDVD_FILES = "__T%02d.mpg"

################################# VirtualDVD ###################################

class VirtualDVD(object):
    class FileData(object):
        def __init__(self, vdvd, path, num, title ):
            self.name = os.path.join( path, FORMAT_VDVD_FILES % num ).encode('utf-8')
            self.isdir = False
            st = os.stat( path )
            #self.mdate = int(st.st_mtime)
            self.mdate = int(time.time())
            self.title = vdvd.TitleName(num)
            if( num >= 0 ):
                self.size = title.Size()
            else:
                self.size = 0

    def __init__( self, path, title_threshold = 0 ):
        
        self.valid = False
        self.TITLE_LENGTH_THRESHOLD = title_threshold
        self.dvd_folder = None
        path = unicode(path, 'utf-8')
        
        if os.path.isdir( path ):
            self.path = path
            self.file = ""
            self.file_id = -1
        else:
            self.path = os.path.dirname( path )
            self.file = os.path.basename( path )
            self.file_id = -1

        try:
            if self.path in VDVD_Cache:
                self.dvd_folder = VDVD_Cache[self.path]
                self.valid = self.dvd_folder.QuickValid()
            else:
                self.dvd_folder = dvdfolder.DVDFolder( self.path, defer=True )
                self.valid = self.dvd_folder.QuickValid()
                if self.valid:
                    VDVD_Cache[self.path] = self.dvd_folder

        except dvdfolder.DVDNotDVD:
            pass
        except dvdfolder.DVDFormatError, err:
            print "Warning while reading DVD %s: %s" % ( self.path, err )
            
        if not os.path.isdir( path ) and self.valid:
            m = PATTERN_VDVD_FILES.match(self.file)
            if m != None:
                self.file_id = int(m.group(1))

    def Path( self ):
        return self.path

    def HasErrors( self ):
        return self.dvd_folder and self.dvd_folder.HasErrors()

    def Valid( self ):
        try:
            if self.valid:
                return self.dvd_folder.Valid()
        except dvdfolder.DVDNotDVD:
            pass
        except dvdfolder.DVDFormatError, err:
            print "Warning while reading DVD %s: %s" % ( self.path, err )

        return False
        
    def QuickValid( self ):
        if self.valid:
            return self.dvd_folder.QuickValid()
        return False
        
    def TitleNumber( self ):
        return self.file_id
        
    def TitleName( self, num = -1 ):
        if num == -1:
            num = self.file_id
            
        if num == 0:
            return "Main Feature"
        elif num > 0:
            if num <= len(self.dvd_folder.TitleList()):
                return "Title " + str(num) + " (" + \
                    str(self.dvd_folder.TitleList()[num-1].Time()) + ")"
            return "<invalid title id "+str(num)+">"
        elif num == -99:
            return self.dvd_folder.Error()
        else:
            return "<negative title id "+str(num)+">"

    def IDToTitle( self, id ):
        if ( not self.Valid() ) or ( id < 0 ) or \
                ( id > len(self.dvd_folder.TitleList()) ):
            return DVDTitle()
        elif id == 0:
            return self.dvd_folder.MainTitle()
        else:
            return self.dvd_folder.TitleList()[id-1]

    def FileTitle( self, file = None ):
        if file == None:
            return self.IDToTitle( self.file_id )
        else:
            m = PATTERN_VDVD_FILES.match( file )
            if m != None:
                return self.IDToTitle( int(m.group(1)) )

        return self.IDToTitle( -1 )
        
    def DVDTitleName( self ):
        return os.path.basename( self.dvd_folder.Folder() )
    
    def NumFiles( self ):
        if self.Valid():
            return self.dvd_folder.NumUsefulTitles( self.TITLE_LENGTH_THRESHOLD )
        else:
            return 0        
    
    def GetFiles( self ):
        files = list()
        if self.Valid() and len( self.dvd_folder.TitleList() ) > 0:
           #if the title 0 has a name in the metadata files count it if it does not startwith ignore
            data = {}
            try:
                data.update( metadata.from_text( os.path.join( self.path, FORMAT_VDVD_FILES % 0 ).encode('utf-8') ) )
            except:
                pass

            if 'episodeTitle' in data:
                pass
            elif 'Title 0' in data:
                data['episodeTitle'] = data['Title 0']
            else:
                data['episodeTitle'] = ""

            if not data['episodeTitle'].lower().startswith('ignore'):
                files.append( self.FileData( self, self.path, 0, \
                    self.dvd_folder.MainTitle() ) )

            for title in self.dvd_folder.TitleList():
                if title.Time().Secs() > self.TITLE_LENGTH_THRESHOLD:
                    #if the title has a name in the metadata files count it if it does not startwith ignore
                    data = {}
                    try:
                        data.update( metadata.from_text( os.path.join( self.path, FORMAT_VDVD_FILES % title.TitleNumber() ).encode('utf-8') ) )
                    except:
                        pass

                    if 'episodeTitle' in data:
                        pass
                    elif 'Title '+ str(title.TitleNumber()) in data:
                        data['episodeTitle'] = data['Title ' + str(title.TitleNumber())]
                    else:
                        data['episodeTitle'] = ""

                    if not data['episodeTitle'].lower().startswith('ignore'):
                        files.append( self.FileData( self, self.path, \
                            title.TitleNumber(), title ) )
        elif self.dvd_folder.HasErrors() != None:
            files.append( self.FileData( self, self.path, -99, None ) )
        return files