"""Original topic illustrations. Never represent real products or artworks."""
from PIL import Image, ImageDraw, ImageOps
from pathlib import Path
import hashlib
import re

ASSET_DIR=Path(__file__).resolve().parents[1]/'assets/images/backgrounds-v4'
GENERATED_LABELS={'exhibition':'AI 공간 콘셉트 · 실제 현장·작품 아님','lip':'AI 뷰티 콘셉트 · 실제 제품·발색 아님','bakery':'AI 제빵 콘셉트 · 실제 제품 아님'}

def background_label(content):
    if content.get('news_image'):return 'AI 뉴스 연출 이미지 · 실제 제품·현장 아님'
    topic=topic_for(content)
    return GENERATED_LABELS.get(topic,TOPICS[topic][0])

TOPICS = {
    'exhibition': ('전시 주제 일러스트 · 실제 전시·작품 아님', '#e8e2d5', '#788a72'),
    'outing': ('나들이 주제 일러스트 · 실제 장소 아님', '#e4e7d4', '#72886b'),
    'lip': ('립 메이크업 일러스트 · 실제 제품·발색 아님', '#eddbd6', '#ba777c'),
    'skincare': ('스킨케어 주제 일러스트 · 실제 제품 아님', '#e3e8df', '#88a39b'),
    'bakery': ('베이커리 주제 일러스트 · 실제 제품 아님', '#eddfc9', '#bd8959'),
    'food': ('먹거리 주제 일러스트 · 실제 제품 아님', '#ede4cf', '#a58a61'),
}

def topic_for(content):
    title = (content['title'] + ' ' + content.get('subtitle','')).lower()
    if content['category']=='place':
        return 'exhibition' if any(x in title for x in ('전시','미술관','갤러리','museum','art')) else 'outing'
    if content['category']=='beauty':
        return 'lip' if any(x in title for x in ('립','틴트','lip')) else 'skincare'
    return 'bakery' if any(x in title for x in ('빵','베이커리','크루아상','도넛','베이글')) else 'food'

def background(content,root=None):
    topic = topic_for(content)
    if content.get('news_image'):
        asset=content['news_image'];key=asset.get('id','')
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('잘못된 뉴스 이미지 ID')
        path=Path(root or ASSET_DIR.parents[2])/'assets/images/news'/f'{key}.png'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=asset.get('sha256'):raise ValueError('뉴스 이미지가 변경되었습니다.')
        with Image.open(path) as source:return ImageOps.fit(source.convert('RGB'),(1080,1350),method=Image.Resampling.LANCZOS),background_label(content)
    if topic in GENERATED_LABELS and (ASSET_DIR/f'{topic}.png').exists():
        with Image.open(ASSET_DIR/f'{topic}.png') as source:
            return ImageOps.fit(source.convert('RGB'),(1080,1350),method=Image.Resampling.LANCZOS),GENERATED_LABELS[topic]
    label, base, accent = TOPICS[topic]
    im=Image.new('RGB',(1080,1350),base)
    d=ImageDraw.Draw(im)
    dark='#244338'; cream='#faf6eb'
    if topic=='exhibition':
        # Empty graphic frames and a visitor bench convey the topic without copying art.
        d.polygon([(0,600),(1080,510),(1080,1350),(0,1350)],fill='#d1c7b5')
        d.polygon([(0,130),(230,190),(230,580),(0,625)],fill='#ddd4c5')
        for x,y,w,h in [(310,210,260,320),(660,250,310,240)]:
            d.rectangle((x+16,y+18,x+w+16,y+h+18),fill='#cec8b7')
            d.rectangle((x,y,x+w,y+h),fill=dark)
            d.rectangle((x+14,y+14,x+w-14,y+h-14),fill=cream)
            # Blank inset, intentionally no artwork.
            d.rectangle((x+35,y+35,x+w-35,y+h-35),fill='#dedfcf')
        d.polygon([(350,630),(700,580),(840,640),(490,695)],fill=accent)
        d.polygon([(490,695),(840,640),(840,669),(490,723)],fill=dark)
        d.rectangle((505,715,521,776),fill=dark);d.rectangle((808,666,824,744),fill=dark)
    elif topic=='outing':
        d.ellipse((685,170,875,360),fill='#e4bd76')
        d.polygon([(0,590),(280,300),(540,615),(820,380),(1080,560),(1080,1000),(0,1000)],fill=accent)
        d.polygon([(430,1350),(630,600),(710,600),(970,1350)],fill=cream)
        d.rounded_rectangle((190,330,220,740),radius=12,fill=dark)
        d.rounded_rectangle((75,245,330,480),radius=95,fill='#a6b68c')
    elif topic=='lip':
        d.ellipse((240,650,870,790),fill='#dcc4b9')
        d.rounded_rectangle((330,450,495,720),radius=16,fill=dark)
        d.rectangle((345,375,480,465),fill='#c2aa7f')
        d.polygon([(360,375),(360,250),(465,200),(465,375)],fill=accent)
        d.rounded_rectangle((580,370,760,720),radius=20,fill='#b78484')
        d.line((595,385,595,700),fill='#e8bfbc',width=12)
    elif topic=='skincare':
        d.ellipse((170,650,910,800),fill='#cbd6cc')
        d.rounded_rectangle((310,320,535,720),radius=35,fill=accent)
        d.rectangle((365,250,485,325),fill=dark)
        d.rounded_rectangle((610,530,835,710),radius=30,fill=cream)
        d.rounded_rectangle((600,485,845,560),radius=20,fill='#b9c8bb')
        d.rectangle((350,475,495,565),fill=cream)
    elif topic=='bakery':
        d.ellipse((135,420,950,780),fill=cream)
        d.ellipse((195,460,900,725),outline='#d1c4a9',width=5)
        d.rounded_rectangle((280,325,780,645),radius=150,fill=accent)
        for x in (370,485,600):d.line((x,420,x+65,515),fill='#f0d2a4',width=32)
    else:
        d.ellipse((200,390,880,755),fill=cream)
        d.ellipse((260,435,820,690),fill=accent)
        d.arc((325,475,720,625),0,180,fill=cream,width=18)
        d.rounded_rectangle((915,280,935,745),radius=9,fill=dark)
        d.rounded_rectangle((950,280,970,745),radius=9,fill=dark)
    return im, label
