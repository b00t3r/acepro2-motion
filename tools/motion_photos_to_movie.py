#!/usr/bin/env python3
"""Join timestamp-named Ace Pro 2 .MP.jpg Motion Photos without re-encoding."""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

def run(folder, output):
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg: raise ValueError('ffmpeg was not found; install it or add it to PATH')
    photos=sorted((p for p in folder.iterdir() if p.is_file() and
                   re.fullmatch(r'LIV_\d{8}_\d{6}_\d+\.MP\.jpg',p.name,re.I)),
                  key=lambda p:p.name.casefold())
    if not photos: raise ValueError('No timestamp-named LIV_*.MP.jpg files in '+str(folder))
    if output.exists():raise ValueError('Output already exists: '+str(output))
    with tempfile.TemporaryDirectory(prefix='motion-photo-') as temp:
        tmp=Path(temp); clips=[]
        for index,photo in enumerate(photos):
            data=photo.read_bytes()
            if not data.startswith(b'\xff\xd8'):raise ValueError(photo.name+': not a JPEG')
            # Our camera writes exactly one XMP MotionPhoto item. The embedded
            # MP4 occupies its declared number of bytes at the end of file.
            matches=re.findall(rb'Item:Semantic="MotionPhoto"\s+Item:Length="(\d+)"',data[:2_000_000])
            if len(matches)!=1:raise ValueError(photo.name+': cannot find unique motion-video length')
            length=int(matches[0]);start=len(data)-length
            if start<2 or data[start+4:start+8]!=b'ftyp':
                raise ValueError(photo.name+': embedded MP4 does not match metadata')
            clip=tmp/f'{index:06d}.mp4';clip.write_bytes(data[start:]);clips.append(clip)
            print('Added:',photo.name,flush=True)
        listing=tmp/'list.txt'
        listing.write_text(''.join("file '"+str(p)+"'\n" for p in clips),encoding='utf-8')
        subprocess.run([ffmpeg,'-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(output)],check=True)
    print('Created:',output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',nargs='?',default='.',type=Path)
    p.add_argument('-o','--output',type=Path,help='Output file (default: motion-photo-movie.mp4 in folder)')
    args=p.parse_args()
    try:
        folder=args.folder.expanduser().resolve()
        run(folder,(args.output.expanduser().resolve() if args.output else folder/'motion-photo-movie.mp4'))
    except (ValueError,OSError,subprocess.CalledProcessError) as e:
        sys.exit('Error: '+str(e))
