# Foto contoh per kategori (untuk screenshot panduan): adegan sederhana + label
import random, sqlite3, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
F='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(n):
    try: return ImageFont.truetype(F,n)
    except: return ImageFont.load_default()
PAL={'dashboard':('#0f2a3a','#2a7fa8'),'tampak_depan':('#7cb7e8','#d9c7a1'),'teknisi':('#8fc7ef','#6f8f5a'),'outdoor':('#9ccbf0','#b9b2a6'),
 'indoor':('#e9e2d6','#bfae95'),'sn_kit':('#f2f2f2','#d6d6d6'),'sn_router':('#efefef','#cfcfcf'),'sn_ap':('#f5f5f5','#d9d9d9'),
 'ping':('#111418','#1d2530'),'speed':('#0d1b2a','#1b3a5c'),'simkopdes':('#f4f7fb','#dfe8f3')}
LBL={'dashboard':'STARMON','tampak_depan':'KOPERASI DESA MERAH PUTIH','teknisi':'TEKNISI + PIC','outdoor':'DISH STARLINK','indoor':'ROUTER + AP',
 'sn_kit':'SN KIT','sn_router':'SN ROUTER','sn_ap':'SN AP','ping':'PING 8.8.8.8','speed':'SPEEDTEST','simkopdes':'SIMKOPDES'}
def make(cat,seed,path):
    r=random.Random(seed);W,H=640,480;a,b=PAL.get(cat,('#888','#bbb'))
    im=Image.new('RGB',(W,H),a);d=ImageDraw.Draw(im)
    for y in range(H):
        t=y/H;ca=tuple(int(a[i:i+2],16) for i in (1,3,5));cb=tuple(int(b[i:i+2],16) for i in (1,3,5))
        d.line([(0,y),(W,y)],fill=tuple(int(ca[k]*(1-t)+cb[k]*t) for k in range(3)))
    if cat in('tampak_depan','teknisi','outdoor'):
        d.rectangle([60,200,580,470],fill=(236,231,220));d.polygon([(40,210),(320,90),(600,210)],fill=(176,58,46))
        d.rectangle([250,320,390,470],fill=(120,84,60));d.rectangle([110,170,530,215],fill=(196,30,40))
        d.text((320,192),'KOPDES MERAH PUTIH',font=font(26),fill='white',anchor='mm')
        if cat=='teknisi':
            for x in (200,440):d.ellipse([x-28,250,x+28,306],fill=(214,170,130));d.rectangle([x-40,306,x+40,440],fill=(30,80,140) if x<300 else (40,120,70))
        if cat=='outdoor':d.ellipse([430,40,560,170],fill=(245,245,245),outline=(160,160,160),width=4);d.line([(495,170),(495,215)],fill=(90,90,90),width=8)
    elif cat in('sn_kit','sn_router','sn_ap'):
        d.rounded_rectangle([90,120,550,360],18,fill='white',outline=(150,150,150),width=3)
        d.text((320,180),LBL[cat],font=font(30),fill=(40,40,40),anchor='mm')
        sn={'sn_kit':'KIT','sn_router':'RTR','sn_ap':'AP'}[cat]+'%07d'%r.randint(1000000,9999999)
        d.text((320,250),'S/N '+sn,font=font(34),fill=(10,10,10),anchor='mm')
        for i in range(36):d.rectangle([140+i*10,300,144+i*10+r.randint(0,4),340],fill='black')
    elif cat in('dashboard','ping','speed','simkopdes'):
        d.rectangle([30,30,610,450],fill=(250,250,250) if cat=='simkopdes' else (20,26,34))
        fg=(30,30,30) if cat=='simkopdes' else (120,230,190)
        d.text((60,60),LBL[cat],font=font(28),fill=fg)
        if cat=='speed':
            d.text((320,230),'%d'%r.randint(90,220),font=font(110),fill=(120,200,255),anchor='mm');d.text((320,320),'Mbps download',font=font(26),fill=(200,210,220),anchor='mm')
        elif cat=='ping':
            for i in range(8):d.text((60,120+i*38),'64 bytes from 8.8.8.8: time=%d ms'%r.randint(28,60),font=font(20),fill=fg)
        elif cat=='dashboard':
            for i in range(10):h=r.randint(40,240);d.rectangle([80+i*50,400-h,110+i*50,400],fill=(42,160,200))
        else:
            d.rectangle([60,110,580,150],fill=(200,40,50));d.text((80,118),'simkopdes.go.id',font=font(20),fill='white')
            for i in range(5):d.rectangle([60,180+i*48,580,210+i*48],fill=(225,230,238))
    else:
        d.rectangle([150,150,490,380],fill=(60,60,64));d.rectangle([190,190,450,250],fill=(30,30,34))
        for i in range(5):d.ellipse([200+i*48,300,220+i*48,320],fill=(90,220,120))
        d.text((320,420),LBL.get(cat,cat.upper()),font=font(26),fill=(50,50,50),anchor='mm')
    im=im.filter(ImageFilter.GaussianBlur(0.6));os.makedirs(os.path.dirname(path),exist_ok=True);im.save(path,'JPEG',quality=78)
base='/tmp/guide/data/projects/p1'
c=sqlite3.connect(base+'/project.db')
rows=c.execute('select p.id,p.category,l.code from photos p join locations l on l.id=p.location_id').fetchall()
for pid,cat,code in rows:
    rel=f'images/{code}/{cat}_{pid}.jpg';make(cat,pid,base+'/'+rel);c.execute('update photos set path=? where id=?',(rel,pid))
c.commit();print('photos',len(rows))
os.makedirs('samples',exist_ok=True)
for i,cat in enumerate(PAL):make(cat,1000+i,f'samples/{cat}.jpg')
print('ok')
