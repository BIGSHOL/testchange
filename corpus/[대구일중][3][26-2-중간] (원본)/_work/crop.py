import fitz, json, os
from PIL import Image
doc = fitz.open("source.pdf")
print(len(doc))
os.makedirs("_work/hi", exist_ok=True)
for i, p in enumerate(doc):
    pix = p.get_pixmap(dpi=300); pix.save(f"_work/hi/p{i+1}.png")
C = [
 (1,1,[.06,.075,.51,.24]),(1,2,[.06,.365,.51,.49]),(1,3,[.03,.65,.51,.79]),
 (1,4,[.52,.075,.96,.15]),(1,5,[.52,.26,.97,.505]),(1,6,[.52,.63,.99,.85]),
 (2,7,[.06,.11,.49,.285]),(2,8,[.06,.35,.49,.49]),(2,9,[.06,.56,.49,.86]),
 (2,10,[.50,.105,.92,.44]),(2,11,[.50,.465,.92,.63]),(2,12,[.50,.645,.92,.86]),
 (3,13,[.07,.065,.51,.29]),(3,14,[.07,.345,.51,.60]),(3,15,[.05,.67,.51,.88]),
 (3,16,[.52,.065,.97,.295]),(3,17,[.52,.345,.97,.55]),(3,18,[.52,.645,1.0,.895]),
 (4,'s1',[.06,.08,.51,.29]),(4,'s2',[.06,.485,.51,.79]),(4,'s3',[.52,.08,.96,.25]),(4,'s4',[.52,.415,.96,.685]),
]
out=[]; cnt={}
for pg,num,bb in C:
    im = Image.open(f"_work/hi/p{pg}.png"); W,H = im.size
    cnt[pg]=cnt.get(pg,0)+1
    im.crop((int(bb[0]*W),int(bb[1]*H),int(bb[2]*W),int(bb[3]*H))).save(f"crop/p{pg}_c{cnt[pg]}.png")
    out.append({"page":pg,"number":num,"bbox":bb,"file":f"p{pg}_c{cnt[pg]}.png"})
json.dump(out, open("crop/crops.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
