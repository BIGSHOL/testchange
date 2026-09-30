# -*- coding: utf-8 -*-
import json, os
from PIL import Image
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DW, DH = 1412, 2000
# (page, number, x0, y0, x1, y1) in display coords of v{n}.png
B = [
    (1, 1, 130, 588, 692, 838), (1, 2, 130, 1035, 692, 1740),
    (1, 3, 718, 322, 1292, 598), (1, 4, 718, 705, 1292, 985),
    (1, 5, 718, 1135, 1292, 1750),
    (2, 6, 122, 140, 692, 508), (2, 7, 122, 578, 692, 1098),
    (2, 8, 122, 1160, 692, 1905), (2, 9, 722, 140, 1292, 622),
    (2, 10, 722, 728, 1292, 1248), (2, 11, 722, 1352, 1292, 1805),
    (3, 12, 92, 132, 662, 665), (3, 13, 92, 728, 662, 1325),
    (3, 14, 92, 1385, 662, 1885), (3, 15, 692, 132, 1268, 718),
    (3, 16, 692, 992, 1268, 1280),
    (4, 's1', 92, 358, 662, 955), (4, 's2', 92, 1060, 662, 1800),
    (4, 's3', 688, 132, 1252, 725), (4, 's4', 688, 952, 1252, 1560),
]
out = []
cnt = {}
for p, n, x0, y0, x1, y1 in B:
    im = Image.open(os.path.join(HERE, 'pages', f'p{p}_r.png'))
    W, H = im.size
    bb = [x0 / DW, y0 / DH, x1 / DW, y1 / DH]
    cnt[p] = cnt.get(p, 0) + 1
    c = im.crop((int(bb[0] * W), int(bb[1] * H), int(bb[2] * W), int(bb[3] * H)))
    fn = f'p{p}_c{cnt[p]}.png'
    c.save(os.path.join(HERE, 'crop', fn))
    out.append({'page': p, 'number': n, 'bbox': [round(v, 4) for v in bb], 'file': fn})
json.dump(out, open(os.path.join(HERE, 'crop', 'crops.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(len(out))
