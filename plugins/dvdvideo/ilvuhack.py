# Module:       ilvuhack.py
# Author:       Eric von Bayer
# Contact:      
# Date:         September 24, 2009
# Description:
#     Code for taking a sector block and figuring out what sectors actually
#     belong to the ILVU angle we start with for the cell.  
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
DEBUG = False

try:
    os.SEEK_SET
except AttributeError:
    os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)

def be_uint8( istr ):
    if len(istr) < 1:
        return 0
    else:
        return ord(istr[0])

def be_uint16( istr ):
    if len(istr) < 2:
        return 0
    else:
        return ( ord(istr[0]) << 8 ) + ord(istr[1])

def be_uint32( istr ):
    if len(istr) < 4:
        return 0
    else:
        return ( ord(istr[0]) << 24 ) + ( ord(istr[1]) << 16 ) + \
            ( ord(istr[2]) << 8 ) + ord(istr[3])

def GetNextDSIPacket( fh ):
    while 1:
        # Read the packet header
        packet_id = fh.read(3)
        
        if len(packet_id) == 0:
            return ( 0, "" )
        
        # Make sure we had a valid packet header
        if packet_id != '\000\000\001':
            raise "Packet Header ID (0x%06x) doesn't match 0x000001" % \
                ( ( ord(packet_id[0]) << 16 ) + ( ord(packet_id[1]) << 8 ) + \
                ord(packet_id[2]) )
        
        # Read in the stream ID
        stream_id = ord(fh.read(1))
        
        # Skip the specialty pack header packet that does not conform to the
        # usual standard
        if stream_id == 0xBA:
            packet_len = 10
            data = fh.read(packet_len)
            pad = ord(data[9]) & 0x7
            fh.read( pad )
            
        # Skip past all the normal packets till we find the DSI packet
        else:
            
            # Get the sector offset
            off = fh.tell() - 4
            
            # Read in the packet length
            packet_len = ( ord(fh.read(1)) << 8 ) + ord(fh.read(1))
            
            # If the stream is Private Stream 2 (0xBF) then check the substream
            if stream_id == 0xBF:
                
                # Get the sub stream id
                sub_stream_id = ord( fh.read(1) )
                
                # If we have the DSI packet, then return out
                if packet_len == 1018 and sub_stream_id == 1:
                    return ( off, fh.read(packet_len-1) )
                
                # Otherwise skip the rest    
                else:
                    fh.seek( packet_len-1, os.SEEK_CUR )
            
            # Seek past the packet
            else:
                fh.seek( packet_len, os.SEEK_CUR )

import sys
def cond( test, t, f ):
    if test:
        return t
    else:
        return f


# Walk the VOB encapsulated MPEG stream to determine which sectors are really
# part of our ILVU stream.
def ComputeRealSectors( start, end, *files ):

    if DEBUG:
        print "ComputeRealSectors(",start,",",end,"):"

    # Assemble a composite file
    cfile = CompositeFile( *files )
    
    # Set the current start to the real start
    cur_start = start
    
    # Real sector list
    rsl = list()
    first = True
    
    while cur_start >= start and cur_start <= end:
        
        # if the seek fails, we're done.
        try:
            # Seek to our starting sector
            cfile.seek( DVD_BLOCK_LEN * cur_start )
            
        except:
            break

        # Read in the next DSI packet
        off, dsi = GetNextDSIPacket( cfile )
        
        if DEBUG:
            print "[S%d/0x%08x+%04X]: [%c%c%c%c]" % (
                off/DVD_BLOCK_LEN, off/DVD_BLOCK_LEN, off%DVD_BLOCK_LEN,
                cond( be_uint8(dsi[32]) & 0x80, "P", "." ),
                cond( be_uint8(dsi[32]) & 0x40, "I", "." ),
                cond( be_uint8(dsi[32]) & 0x20, "S", "." ),
                cond( be_uint8(dsi[32]) & 0x10, "E", "." )
                )
            #for i in range(48):
            #    if i % 16 == 0:
            #        sys.stdout.write(  "+%03X: " % i )
            #    
            #    sys.stdout.write( "%02X " % ord(dsi[i]) )
            #    if i % 16 == 15 and i != 0:
            #        print ""
            
            print "Audio Packet Off:",list( be_uint16( dsi[apo:apo+2] ) for apo in range(402,418,2) )
            
            print "ILVU End:  %08x" % be_uint32( dsi[34:38] )
            print "ILVU Next: %08x" % be_uint32( dsi[38:42] )
            print "ILVU Size: %04x" % be_uint16( dsi[42:44] )
        
        # If we're not an ILVU, then return our original start,end
        if be_uint8(dsi[32]) & 0x40 == 0 and first == True:
            return [ [ start, end ] ]
        
        # Read in the information for the 
        end_ilvu_block = be_uint32( dsi[34:38] )
        next_ilvu_block = be_uint32( dsi[38:42] )
        
        if be_uint8(dsi[32]) & 0x60 != 0x60:
            #print "* Not a start, skipping this block. **********************************"
            cur_start += next_ilvu_block
            continue                
    
                
        # Add the block to the block list
        rsl.append( [ cur_start, cur_start + end_ilvu_block ] )
                
        # Advance the next cur start
        cur_start = cur_start + next_ilvu_block
        first = False
        
    return rsl