"""Make a labelled diagnostic sheet from original capture JPEGs."""
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

folder=Path(sys.argv[1])
files=sorted(p for p in folder.glob('LIV_*.jpg') if '.MP.' not in p.name)
sheet=Image.new('RGB',(1000,((len(files)+1)//2)*330),'white')
for i,path in enumerate(files):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        im=ImageOps.contain(im,(500,300))
        x,y=(i%2)*500,(i//2)*330
        sheet.paste(im,(x,y+30))
        ImageDraw.Draw(sheet).text((x+5,y+5),path.name,fill='black')
sheet.save(folder.parent/'contact-sheet.jpg')
print(folder.parent/'contact-sheet.jpg')
