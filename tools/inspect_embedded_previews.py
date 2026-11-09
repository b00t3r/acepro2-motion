"""Inspect independently decodable JPEG previews embedded in capture files."""
import io
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/green-008-010/embedded-previews'
OUT.mkdir(exist_ok=True)
files = [ROOT / 'analysis/green-008-010/comparison/LIV_20261029_175232_007.jpg']
files += sorted((ROOT / 'analysis/green-008-010').glob('*.jpg'))
tiles = []
for path in files:
    if '.MP.' in path.name:
        continue
    data = path.read_bytes()
    start = 0
    count = 0
    while True:
        at = data.find(b'\xff\xd8\xff', start)
        if at < 0:
            break
        start = at + 3
        end = data.find(b'\xff\xd9', start)
        if end < 0:
            continue
        try:
            im = Image.open(io.BytesIO(data[at:end+2]))
            im.load()
        except Exception:
            continue
        # Outer JPEG includes nested EXIF JPEGs; only decode proper standalone
        # inner candidates here. Original main photo is displayed separately.
        if at == 0:
            continue
        count += 1
        name = f'{path.stem}_offset-{at}_{im.width}x{im.height}.jpg'
        (OUT / name).write_bytes(data[at:end+2])
        print(name)
        tile = Image.new('RGB', (420, 300), 'white')
        thumb = ImageOps.contain(im.convert('RGB'), (420, 260))
        tile.paste(thumb, (0, 40))
        ImageDraw.Draw(tile).text((5, 5), f'{path.stem}\n{im.size} offset {at}', fill='black')
        tiles.append(tile)
    print(path.name, 'embedded JPEG count', count)
if tiles:
    sheet = Image.new('RGB', (840, ((len(tiles)+1)//2)*300), 'white')
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 2)*420, (i//2)*300))
    sheet.save(OUT / 'comparison.jpg')
