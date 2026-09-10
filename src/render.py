"""Deterministic, locally drawn editorial backgrounds and cards; no AI calls."""
from pathlib import Path
import os
import hashlib
from PIL import Image, ImageDraw, ImageFont
from .backgrounds import background, topic_for, GENERATED_LABELS, ASSET_DIR

RENDER_VERSION = 'editorial-background-v10-generated-ending'

def visual_revision():
    """Asset changes must invalidate approvals even if the manuscript is identical."""
    h=hashlib.sha256(RENDER_VERSION.encode())
    for name in sorted(GENERATED_LABELS):
        asset=ASSET_DIR/f'{name}.png'
        if asset.exists():h.update(asset.read_bytes())
    logo=Path(__file__).resolve().parents[1]/'assets/images/brand/studio-icon-source.png'
    if logo.exists():h.update(logo.read_bytes())
    h.update(FONT.read_bytes());h.update(BOLD.read_bytes())
    ending=Path(__file__).resolve().parents[1]/'assets/images/brand/follow-generated-v1.png'
    if ending.exists():h.update(ending.read_bytes())
    return h.hexdigest()

SIZE = (1080, 1350)
INK = '#18352e'
PAPER = '#f4f2e9'
FONT = Path(os.environ.get('CARD_FONT', str(Path(__file__).resolve().parents[1]/'assets/fonts/Pretendard-Regular.otf')))
BOLD = Path(os.environ.get('CARD_BOLD_FONT', str(Path(__file__).resolve().parents[1]/'assets/fonts/Pretendard-Bold.otf')))
PALETTES = {'place': ('#c8c7a6', '#788a72'), 'beauty': ('#edc8be', '#ab827c'), 'food': ('#e8c899', '#af8656')}
LABELS = {'place': '가볼 곳', 'beauty': '뷰티 신상', 'food': '신상 먹거리'}

def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)

def text(draw, value, xy, size=42, fill=INK, bold=False, width=920, max_lines=8, stroke=0):
    f = font(size, bold)
    lines = []
    for paragraph in str(value).split('\n'):
        line = ''
        for char in paragraph:
            if line and draw.textlength(line + char, font=f) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    if len(lines) > max_lines:
        raise ValueError('문구가 카드 영역보다 깁니다. 자동 제작을 보류했습니다.')
    x, y = xy
    if y + len(lines) * size * 1.5 > 1334:
        raise ValueError('카드 하단 영역을 초과했습니다.')
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill, stroke_width=stroke, stroke_fill=INK)
        y += int(size * 1.5)
    return y

def render_cards(content, directory, root=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    category = content['category']
    bg, background_label = background(content,root)
    photographic=bool(content.get('news_image')) or topic_for(content) in GENERATED_LABELS
    accent={'place':'#18352e','beauty':'#412330','food':'#493021'}[category]
    paths = []
    for index in range(4):
        im = bg.copy()
        d = ImageDraw.Draw(im)
        if photographic and index==0:
            # Full-bleed cover; deterministic type is kept outside the generated image.
            shade=Image.new('RGBA',SIZE,(0,0,0,0));sd=ImageDraw.Draw(shade)
            sd.rectangle((0,0,1080,130),fill=(10,10,10,90))
            for y in range(720,1350):sd.line((0,y,1080,y),fill=(10,10,10,int(150*(y-720)/630)))
            im=Image.alpha_composite(im.convert('RGBA'),shade).convert('RGB');d=ImageDraw.Draw(im)
            text(d,LABELS[category],(64,44),30,PAPER,True)
            text(d,'정보 큐레이션',(795,44),26,PAPER)
            text(d,content['title'],(64,870),78,PAPER,True,max_lines=2)
            text(d,content['subtitle'],(64,1120),32,PAPER,max_lines=2)
            text(d,'01 / 04',(890,1247),25,PAPER)
            path=directory/'card-1.png';im.save(path);paths.append(path);continue
        if index == 3:
            # The approved reusable brand ending is always the fourth card.
            ending=Path(__file__).resolve().parents[1]/'assets/images/brand/follow-generated-v1.png'
            if ending.exists():
                with Image.open(ending) as asset:im=asset.convert('RGB').resize(SIZE,Image.Resampling.LANCZOS)
            else:
                im=Image.new('RGB',SIZE,INK);d=ImageDraw.Draw(im)
                text(d,'다음 소식도 함께해요',(64,480),64,PAPER,True)
                text(d,'프로필에서 팔로우해 주세요',(64,640),42,PAPER)
                text(d,'AI 연출 이미지 포함 · 실제 제품·현장 사진 아님',(64,1240),25,PAPER)
            path=directory/'card-4.png';im.save(path);paths.append(path);continue
        if index >= 1:
            # Reserve the bottom 20% for type; keep the photograph unobstructed.
            d.rectangle((0,1080,1080,1350),fill='#101412')
            if index == 1:
                heading=content['intro_heading'].replace('\n',' ')
                body=content['intro']
            elif index == 2:
                heading='알아두고 가세요' if category=='place' else '구매 전 확인'
                body='\n'.join(f"{f['label']} · {f['value'].replace(chr(10),' ')}" for f in content['facts'])
            else:
                heading=content['cta'].replace('\n',' ')
                body=content['conditions']+'\n'+content['source_label'].replace('\n',' · ')
            # Fit without clipping or silently removing factual content.
            def block(value,top,bottom,preferred,bold=False):
                for size in range(preferred,21,-1):
                    f=font(size,bold);lines=[]
                    for paragraph in value.split('\n'):
                        line=''
                        for char in paragraph:
                            if line and d.textlength(line+char,font=f)>976:
                                lines.append(line);line=char
                            else:line+=char
                        lines.append(line)
                    step=int(size*1.3)
                    if len(lines)*step<=bottom-top:break
                else:raise ValueError('하단 텍스트 영역보다 문구가 깁니다. 원고 보완 필요')
                for line in lines:
                    d.text((52,top),line,font=f,fill=PAPER if bold else '#d4d8d5');top+=step
            block(heading,1098,1156,38,True)
            block(body,1160,1280 if index==3 else 1294,30)
            if index==3:
                d.text((52,1293),background_label,font=font(23),fill='#b6bfb8')
            d.text((948,1318),f'{index+1:02}/04',font=font(18),fill='#b6bfb8')
            path=directory/f'card-{index+1}.png';im.save(path);paths.append(path);continue
        d.rectangle((0, 0, 1080, 128), fill=PAPER)
        text(d, LABELS[category], (64, 40), 30, bold=True)
        text(d, '정보 큐레이션', (795, 44), 26)
        if index == 0:
            d.rectangle((0, 860, 1080, 1350), fill=INK)
            text(d, content['title'], (64, 885), 78, PAPER, True, max_lines=2)
            text(d, content['subtitle'], (64, 1135), 32, PAPER, max_lines=2)
        footer_color = PAPER if index in (0, 3) else INK
        text(d, f'{index + 1:02} / 04', (890, 1260), 25, footer_color)
        path = directory / f'card-{index + 1}.png'
        im.save(path)
        paths.append(path)
    return paths
