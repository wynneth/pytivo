# Module:       compositefile.py
# Author:       Eric von Bayer
# Contact:      
# Date:         August 18, 2009
# Description:
#     Class that works like a file but is in reality a series of file system
#     files.  Intentionally is a similar API to the file object.  
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
import copy

try:
    os.SEEK_SET
except AttributeError:
    os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)

# Handle a series of files as if it's one file
class CompositeFile(object):
    """Virtual file that is a composite of other files"""
    def __init__( self, *files ):
        self.__file_map = list()
        self.closed = True

        # If we are given a composite file, copy the file map
        if len(files) == 1 and isinstance( files[0], CompositeFile ):
            self.__file_map = copy.deepcopy( files[0].__file_map )

        # Build a file offset map
        else:
            off = 0L
            for cfile in files:
                size = os.path.getsize( cfile )
                if size > 0 and os.path.isfile( cfile ):
                    off += size
                    self.__file_map.append( ( off, cfile ) )
        
        # Open the first file
        self.open()
        
    def __str__( self ):
        return ",".join( fm[1] for fm in self.__file_map )
    
    # Advance to the next file    
    def __next_file( self ):
        # If we have an open handle, close it in preparation for the next one
        if self.__handle != None and not self.__handle.closed:
            self.__handle.close()
            
        # Bump the file number that we're on
        self.__fileno += 1
        
        # If there's another file, open it and get the next offset
        if self.__fileno < len( self.__file_map ):
            self.__handle = open( self.__file_map[ self.__fileno ][1], "rb" )
            self.__next_file_off = self.__file_map[ self.__fileno ][0]
        
        # We're done, null the handle and mark as closed
        else:
            self.close()

    # Read a slice, return the data and how many bytes remain to be read
    def __read_slice( self, bytes ):
        rem = self.__off + bytes - self.__next_file_off
        
        # If the remaining bytes aren't negative, then read a slice and advance
        # to the next file.
        if rem >= 0L:
            bytes = bytes - rem
            #print "Read %d[%d]: %d: %s+%d" % ( bytes, rem, self.__off, os.path.basename(self.__handle.name), self.__handle.tell() )
            data = self.__handle.read( bytes )
            self.__off += len(data)
            assert bytes == len(data), "Failed to read the requested number of bytes"
            self.__next_file()
            return data, rem
            
        # Read the bytes all from this file
        else:
            #print "Read %d: %d: %s+%d" % ( bytes, self.__off, os.path.basename(self.__handle.name), self.__handle.tell() )
            data = self.__handle.read( bytes )
            self.__off += len(data)
            assert bytes == len(data), "Failed to read the requested number of bytes"
            return data, 0
    
    # Get a list of files
    def files( self ):
        return [ fm[1] for fm in self.__file_map ]
            
    # Return the linear offset
    def tell( self ):
        return self.__off
        
    # Seek into the composite file
    def seek( self, off, whence = os.SEEK_SET ):
        
        # Calculate the new seek offset
        if whence == os.SEEK_SET:
            new_off = off
        elif whence == os.SEEK_CUR:
            new_off = self.__off + off
        elif whence == os.SEEK_END:
            new_off = self.__file_map[-1][0] + off
        else:
            raise "seek called with an invalid offset type"
        
        # Determine which file this seek offset is part of
        soff = 0
        fileno = 0
        eoff = 0
        for ( eoff, mfile ) in self.__file_map:
            if eoff > new_off:
                break
            fileno += 1
            soff = eoff
        
        # Make sure this was a valid seek point
        if eoff <= new_off:
            raise "seek beyond the bounds of the composite file"
        
        # Make sure the correct file is open    
        if fileno != self.__fileno:
            if not self.__handle.closed:
                self.__handle.close()
            self.__handle = open( self.__file_map[fileno][1], "rb" )
            self.__next_file_off = eoff
            self.__fileno = fileno
            
        # Seek the file handle
        self.__handle.seek( new_off - soff )
        self.__off = new_off

    # Read from the file
    def read( self, bytes ):
        if self.__handle.closed == False:
            data = ""
            while bytes > 0 and self.closed == False:
                slice_data, bytes = self.__read_slice( bytes )
                data += slice_data
            return data
        else:
            return ""

    def open(self):
        if self.closed:
            self.__fileno = -1
            self.__off = 0L
            self.__next_file_off = 0L
            self.__handle = None
            self.closed = False
            
            # Open the first file
            self.__next_file()


    def close( self ):
        if self.__handle != None and self.__handle.closed == False:
            self.__handle.close()
            self.__handle = None
        self.closed = True
        
    def size( self ):
        return self.__file_map[-1][0]
