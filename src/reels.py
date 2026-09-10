"""Local 30-second card slideshow. A card approval never approves the video."""
import hashlib
import json
import subprocess
from pathlib import Path
from .artifacts import valid_bundle
from .editorial import verify_content

POLICY='card-reel-v1-1080x1920-30fps-30s'


def encoder(root):
    candidates=list((Path(root)/'data/runtime/video-tools/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
    if len(candidates)==1:return str(candidates[0])
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def build(root,item_id,version,content):
    root=Path(root)
    if content.get('sample'):raise ValueError('샘플 릴스 제외')
    if not valid_bundle(root,item_id,version,content):raise ValueError('카드 원본 무결성 오류')
    verify_content(root,content)
    key=hashlib.sha256((version+POLICY).encode()).hexdigest()
    directory=root/'assets/videos/generated'/item_id/key
    directory.mkdir(parents=True,exist_ok=True)
    video=directory/'reel.mp4';manifest=directory/'manifest.json'
    if manifest.exists():
        saved=json.loads(manifest.read_text(encoding='utf-8'))
        if saved.get('card_version')!=version or saved.get('policy')!=POLICY or hashlib.sha256(video.read_bytes()).hexdigest()!=saved.get('sha256'):
            raise ValueError('릴스 원본 변경 감지')
        return saved
    inputs=[];filters=[]
    for index in range(4):
        card=root/'assets/images/generated'/item_id/version/f'card-{index+1}.png'
        inputs += ['-loop','1','-framerate','30','-t','7.5','-i',str(card)]
        filters.append(f'[{index}:v]scale=960:1200,pad=1080:1920:60:240:color=0xF4F1E8,setsar=1,setpts=PTS-STARTPTS[v{index}]')
    filters.append('[v0][v1][v2][v3]concat=n=4:v=1:a=0[out]')
    temp=directory/'rendering.mp4'
    command=[encoder(root),'-hide_banner','-loglevel','error','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[out]',
             '-t','30','-r','30','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-g','60','-threads','4',
             '-movflags','+faststart','-an',str(temp)]
    subprocess.run(command,check=True,capture_output=True,timeout=240)
    if not valid_bundle(root,item_id,version,content):raise ValueError('렌더 중 카드 원본 변경')
    temp.replace(video)
    saved={'item_id':item_id,'card_version':version,'policy':POLICY,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
           'path':video.relative_to(root).as_posix(),'seconds':30,'fps':30,'width':1080,'height':1920,
           'audio':False,'caption':content['caption'],'approval':None,'status':'awaiting_review'}
    manifest.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    return saved


def tick(store):
    config=store.root/'config/reels.json'
    if not config.exists() or json.loads(config.read_text(encoding='utf-8')).get('enabled') is not True:return
    with store.connect() as db:
        rows=db.execute("SELECT * FROM items WHERE state IN ('waiting','ready','approved') ORDER BY created DESC").fetchall()
    for row in rows:
        content=json.loads(row['content'])
        if content.get('sample'):continue
        key=hashlib.sha256((row['version']+POLICY).encode()).hexdigest()
        if (store.root/'assets/videos/generated'/row['id']/key/'manifest.json').exists():continue
        try:build(store.root,row['id'],row['version'],content)
        except (ValueError,OSError,subprocess.SubprocessError):
            with store.connect() as db:store.event(db,'릴스 제작 보류: '+row['id']+' · 근거/인코더 확인 필요')
        return  # Bound work to one new video per worker cycle.
