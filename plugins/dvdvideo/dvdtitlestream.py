# Module:       dvdtitlestream.py
# Author:       Eric von Bayer
# Contact:      
# Date:         August 18, 2009
# Description:
#     Class that works like a file but is in reality a series of file system
#     files along with a sector map.  This in conjunction with the underlying
#     composite file will allow linear file access to the convoluted underlying
#     video stream.  Intentionally is a similar API to the file object.  
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
from compositefile import CompositeFile

DVD_BLOCK_LEN = 2048L

try:
    os.SEEK_SET
except AttributeError:
    os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)

class DVDTitleStream(object):
    """Virtual file that is a composite of vob files mapped through a sector list"""
    def __init__( self, *files ):
        if len(files) == 1 and isinstance( files[0], DVDTitleStream ):
            self.__cfile = CompositeFile( files[0].__cfile )
            self.__slist = files[0].__slist
        else:
            self.__cfile = CompositeFile( *files )
            self.__slist = list()

        self.__cfile.close()
        self.__sector_map = None
        self.__srange = -1
        self.__sects = 0L
        self.__off = 0L
        self.__next_sec_off = 0L
        self.closed = False

    def __str__( self ):
        ser = list()
        for [s,e] in self.__slist:
            ser.append( "[%d-%d]" % (s,e) )
        return "[" + str( self.__cfile ) + "] % " + ",".join( ser )
    
    # Build a map of ( virtual offset, real offset )    
    def __map_sectors( self ):
        if self.__sector_map == None:
            self.__cfile.open()
            self.__sector_map = list()
            off = 0L
            for (s,e) in self.__slist:
                off += ( e - s + 1 ) * DVD_BLOCK_LEN
                self.__sector_map.append( ( off, s * DVD_BLOCK_LEN ) )
            self.__srange = -1
            self.__offset = 0L
            self.__next_sec_off = self.__sector_map[0][0]
            self.__next_range()

    # Advance to the next file
    def __next_range( self ):

        if not self.closed:
            # Bump the file number that we're on
            self.__srange += 1
            
            # If there's another sector range, seek to it and get the next offset
            if self.__srange < len( self.__sector_map ):
                self.__cfile.seek( self.__sector_map[self.__srange][1] )
                self.__next_sec_off = self.__sector_map[self.__srange][0]
            
            # We're done, close the file
            else:
                self.__cfile.close()
                self.closed = True

    # Read a slice, return the data and how many bytes remain to be read
    def __read_slice( self, bytes ):
        
        if not self.closed:
            rem = self.__off + bytes - self.__next_sec_off
            
            # If the remaining bytes aren't negative, then read a slice and advance
            # to the next file.
            if rem >= 0L:
                bytes = bytes - rem
                data = self.__cfile.read( bytes )
                self.__off += len(data)
                self.__next_range()
                return data, rem
                
            # Read the bytes all from this file
            else:
                data = self.__cfile.read( bytes )
                self.__off += len(data)
                return data, 0
        else:
            return "", bytes
        
    def AddSectors( self, start, end ):
        self.__sects += (end - start) + 1
        if len(self.__slist) > 0:
            if self.__slist[-1][1]+1 == start:
                self.__slist[-1][1] = end
                return
        self.__slist.append( [ start, end ] )
        self.__sector_map = None
    
    def SectorList( self ):
        return self.__slist

    def files( self ):
        return self.__cfile.files()
        
    def tell_real( self ):
        return self.__cfile.tell()

    def tell( self ):
        return self.__off
        
    # Seek into the composite file
    def seek( self, off, whence = os.SEEK_SET ):
        self.__map_sectors()
        
        # Calculate the new seek offset
        if whence == os.SEEK_SET:
            new_off = off
        elif whence == os.SEEK_CUR:
            new_off = self.__off + off
        elif whence == os.SEEK_END:
            new_off = self.__sector_map[-1][0] + off
        else:
            raise "seek called with an invalid offset type"
        
        # Determine which file this seek offset is part of
        soff = 0
        srange = 0
        for ( eoff, roff ) in self.__sector_map:
            if eoff > new_off:
                break
            srange += 1
            soff = eoff
        
        # Make sure this was a valid seek point
        if eoff <= new_off:
            raise "seek beyond the bounds of the composite file"
        
        # Make sure the correct file is open    
        if srange != self.__srange:
            self.__next_sec_off = eoff
            self.__srange = srange
            
        # Seek the file handle
        self.__cfile.seek( roff + new_off - soff )
        self.__off = new_off

    # Read from the file
    def read( self, bytes ):
        self.__map_sectors()
        if self.closed == False:
            data = ""
            while bytes > 0 and self.closed == False:
                slice_data, bytes = self.__read_slice( bytes )
                data += slice_data
            return data
        else:
            return ""
            
    def close( self ):
        if self.__cfile.closed == False:
            self.__cfile.close()
        self.closed = True
        
    def size( self ):
        return self.__sects * DVD_BLOCK_LEN
