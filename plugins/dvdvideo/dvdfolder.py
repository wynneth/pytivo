# Module:       dvdfolder.py
# Author:       Eric von Bayer
# Updated By:   Luke Broadbent
# Contact:      
# Date:         June 25, 2011
# Description:
#     Routines for reading data out of a DVD Folder.  This in no way is an
#     exhaustive implementation, but merely to give a good platform for
#     some automated DVD processing.
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
import ilvuhack
from dvdtitlestream import DVDTitleStream

import metadata

try:
    os.SEEK_SET
except AttributeError:
    os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)

# Constants for various parts of the structure
IFO_TYPE_VMG = 0
IFO_TYPE_VTS = 1
DVD_BLOCK_LEN = 2048

# Patterns to match against for the various parts of the DVD
PATTERN_VIDEO_TS =     re.compile( r"(?i)VIDEO_TS$" )
PATTERN_VIDEO_TS_IFO = re.compile( r"(?i)VIDEO_TS.IFO$" )
PATTERN_VIDEO_TS_VOB = re.compile( r"(?i)VIDEO_TS.VOB$" )
PATTERN_VTS_IFO =      re.compile( r"(?i)VTS_([0-9]{2})_0.IFO$" )
PATTERN_VTS_VOB =      re.compile( r"(?i)VTS_([0-9]{2})_([0-9]).VOB$" )
FORMAT_VDVD_FILES = "__T%02d.mpg"

def FindDOSFilename( path, dosname ):
    try:
        if os.path.isdir( path ):
            for f in os.listdir( path ):
                if f.upper() == dosname:
                    return os.path.join( path, f )
    except:
        return None

def MatchAudioAttr( audio_attr, lang, chan ):
    if lang != '*' and lang.lower() != audio_attr.LanguageCode().lower():
        #print "Failed based on language"
        return False
    elif chan != '*' and int( chan ) != audio_attr.Channels():
        #print "Failed based on channels"
        return False
    elif audio_attr.Coding() != "AC3":
        #print "Failed based on coding"
        return False
    elif audio_attr.CodeExtensionValue() > 1:
        #print "Failed based on extension", audio_attr.CodeExtensionValue()
        return False
    else:
        return True

def BCD2Dec( bcd ):
    return int( str( "%X" % bcd ) )
    
class DVDNotDVD(Exception):
    def __init__( self, txt ):
        self.__txt = txt
    
    def __str__( self ):
        return self.__txt

class DVDFormatError(Exception):
    def __init__( self, txt ):
        self.__txt = txt
    
    def __str__( self ):
        return self.__txt

########################## Misc Utility Functions ##############################

class DVDFileHandle(object):
    """Utility functions for reading DVD data structures"""
    DVD_BLOCK_LEN = 2048L
    __handle = None
    
    def __init__( self, handle, offset = -1 ):
        if not isinstance( handle, file ):
            raise "handle was not a file"

        self.__handle = handle
        self.__sector_offset = 0
        
        if self.IsOpen() and offset >= 0:
            self.Seek( offset )

    def IsOpen( self ):
        return not self.__handle.closed
        
    def Close( self ):
        if self.__handle != None and not self.__handle.closed:
            self.__handle.close()

    def Handle( self ):
        return self.__handle

    def SetSectorOffset( self, offset ):
        self.__sector_offset = offset
        
    def SectorOffset( self ):
        return self.__sector_offset
        
    def SectorSeek( self, sector, offset = None ):
        off = ( sector - self.__sector_offset ) * DVD_BLOCK_LEN
        if offset != None:
            off += offset
        self.Seek( off )
    
    def Seek( self, offset ):
        self.__handle.seek( offset )

    def Tell( self ):
        return self.__handle.tell()
        
    def SectorTell( self ):
        off = self.__handle.tell()
        sect = int( off / DVD_BLOCK_LEN )
        off = off % DVD_BLOCK_LEN
        return sect, off

    def Skip( self, bytes ):
        self.__handle.seek( bytes, 1 )

    def Read( self, bytes ):
        return self.__handle.read( bytes )

    def ReadU8( self ):
        return ord(self.__handle.read(1))

    def ReadU16( self ):
        return ( ord(self.__handle.read(1)) << 8 ) | \
            ord(self.__handle.read(1))
    
    def ReadU32( self ):
        return ( ord(self.__handle.read(1)) << 24 ) | \
            ( ord(self.__handle.read(1)) << 16 ) | \
            ( ord(self.__handle.read(1)) << 8 ) | \
            ord(self.__handle.read(1))

############################# IFOPlaybackTime ##################################

class IFOPlaybackTime(object):
    """Playback Time Data in an IFO file"""
    __sec = 0
    __frame_rate = 29.97
    
    def __init__( self, sec_handle = 0 ):
        if isinstance( sec_handle, file ):
            self.Read( sec_handle )
    
    def __iadd__( a, b ):
        a.__sec += b.__sec
        return a
        
    def __lt__( a, b ):
        return a.__sec < b.__sec

    def __ge__( a, b ):
        return a.__sec >= b.__sec or a == b
    
    def __le__( a, b ):
        return a.__sec <= b.__sec or a == b

    def __eq__( a, b ):
        return abs( a.__sec - b.__sec ) < 0.04

    def __ne__( a, b ):
        return not ( a == b )

    def __str__( self ):
        return "%d:%02d:%06.3f" % ( \
            int( self.__sec / 3600 ),
            int( ( self.__sec % 3600 ) / 60 ),
            self.__sec % 60 )
        
    def SetFrameRate( self, fr ):
        self.__frame_rate = fr
            
    def Read( self, handle ):
        try:
            hrs = BCD2Dec( ord(handle.read(1)) )
            mins = BCD2Dec( ord(handle.read(1)) )
            secs = BCD2Dec( ord(handle.read(1)) )
            fms = ord(handle.read(1))
            self.__frame_rate = [ 1000000, 25.0, 1000000, 29.97 ] \
                [ ( fms & 0xC0 ) >> 6 ]
            fms = BCD2Dec( fms  & 0x3F )
        except:
            self.__frame_rate = 29.97
            self.__sec = 0
            raise DVDFormatError( "Improper time format" )

        if self.__frame_rate == 1000000:
            print "Warning: Invalid Frame Rate flag, got " + \
                str( ( fms & 0xC0 ) >> 6 ) + " instead of 1 or 3."
        
        self.__sec = ( fms / self.__frame_rate ) + secs + (mins * 60) + (hrs * 3600)

    
    def FrameRate( self ):
        return self.__frame_rate
        
    def Secs( self ):
        return self.__sec

    def MSecs( self ):
        return int( self.__sec * 1000 )

############################## IFOVideoAttrs ###################################

class IFOVideoAttrs(DVDFileHandle):
    """Video Attributes in an IFO file"""
    def __init__( self, handle, offset ):
        DVDFileHandle.__init__( self, handle, offset )
        self.__data = self.ReadU16()
        self.__frame_rate = 29.97
        
    def backdoor_SetFrameRate( self, rate ):
        self.__frame_rate = rate
        
    def AspectRatio( self ):
        return [ "4:3", "16:9", "<unknown>", "16:9" ] \
            [ ( self.__data & 0x0C00 ) >> 10 ]

    def Resolution( self ):
        if ( self.__data & 0x3000 ) == 0:
            return [ "720x480", "704x480", "352x480", "352x240" ] \
                [ ( self.__data & 0x38 ) >> 3 ]
        else:
            return [ "720x576", "704x576", "352x576", "352x288" ] \
                [ ( self.__data & 0x38 ) >> 3 ]
    
    def Width( self ):
        return [ 720, 704, 352, 352 ] \
            [ ( self.__data & 0x38 ) >> 3 ]

    def Height( self ):
        if ( self.__data & 0x3000 ) == 0:
            return [ 480, 480, 480, 240 ] \
                [ ( self.__data & 0x38 ) >> 3 ]
        else:
            return [ 576, 576, 576, 288 ] \
                [ ( self.__data & 0x38 ) >> 3 ]
    
    def Standard( self ):
        return [ "NTSC", "PAL" ][ ( self.__data & 0x3000 ) >> 12 ]
    
    def Coding( self ):
        return [ "MPEG-1", "MPEG-2" ] [ ( self.__data & 0xC000 ) >> 14 ]
        
    def FrameRate( self ):
        return self.__frame_rate
        
############################## IFOAudioAttrs ###################################

class IFOAudioAttrs(DVDFileHandle):
    """Audio Attributes in an IFO file"""
    def __init__( self, handle, num, offset ):
        DVDFileHandle.__init__( self, handle, offset )
        self.__data = self.ReadU16()
        self.__lang = self.Read(2)
        self.__lang_ext = self.Read(1)
        self.__code_ext = self.ReadU8()
        self.__unk = self.Read(1)
        self.__mode = self.ReadU8()
        self.__stream_id = [ 0x80, 0, 0xC0, 0xC0, 0xA0, 0, 0x88, 0 ] \
            [ ( self.__data & 0xE000 ) >> 13 ] + num

    def Coding( self ):
        return [ "AC3", "<unknown>", "MPEG-1", "MPEG-2", "LPCM", "<unknown>", "DTS", "<unknown>" ] \
            [ ( self.__data & 0xE000 ) >> 13 ]
    
    def LanguageCode( self ):
        return self.__lang
    
    def CodeExtension( self ):
        return [ "Unspecified", "Normal", "For the Blind", "Director's Comments", \
            "Alternate Director's Comments" ] [ self.__code_ext ]

    def CodeExtensionValue( self ):
        return self.__code_ext
    
    def StreamID( self ):
        return self.__stream_id
        
    def Channels( self ):
        return ( self.__data & 0x7 ) + 1
        
    def DRC( self ):
        cmode = ( self.__data & 0xE000 ) >> 13
        return ( cmode == 2 or cmode == 3 ) and ( self.__data & 0xC0 ) == 0xC0 

    def Quantization( self ):
        if ( ( self.__data & 0xE000 ) >> 13 ) == 4:
            return [ 16, 20, 24, 0 ] [ ( self.__data & 0xC0 ) >> 6 ]
        else:
            return 16

################################ IFOAVAttrs ####################################

class IFOAVAttrs(DVDFileHandle):
    """Audio/Video Attributes in an IFO file"""
    def __init__( self, handle, offset ):
        DVDFileHandle.__init__( self, handle, offset )
        self.__video = IFOVideoAttrs( self.Handle(), offset )
        self.__audio_streams = self.ReadU16()
        self.__audio = list()
        for stm in range(self.__audio_streams):
            self.__audio.append( IFOAudioAttrs( self.Handle(), stm, offset + 4 + 8*stm ) )
            
    def Video( self ):
        return self.__video
        
    def AudioList( self ):
        return self.__audio
        
################################# IFOFile ######################################

class IFOVMGFile(DVDFileHandle):
    """IFO VMG File From a DVD"""
    def __init__( self, filename ):
        self.__filename = filename
        self.__time = IFOPlaybackTime()
        self.__frame_rate = 29.97
        try:
            # Open the file through our parent
            handle = open( filename, "rb" )
            DVDFileHandle.__init__( self, handle, 0x0 )
            if not self.IsOpen():
                raise DVDFormatError( "Couldn't open "+filename )
            
            # Make sure we're a VMG IFO file
            id = self.Read( 12 )
            if id != "DVDVIDEO-VMG":
                raise DVDFormatError( filename + "IFO file is not a VMG file" )

            # Get the VOB, IFO, and BUP sectors
            self.Seek( 0x0C )
            self.__last_sector_bup = self.ReadU32()
            self.Seek( 0x1C )
            self.__last_sector_ifo = self.ReadU32()
            self.Seek( 0xC0 )
            self.__first_sector_menu = self.ReadU32()            

            # Read in the version as big endian
            handle.seek( 0x20 )
            self.__version = self.ReadU32()
            
            # Get the A/V Attributes for the menu
            self.__menu = IFOAVAttrs( self.Handle(), 0x100 )

            # Read the simple header information
            self.Seek( 0x22 )
            self.__vmg_category = self.ReadU32()
            self.__num_vols = self.ReadU16()
            self.__vol_num = self.ReadU16()
            self.__side_id = self.ReadU8()
            self.Seek( 0x3E )
            self.__num_vts = self.ReadU16()
            self.__provider_id = self.Read(32)
            self.Seek( 0xC4 )
            self.__vmg_tt_srpt = self.ReadU32()
                        
            # Read the critical bits of the Table of Titles structure
            self.SectorSeek( self.__vmg_tt_srpt )
            tt_srpt_offset = self.Tell()
            self.__num_titles = self.ReadU16()
            self.Skip(6)
            self.__title_info = list()
            
            # Read in the title information             
            for tn in range(self.__num_titles):
                title = dict()
                title['number'] = tn+1
                title['type'] = self.ReadU8()
                title['angles'] = self.ReadU8()
                title['chapters'] = self.ReadU16()
                title['parental'] = self.ReadU16()
                title['vts_num'] = self.ReadU8()
                title['vts_pgc_num'] = self.ReadU8()
                title['vts_ifo_sector'] = self.ReadU32()
                
                # Make sure the information was "sane"
                assert title['vts_num'] <= 99, DVDFormatError( "Title "+str(tn)+" has a vts_num > 99" )
                assert title['vts_pgc_num'] <= 99, DVDFormatError( "Title "+str(tn)+" has a vts_pgc_num > 99" )
                
                # Add the title information
                self.__title_info.append( title )
                
            self.Close()
            self.__valid = True
        
        except:
            self.Close()
            self.__valid = False
            raise

    def Menu( self ):
        return self.__menu
    
    def Valid( self ):
        return self.__valid
    
    def NumVolumes( self ):
        return self.__num_vols
        
    def VolumeNum( self ):
        return self.__vol_num
        
    def SideID( self ):
        return self.__side_id
            
    def NumVTSes( self ):
        return self.__num_vts
        
    def NumTitles( self ):
        return self.__num_titles
        
    def TitleInfo( self, tnum ):
        return self.__title_info[tnum-1]            

class IFOVTSFile(DVDFileHandle):
    """IFO VTS File From a DVD"""
    def __init__( self, filename ):
        self.__filename = filename
        self.__time = IFOPlaybackTime()
        self.__frame_rate = 29.97
        try:
            # Get our VTS number
            match = PATTERN_VTS_IFO.match( os.path.basename( filename ) )
            if match == None:
                raise DVDFormatError( "Not a valid VTS file" )
            self.__num = int( match.group(1) )

            # Read in a list of all the VTS VOB files        
            self.__vob_files = list()
            path = os.path.dirname( self.__filename )
            for fn in os.listdir( path ):
                match = PATTERN_VTS_VOB.match( fn )
                if match != None and int(match.group(1)) == self.__num and int(match.group(2)) > 0:
                    self.__vob_files.append( os.path.join( path, fn ) )
            self.__vob_files.sort()
            
            # Open the file through our parent
            handle = open( filename, "rb" )
            DVDFileHandle.__init__( self, handle, 0x0 )
            if not self.IsOpen():
                raise DVDFormatError( "Can't open VTS info file" )
            
            # Make sure we're a VMG IFO file
            id = self.Read( 12 )
            if id != "DVDVIDEO-VTS":
                raise DVDFormatError( "Expected a VTS info file" )

            # Get the VOB, IFO, and BUP sectors
            self.Seek( 0x0C )
            self.__last_sector_bup = self.ReadU32()
            self.Seek( 0x1C )
            self.__last_sector_ifo = self.ReadU32()
            self.Seek( 0xC0 )
            self.__first_sector_menu = self.ReadU32()            
            self.__first_sector_title = self.ReadU32()            

            # Read in the version as big endian
            handle.seek( 0x20 )
            self.__version = self.ReadU32()
            
            # Get the A/V Attributes for the menu
            self.__menu = IFOAVAttrs( self.Handle(), 0x100 )
            
            # Get the A/V Attributes for the title (if present)
            self.__title = IFOAVAttrs( self.Handle(), 0x200 )

            # Read the program chain structure for playtimes and stream ids
            handle.seek( 0xCC )
            self.__vts_pgci_sector = self.ReadU32()
            
            # Read the critical bits of the Program Chain structure
            self.SectorSeek( self.__vts_pgci_sector )
            pgci_offset = self.Tell()
            
            # Get the Program chain information
            self.__pgc_info = list()
            self.__num_pgc = self.ReadU16()
            self.Skip(2)
            self.__pgc_end_off = self.ReadU32()
            for pgc in range(self.__num_pgc):
                
                # Read in the information in the program chain index
                info = dict()
                info['vts_number'] = self.__num
                info['number'] = pgc+1
                t1 = self.ReadU8()
                info['title_number'] = t1 & 0x3F
                info['entry'] = ( (t1 & 0x80) == 0x80 )
                self.Skip(1)
                info['parental_ctl_mask'] = self.ReadU16()

                # Find the offset of the program chain
                pgc_off = self.ReadU32()

                # Ignore non entry program chains as they will be picked
                # up in other ways.
                if info['entry'] == False:
                    continue

                # Save the current location and seek to the Program Chain
                cur_off = self.Tell()                
                self.Seek( pgci_offset + pgc_off + 2 )
                
                # Read in the number of programs/chapters and cells
                info['programs'] = self.ReadU8()
                info['cells'] = self.ReadU8()
                
                # Read in the playback time
                info['playtime'] = IFOPlaybackTime( handle )
                
                # Skip the prohibited ops
                self.Skip(4)
                
                # Read the list of valid audio streams
                astrs = list()
                for num in range(8):
                    strnum = self.ReadU8()
                    self.Skip(1)
                    if strnum & 0x80:
                        astrs.append( strnum & 0x7 )
                info[ 'audio_stream_nums' ] = astrs
                
                # Default these to False and mark true if we find a cell
                # that matches.
                info['ilvu'] = False
                info['angles'] = False
                    
                # Get the playback information table and seek to there
                self.Seek( pgci_offset + pgc_off + 0xE8 )
                pgc_playback_off = self.ReadU16()
                self.Seek( pgci_offset + pgc_off + pgc_playback_off )
                
                # Walk the cells showing the info
                ts = DVDTitleStream( *self.__vob_files )
                for cn in range( info['cells'] ):
                    t1 = self.ReadU8()
                    t2 = self.ReadU8()
                    if ( t1 & 0xF0 ) != 0x00:
                        info['angles'] = True

                    self.Skip(6)
                    s = self.ReadU32()
                    i = self.ReadU32()
                    self.Skip(4)
                    e = self.ReadU32()
                    if i != 0:
                        info['ilvu'] = True

                    # If there are no ILVUs then just add the block                    
                    if i == 0:
                        ts.AddSectors( s, e )
                        
                    # Otherwise, we need to let the ILVU hack compute the real
                    # sectors by partially decoding the VOB.
                    else:
                        try:
                            for [sr,er] in ilvuhack.ComputeRealSectors( s, e, \
                                    *ts.files() ):
                                ts.AddSectors( sr, er )
                        except AssertionError, err:
                            raise DVDFormatError( \
                                "Error processing ILVU block within title set "+\
                                str(self.__num)+", program chain "+\
                                str(info["number"])+": "+str(err) )
                        except:
                            raise DVDFormatError( \
                                "Error processing ILVU block within title set "+\
                                str(self.__num)+", program chain "+\
                                str(info["number"]) )
                            
                info['stream'] = ts
                
                # Add all the information to the PGC list                    
                self.__pgc_info.append( info )
                
                # Return to the PGC table
                self.Seek( cur_off )

            self.__title.Video().backdoor_SetFrameRate( \
                self.__pgc_info[0]['playtime'].FrameRate() )
            
            self.Close()
            self.__valid = True
            
        except:
            self.Close()
            self.__valid = False
            raise
    
    def Name( self ):
        return self.__filename
    
    def Size( self ):
        return os.path.getsize( self.__filename )
        
    def Sectors( self ):
        return self.__last_sector_ifo
        
    def VOBSectors( self ):
        return self.__last_sector_bup - ( self.__last_sector_ifo * 2 )
        
    def VOBFiles( self ):
        return self.__vob_files
        
    def BUPSectorOffset( self ):
        return self.__last_sector_bup - self.__last_sector_ifo
        
    def VOBSize( self ):
        return self.VOBSectors() * self.DVD_BLOCK_LEN
        
    def NumPGCs( self ):
        return self.__num_pgc
        
    def PGCInfo( self, num ):
        if num < 1 or num > len(self.__pgc_info):
            return None
        return self.__pgc_info[ num-1 ]

    def Version( self ):
        return self.__version
    
    def Menu( self ):
        return self.__menu
        
    def Title( self ):
        return self.__title
    
    def Valid( self ):
        return self.__valid

################################# DVDTitle #####################################

class DVDTitle(object):
    """Information about a set of VOBs based on VMG/VTS info"""
    def __init__( self, tnum, vmg_ifo, vts_list ):
        self.__valid = False
        try:
            self.__tinfo = vmg_ifo.TitleInfo( tnum )
            self.__vts = vts_list[ self.__tinfo['vts_num']-1 ]        
            self.__pgcinfo = self.__vts.PGCInfo( self.__tinfo['vts_pgc_num'] )
            
            if self.__pgcinfo == None:
                raise DVDFormatError( "Title number: %d - PGC number %d in VTS %d is out of range (%d)" %
                    ( tnum, self.__tinfo['vts_pgc_num'], self.__tinfo['vts_num'], self.__vts.NumPGCs() ) )
            self.__valid = True
            
            self.__audio_streams = list()
            vts_audio_streams = self.__vts.Title().AudioList()
            for asnum in self.__pgcinfo['audio_stream_nums']:
                self.__audio_streams.append( vts_audio_streams[asnum] )
                
        except:
            raise
        
    def Valid( self ):
        return self.__valid
        
    def TitleNumber( self ):
        return self.__tinfo['number']
        
    def VTS( self ):
        return self.__vts
        
    def VTSNumber( self ):
        return self.__tinfo['vts_num']
        
    def PGCNumber( self ):
        return self.__tinfo['vts_pgc_num']
        
    def HasAngles( self ):
        return self.__pgcinfo['angles']

    def HasInterleaved( self ):
        return self.__pgcinfo['ilvu']

    def AudioStreams( self ):
        return self.__audio_streams
    
    def FindBestAudioStreamID( self, spec ):
        #print "FindBestAudioStreamID( "+spec+" )"
        parts = spec.split( ',' )
        for part in parts:
            #print "Part:", part
            elems = part.split( ':', 1 )
            
            if len(elems) >= 2:
                for stream in self.__audio_streams:
                    #print elems[0], elems[1], "==?", stream.LanguageCode(),stream.Channels(), "(0x%02x)" % stream.StreamID()
                    if MatchAudioAttr( stream, elems[0], elems[1] ):
                        return stream.StreamID()
            
        #print "Defaulted to", self.__audio_streams[0].LanguageCode(),self.__audio_streams[0].Channels(), "(0x%02x)" % self.__audio_streams[0].StreamID()
        return self.__audio_streams[0].StreamID()

    def Stream( self ):
        return self.__pgcinfo['stream']
        
    def Size( self ):
        return self.__pgcinfo['stream'].size()

    def Time( self ):
        return self.__pgcinfo['playtime']
        

###########################s###### DVDFolder ####################################
    
class DVDFolder(object):
    """DVD Folder along with routines to read contents"""
    def __init__( self, path, defer = False ):
        self.__valid = False
        self.__disc_ifo = None
        self.__disc_vob = None
        self.__titles = list()
        self.__main_title = None
        self.__deferred = False
        self.__error = None
        
        try:
            # Make sure we have a directory
            if not os.path.isdir( path ):
                raise DVDNotDVD( "VIDEO_TS not located in "+path )
            self.__path = path
            
            # Find the sub VIDEO_TS folder
            self.__videots_path = FindDOSFilename( path, "VIDEO_TS" )
            if self.__videots_path == None:
                raise DVDNotDVD( "VIDEO_TS not located in "+path )
        
            # Find the top level IFO file
            self.__vmg_ifo_fn = FindDOSFilename( self.__videots_path, "VIDEO_TS.IFO" )
            if self.__vmg_ifo_fn == None:
                raise DVDFormatError( "Couldn't locate VIDEO_TS.IFO in "+self.__videots_path )
                        
            # Defer most of the load if asked to, this lets the pages load faster,
            # otherwise load it immediately
            self.__deferred = True
            if not defer:
                self.__load_full()
            
            # We're valid, mark ourself as such
            self.__valid = True

        except DVDFormatError, err:
            self.__error = str(err)
            self.__valid = False
            raise
                      
        except DVDNotDVD:
            self.__valid = False
            raise
            
        except:
            self.__error = "Unknown internal error."
            self.__valid = False
            raise
    
    def __load_full( self ):
        if self.__valid == False or self.__deferred == False:
            return

        self.__deferred = False
                    
        try:
            # Read in the top level IFO
            self.__vmg_ifo = IFOVMGFile( self.__vmg_ifo_fn )

            # Read in the list of VTS IFOs
            self.__vts_list = list()
            for vts in range( 1, self.__vmg_ifo.NumVTSes()+1 ):
                
                # Figure out the file name we're after
                ufile = "VTS_%02d_0.IFO" % vts
                dfile = FindDOSFilename( self.__videots_path, ufile )
                
                # Make sure we got a file
                if dfile == None:
                    raise DVDFormatError( "Couldn't find file "+ufile+"  in "+self.__videots_path )
                
                # Get the file and if it was valid, add it to our list
                vts_ifo = IFOVTSFile( dfile )
                if vts_ifo.Valid() == False:
                    raise DVDFormatError( dfile+" contained invalid format" )
                self.__vts_list.append( vts_ifo )
            
            # Walk all the titles assembling the data
            self.__titles = list()
            lt_time = IFOPlaybackTime(0)
            self.__main_title = None
            for tn in range( 1, self.__vmg_ifo.NumTitles()+1 ):
                try:
                    title = DVDTitle( tn, self.__vmg_ifo, self.__vts_list )

                    if title.Time() > lt_time:
                        lt_time = title.Time()
                        self.__main_title = title
                    
                    self.__titles.append( title )
                
                except DVDFormatError:
                    pass
            
            if len(self.__titles) < 1:
                raise DVDFormatError( "No valid titles present" )

        except DVDFormatError, err:
            self.__error = str(err)
            self.__valid = False
            raise
                      
        except DVDNotDVD:
            self.__valid = False
            raise
            
        except:
            self.__error = "Unknown internal error."
            self.__valid = False
            raise
    
    def Defered( self ):
        return self.__deferred
    
    def Folder( self ):
        return self.__path
    
    def MenuIFO( self ):
        self.__load_full()
        return self.__vmg_ifo
    
    # Count up the usable titles
    def NumUsefulTitles( self, title_threshold = 30.0 ):
        self.__load_full()
        if self.__valid:
            utitles = 0
            for title in self.TitleList():
                if title.Time() > title_threshold:
                    #if the title has a name in the metadata files count it if it does not startwith ignore
                    data = {}
                    try:
                        data.update( metadata.from_text( os.path.join( self.__path, FORMAT_VDVD_FILES % title.TitleNumber() ).encode('utf-8') ) )
                    except:
                        pass

                    if 'episodeTitle' in data:
                        pass
                    elif 'Title '+ str(title.TitleNumber()) in data:
                        data['episodeTitle'] = data['Title ' + str(title.TitleNumber())]
                    else:
                        data['episodeTitle'] = ""

                    if not data['episodeTitle'].lower().startswith('ignore'):
                        utitles += 1
    
            return utitles
        return 0
    
    def TitleList( self ):
        self.__load_full()
        return self.__titles
        
    def MainTitle( self ):
        self.__load_full()
        return self.__main_title
    
    def Valid( self ):
        self.__load_full()
        return self.__valid

    def QuickValid( self ):
        return self.__valid
        
    def HasErrors( self ):
        return self.__error != None
        
    def Error( self ):
        return self.__error
      