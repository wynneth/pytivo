# Module:       dvdfolder.py
# Author:       Eric von Bayer
# Updated By:   Luke Broadbent
# Contact:      
# Date:         June 15, 2011
# Description:
#     Routines for reading DVD vob files and streaming them to the TiVo.
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

from threading import Thread
from dvdtitlestream import DVDTitleStream

import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import lrucache

import config
import metadata
import virtualdvd

def WriteStreamToSubprocess( fhin, sub, event, blocksize ):
    if event == None:
        event = 1
    # Write all the data till either end is closed or done
    while not event.isSet():
        
        # Read in the block and escape if we got nothing
        data = fhin.read( blocksize )
        if len(data) == 0:
            break
        
        if sub.poll() != None and sub.stdin != None:
            break

        # Write the data and flush it
        try:
            sub.stdin.write( data )
            sub.stdin.flush()
        except IOError:
            break
        
        # We got less data so we must be at the end
        if len(data) < blocksize:
            break
    
    # Close the input if it's not already closed
    if not fhin.closed:
        fhin.close()
    
    # Close the output if it's not already closed
    if sub.stdin != None and not sub.stdin.closed:
        sub.stdin.close()

def vobstream(isQuery, inFile, ffmpeg, blocksize):
    dvd = virtualdvd.VirtualDVD( inFile )
    if not dvd.Valid() or dvd.file_id == -1:
        debug('Not a valid dvd file')
        return 0

    title = dvd.FileTitle()
    ts = DVDTitleStream( title.Stream() )
                                  
    # Make an event to shutdown the thread
    sde = threading.Event()
    sde.clear()

    # Stream data to the subprocess
    t = Thread( target=WriteStreamToSubprocess, args=(ts, ffmpeg, sde, blocksize) )
    t.start()

    if isQuery:
        # Shutdown the helper threads/processes    
        ffmpeg.wait()
        sde.set()
        t.join()
            
        # Close the title stream
        ts.close()    
    else:
        proc = {'stream': ts, 'thread': t, 'event':sde}
        return proc
    
def is_dvd(inFile):
    dvd = virtualdvd.VirtualDVD( inFile )
    return dvd.Valid() or dvd.file_id != -1

def size(inFile):
    try:
        dvd = virtualdvd.VirtualDVD( inFile )
        return dvd.FileTitle().Size()
    except:
        return 0

def duration(inFile):
    dvd = virtualdvd.VirtualDVD( inFile )
    title = dvd.FileTitle()
    return title.Time().MSecs()

def tivo_compatible(inFile, tsn='', mime=''):
    message = (False, 'All DVD Video must be re-encapsulated')
    debug('TRANSCODE=%s, %s, %s' % (['YES', 'NO'][message[0]],
                                           message[1], inFile))
    return message

def video_info(inFile, audio_spec = "", cache=True):
    vInfo = dict()
    fname = unicode(os.path.dirname(inFile), 'utf-8')
    mtime = os.stat(fname).st_mtime
    if cache:
        if inFile in info_cache and info_cache[inFile][0] == mtime:
            debug('CACHE HIT! %s' % inFile)
            return info_cache[inFile][1]

    dvd = virtualdvd.VirtualDVD( inFile )
    if not dvd.Valid() or dvd.file_id == -1:
        debug('Not a valid dvd file')
        return dict()
    
    ffmpeg_path = config.get_bin('ffmpeg')
    
    title = dvd.FileTitle()
    sid = title.FindBestAudioStreamID( audio_spec )
    ts = DVDTitleStream( title.Stream() )
    ts.seek(0)

    cmd = [ffmpeg_path, '-i', '-']
    # Windows and other OS buffer 4096 and ffmpeg can output more than that.
    err_tmp = tempfile.TemporaryFile()
    ffmpeg = subprocess.Popen(cmd, stderr=err_tmp, stdout=subprocess.PIPE,
                              stdin=subprocess.PIPE)

    # Write all the data till either end is closed or done
    while 1:
        # Read in the block and escape if we got nothing
        data = ts.read(BLOCKSIZE)
        if len(data) == 0:
            break

        if ffmpeg.poll() != None and sub.stdin != None:
            break
            
        try:
            ffmpeg.stdin.write(data)
            ffmpeg.stdin.flush()
        except IOError:
            break
            
        # We got less data so we must be at the end
        if len(data) < BLOCKSIZE:
            break

    # wait configured # of seconds: if ffmpeg is not back give up
    wait = config.getFFmpegWait()
    debug('starting ffmpeg, will wait %s seconds for it to complete' % wait)
    for i in xrange(wait * 20):
        time.sleep(.05)
        if not ffmpeg.poll() == None:
            break

    if ffmpeg.poll() == None:
        kill(ffmpeg)
        vInfo['Supported'] = False
        if cache:
            info_cache[inFile] = (mtime, vInfo)
        return vInfo

    err_tmp.seek(0)
    output = err_tmp.read()
    err_tmp.close()
    debug('ffmpeg output=%s' % output)

    # Close the input if it's not already closed
    if not ts.closed:
        ts.close()
    
    #print "VOB Info:", output
    vInfo['mapAudio'] = ''

    attrs = {'container': r'Input #0, ([^,]+),',
             'vCodec': r'Video: ([^, ]+)',             # video codec
             'aKbps': r'.*Audio: .+, (.+) (?:kb/s).*',     # audio bitrate
             'aCodec': r'.*Audio: ([^,]+),.*',             # audio codec
             'aFreq': r'.*Audio: .+, (.+) (?:Hz).*',       # audio frequency
             'mapVideo': r'([0-9]+\.[0-9]+).*: Video:.*',  # video mapping
             'mapAudio': r'([0-9]+\.[0-9]+)\[0x%02x\]: Audio:.*' % sid } # Audio mapping

    for attr in attrs:
        rezre = re.compile(attrs[attr])
        x = rezre.search(output)
        if x:
            vInfo[attr] = x.group(1)
        else:
            if attr in ['container', 'vCodec']:
                vInfo[attr] = ''
                vInfo['Supported'] = False
            else:
                vInfo[attr] = None
            debug('failed at ' + attr)
            
    # Get the Pixel Aspect Ratio
    rezre = re.compile(r'.*Video: .+PAR ([0-9]+):([0-9]+) DAR [0-9:]+.*')
    x = rezre.search(output)
    if x and x.group(1) != "0" and x.group(2) != "0":
        vInfo['par1'] = x.group(1) + ':' + x.group(2)
        vInfo['par2'] = float(x.group(1)) / float(x.group(2))
    else:
        vInfo['par1'], vInfo['par2'] = None, None
 
    # Get the Display Aspect Ratio
    rezre = re.compile(r'.*Video: .+DAR ([0-9]+):([0-9]+).*')
    x = rezre.search(output)
    if x and x.group(1) != "0" and x.group(2) != "0":
        vInfo['dar1'] = x.group(1) + ':' + x.group(2)
    else:
        vInfo['dar1'] = None

    # Get the video dimensions
    rezre = re.compile(r'.*Video: .+, (\d+)x(\d+)[, ].*')
    x = rezre.search(output)
    if x:
        vInfo['vWidth'] = int(x.group(1))
        vInfo['vHeight'] = int(x.group(2))
    else:
        vInfo['vWidth'] = ''
        vInfo['vHeight'] = ''
        vInfo['Supported'] = False
        debug('failed at vWidth/vHeight')
    
    vInfo['millisecs'] = title.Time().MSecs()
    vInfo['Supported'] = True

    if cache:
        info_cache[inFile] = (mtime, vInfo)
    debug("; ".join(["%s=%s" % (k, v) for k, v in vInfo.items()]))
    return vInfo

def supported_format(inFile):
    dvd = virtualdvd.VirtualDVD( inFile )
    return dvd.Valid() and dvd.file_id != -1
    if video_info(inFile)['Supported']:
        return True
    else:
        debug('FALSE, file not supported %s' % inFile)
        return False

def kill(popen):
    debug('killing pid=%s' % str(popen.pid))
    if mswindows:
        win32kill(popen.pid)
    else:
        import os, signal
        for i in xrange(3):
            debug('sending SIGTERM to pid: %s' % popen.pid)
            os.kill(popen.pid, signal.SIGTERM)
            time.sleep(.5)
            if popen.poll() is not None:
                debug('process %s has exited' % popen.pid)
                break
        else:
            while popen.poll() is None:
                debug('sending SIGKILL to pid: %s' % popen.pid)
                os.kill(popen.pid, signal.SIGKILL)
                time.sleep(.5)

def win32kill(pid):
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
    ctypes.windll.kernel32.TerminateProcess(handle, -1)
    ctypes.windll.kernel32.CloseHandle(handle)
