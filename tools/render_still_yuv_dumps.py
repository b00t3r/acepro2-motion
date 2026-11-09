"""Render sampled native NV12 diagnostics for comparison with saved JPEGs."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[1]/'analysis/still-debug-hardware'
tiles=[]
for stem in ('LIV_20261029_201342_962','LIV_20261029_201348_963'):
    for name in ('02.yuv','03.yuv','jpeg'):
        if name=='jpeg':
            im=Image.open(ROOT/'captures'/f'{stem}.jpg').convert('RGB')
        else:
            data=np.fromfile(ROOT/'captures'/f'{stem}_dbg'/name,dtype=np.uint8)
            w,h=4096,3072
            assert len(data)==w*h*3//2
            y=data[:w*h].reshape(h,w)[::4,::4]
            uv=data[w*h:].reshape(h//2,w//2,2)[::2,::2]
            im=Image.fromarray(np.dstack((y,uv[:,:,0],uv[:,:,1])),'YCbCr').convert('RGB')
            im.save(ROOT/f'{stem}_{name}.png')
        tile=Image.new('RGB',(450,370),'white')
        tile.paste(ImageOps.contain(im,(450,340)),(0,30))
        ImageDraw.Draw(tile).text((5,5),f'{stem} {name}',fill='black')
        tiles.append(tile)
sheet=Image.new('RGB',(1350,740),'white')
for i,tile in enumerate(tiles):
    sheet.paste(tile,((i%3)*450,(i//3)*370))
sheet.save(ROOT/'yuv-comparison.jpg')
