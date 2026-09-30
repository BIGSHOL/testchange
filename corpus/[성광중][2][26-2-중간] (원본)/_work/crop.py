import fitz, json, os
from PIL import Image
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(D, "_work")
doc = fitz.open(os.path.join(D, "source.pdf"))
for i in range(1, 6):
    p = os.path.join(W, f"p{i+1}_300.png")
    if not os.path.exists(p):
        doc[i].get_pixmap(dpi=300).save(p)
B = [
 (2,1,[0.08,0.19,0.495,0.35]),(2,2,[0.08,0.385,0.495,0.60]),(2,3,[0.08,0.67,0.495,0.865]),
 (2,4,[0.495,0.12,0.925,0.29]),(2,5,[0.495,0.46,0.925,0.69]),
 (3,6,[0.08,0.115,0.50,0.285]),(3,7,[0.08,0.345,0.50,0.575]),(3,8,[0.08,0.63,0.50,0.86]),
 (3,9,[0.50,0.115,0.93,0.31]),(3,10,[0.50,0.45,0.93,0.69]),
 (4,11,[0.075,0.11,0.50,0.305]),(4,12,[0.075,0.365,0.50,0.61]),(4,13,[0.075,0.67,0.50,0.87]),
 (4,14,[0.495,0.11,0.93,0.32]),(4,15,[0.495,0.46,0.93,0.685]),
 (5,16,[0.08,0.10,0.51,0.355]),(5,17,[0.08,0.46,0.51,0.75]),(5,18,[0.505,0.10,0.94,0.33]),
 (5,19,[0.505,0.455,0.94,0.665]),
 (6,20,[0.08,0.095,0.51,0.47]),(6,21,[0.08,0.61,0.51,0.79]),(6,22,[0.505,0.095,0.93,0.29]),
]
out=[]; cnt={}
for pg,num,bb in B:
    im = Image.open(os.path.join(W, f"p{pg}_300.png"))
    w,h = im.size
    cnt[pg]=cnt.get(pg,0)+1
    c = im.crop((int(bb[0]*w),int(bb[1]*h),int(bb[2]*w),int(bb[3]*h)))
    c.save(os.path.join(D,"crop",f"p{pg}_c{cnt[pg]}.png"))
    out.append({"page":pg,"number":num,"bbox":bb,"file":f"p{pg}_c{cnt[pg]}.png"})
json.dump(out, open(os.path.join(D,"crop","crops.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out))
