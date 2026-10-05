from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, random
F='/home/user/streams/stream-clipper/assets/fonts/Montserrat-Black.ttf'
YEL=(255,214,0); BLK=(12,12,12); WHT=(255,255,255)
def bubble(size, rot=-8, shake=True):
    S=size*4; im=Image.new('RGBA',(S,S),(0,0,0,0)); d=ImageDraw.Draw(im)
    # body
    x0,y0,x1,y1=S*0.12,S*0.16,S*0.88,S*0.74
    d.rounded_rectangle([x0,y0,x1,y1],radius=S*0.17,fill=YEL)
    # tail
    d.polygon([(S*0.24,y1-S*0.05),(S*0.20,S*0.90),(S*0.44,y1-S*0.02)],fill=YEL)
    # ))) — real brackets, growing like a laugh getting louder; fitted inside the bubble
    sizes=[0.20,0.28,0.37]; gap=S*0.03
    def layout(k):
        fs=[ImageFont.truetype(F,int(S*z*k)) for z in sizes]
        bbs=[d.textbbox((0,0),')',font=f) for f in fs]
        return fs,bbs,sum(b[2]-b[0] for b in bbs)+gap*2
    k=1.0
    fs,bbs,tw=layout(k)
    while tw>(x1-x0)*0.62: k*=0.95; fs,bbs,tw=layout(k)
    x=(x0+x1)/2-tw/2+S*0.02; base=(y0+y1)/2
    for f,bb in zip(fs,bbs):
        h=bb[3]-bb[1]; d.text((x-bb[0],base-h/2-bb[1]),')',font=f,fill=BLK)
        x+=(bb[2]-bb[0])+gap
    if shake:
        for (ax,ay,bx,by) in [(0.86,0.08,0.93,0.02),(0.92,0.16,0.99,0.13),(0.80,0.03,0.83,-0.03)]:
            d.line([S*ax,S*ay,S*bx,S*by],fill=YEL,width=int(S*0.03))
    im=im.rotate(-rot*-1,resample=Image.BICUBIC,center=(S/2,S/2))
    return im.resize((size,size),Image.LANCZOS)
def wordmark(h, color=WHT):
    # "ЧАТ ОРЁТ" with yellow dots on Ё
    f=ImageFont.truetype(F,h*4); tmp=ImageDraw.Draw(Image.new('RGB',(1,1)))
    txt='ЧАТ ОРЕТ'; w=int(tmp.textlength(txt,font=f))+h*2
    im=Image.new('RGBA',(w,int(h*5.2)),(0,0,0,0)); d=ImageDraw.Draw(im)
    y=int(h*0.9); d.text((0,y),txt,font=f,fill=color)
    # dots above Е (index 6)
    xe=tmp.textlength('ЧАТ ОР',font=f); we=tmp.textlength('Е',font=f)
    top=y+f.getbbox('Е')[1]; r=h*0.42
    for dx in (we*0.28,we*0.72):
        cx=xe+dx; cy=top-h*0.75
        d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=YEL)
    bb=im.getbbox(); im=im.crop(bb)
    return im.resize((im.width//4,im.height//4),Image.LANCZOS)

# 1) avatar 800x800
av=Image.new('RGB',(800,800),BLK); b=bubble(640); av.paste(b,(80,90),b)
av.save('logo-avatar-800.png')
# 2) icon on transparent
bubble(1024).save('logo-icon-1024.png')
# 3) horizontal lockup on black and on white
for bg,fg,name in [(BLK,WHT,'logo-horizontal-dark.png'),(WHT,BLK,'logo-horizontal-light.png')]:
    W,H=2200,640; im=Image.new('RGB',(W,H),bg); ic=bubble(560); im.paste(ic,(40,40),ic)
    wm=wordmark(200,fg); im.paste(wm,(640,(H-wm.height)//2+10),wm)
    im.save(name)

# 4) YouTube banner 2560x1440
W,H=2560,1440; ban=Image.new('RGB',(W,H),BLK); d=ImageDraw.Draw(ban)
random.seed(7)
words=['АХАХАХАХ',')))))','ОРУ','КЛИП','ПХАХАХ','KEKW','LUL','АХАХАХ','))))','ОРУУУ','КЛИПНИТЕ','ХАХАХА',')))','ЛОЛ','ОР','ICANT']
f=ImageFont.truetype(F,64)
layer=Image.new('RGBA',(W*2,H*2),(0,0,0,0)); ld=ImageDraw.Draw(layer)
y=0
while y<H*2:
    x=-random.randint(0,300)
    while x<W*2:
        w=random.choice(words); col=(255,214,0,70) if random.random()<0.12 else (255,255,255,22)
        ld.text((x,y),w,font=f,fill=col); x+=ld.textlength(w+'   ',font=f)
    y+=96
layer=layer.rotate(-12,resample=Image.BICUBIC).crop((W//2,H//2,W//2+W,H//2+H))
ban.paste(layer,(0,0),layer)
# dark vignette in the safe area so the logo pops
vg=Image.new('L',(W,H),0); vd=ImageDraw.Draw(vg); vd.rounded_rectangle([420,440,2140,1000],radius=120,fill=235)
vg=vg.filter(ImageFilter.GaussianBlur(70)); ban=Image.composite(Image.new('RGB',(W,H),BLK),ban,vg)
d=ImageDraw.Draw(ban)
# safe area 1546x423 centred: x 507..2053, y 508..931
ic=bubble(420); ban.paste(ic,(505,500),ic)
wm=wordmark(150); ban.paste(wm,(935,540),wm)
tf=ImageFont.truetype(F,35)
tag='СМОТРИМ СТРИМЫ ЦЕЛИКОМ. ТЕБЕ — ТОЛЬКО ОР.'
d.text((940,540+wm.height+34),tag,font=tf,fill=WHT)
pf=ImageFont.truetype(F,34); pill='НАРЕЗКИ · ШОРТСЫ · ЛУЧШЕЕ СО СТРИМОВ'
pw=d.textlength(pill,font=pf); py=540+wm.height+34+78
d.rounded_rectangle([930,py,930+pw+56,py+66],radius=33,fill=YEL); d.text((958,py+12),pill,font=pf,fill=BLK)
ban.save('youtube-banner-2560x1440.png')
# preview with safe zones marked (not for upload)
pv=ban.copy(); pd=ImageDraw.Draw(pv)
pd.rectangle([507,508,2053,931],outline=(255,0,0),width=4); pd.text((515,940),'safe area (all devices)',fill=(255,0,0),font=ImageFont.truetype(F,28))
pd.rectangle([0,508,2560,931],outline=(0,200,255),width=3)
pv.resize((1280,720)).save('_banner-safe-zones-preview.jpg')
print('ok')
