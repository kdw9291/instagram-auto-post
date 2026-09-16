# Instagram Auto Post

공식 뉴스·RSS를 수집하고 근거가 확인된 원고를 카드뉴스 4장과 약 30초 릴스로 제작하는 로컬 Python 작업실입니다. 가볼 곳, 뷰티, 신상 먹거리를 다루며 완성본을 확인한 사용자가 선택한 형식만 Instagram에 게시합니다.

- 브라우저 작업실: 새 콘텐츠 만들기 → 카드·릴스·캡션 확인 → 형식별 게시
- 로컬 ComfyUI 이미지 생성, Pretendard 카드 렌더링, FFmpeg 영상 생성
- Cloudinary 업로드, Instagram API 발행, 중복 전송 및 승인 버전 검사
- 상업적 SNS 사용·편집·영상·호스팅 권리가 등록된 제공 이미지를 우선 사용하고, 조건을 충족하지 않으면 로컬 생성 이미지 사용
- CU 다상품 기사, 신세계 팝업·카페 신메뉴, 서울 문화 RSS의 최신 공식 전시 상세 검증
- 개인 계정, 토큰, 운영 이력, 기획 문서, 생성 이미지, AI 모델은 포함하지 않습니다.

## 준비

Python 3.12와 Git이 필요합니다. 제작에는 별도로 설치한 ComfyUI 및 `sd_xl_base_1.0.safetensors` 체크포인트가 필요합니다. 모델은 배포자의 이용 조건을 확인하고 직접 내려받으세요. 이 프로젝트는 모델이나 GPU 런타임을 설치하지 않습니다.

- ComfyUI 설치: https://docs.comfy.org/installation/desktop
- Pretendard: https://github.com/orioncactus/pretendard (라이선스는 assets/fonts에 포함)
- Instagram 게시: 본인 소유 프로페셔널 계정, 해당 계정 접근 및 콘텐츠 게시 권한을 가진 Meta 앱과 토큰
- 공개 미디어 호스팅: 본인 Cloudinary 계정/API 자격 증명

외부 서비스의 무료 한도는 별도로 적용됩니다. 이 프로그램이 무제한 무료 운영을 보장하지 않습니다. Cloudinary 게시 경로는 Free 플랜과 사용량을 검사합니다.

## Windows

PowerShell에서:

```powershell
git clone https://github.com/kdw9291/instagram-auto-post.git
cd instagram-auto-post
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup.py
```

1. ComfyUI를 설치하고 SDXL 체크포인트를 `models/checkpoints`에 둡니다. ComfyUI 서버를 `127.0.0.1:8188`에서 실행합니다. 파일명이 다르면 `config/images.json`의 `checkpoint`를 수정하세요.
2. `config/publishing.json`의 `username`, `user_id`를 **본인 계정**으로 수정합니다. 토큰은 이 JSON에 넣지 않습니다.
3. 게시하려면 다음 숨김 입력 스크립트를 실행합니다. 인증은 현재 Windows 사용자의 DPAPI로 암호화됩니다. 다른 PC로 인증 파일을 복사하지 말고 다시 저장하세요.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/save-instagram-token.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/save-cloudinary-credentials.ps1
.\.venv\Scripts\python.exe -m src.server
```

브라우저에서 http://127.0.0.1:8765 를 엽니다. 서버 종료는 실행 터미널에서 Ctrl+C입니다. 개인 PC의 바탕화면 바로가기 및 자동 엔진 실행기는 배포하지 않으며 이 공통 실행 방법을 사용합니다.

## macOS

Python 3.12와 Git 설치 후 터미널에서:

```bash
git clone https://github.com/kdw9291/instagram-auto-post.git
cd instagram-auto-post
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/setup.py
```

1. ComfyUI 공식 macOS 설치 안내에 따라 설치합니다. 하드웨어별 지원 여부를 확인하세요. SDXL 모델을 설치하고 `127.0.0.1:8188`에서 서버를 실행합니다. 생성 속도와 메모리 요구량은 기기에 따라 다릅니다.
2. `config/publishing.json`에 본인 `username`, `user_id`를 설정합니다.
3. 본인 로그인 세션에서 아래 스크립트로 토큰·Cloudinary 정보를 macOS Keychain에 저장하고 작업실을 실행합니다.

```bash
python scripts/save-keychain.py
python -m src.server
```

http://127.0.0.1:8765 를 엽니다. Keychain 접근 요청이 표시되면 본인 프로그램인지 확인하세요. macOS 실행 경로와 Keychain 지원은 코드에 포함되어 있지만 **macOS 실기기의 이미지 생성부터 실제 게시까지는 검증하지 않았습니다**. Windows DPAPI 파일은 macOS에서 사용할 수 없습니다.

## 사용 및 한계

- 작업실을 열기만 해서는 제작/발행하지 않습니다. `새 콘텐츠 만들기`를 눌러 시작하세요. 수집 대상과 이미지를 실제 생성할 엔진 연결이 필요합니다.
- 기존 소재는 갱신될 수 있으며 클릭할 때마다 새로운 뉴스가 생기는 것은 아닙니다. 지원하지 않는 기사 구조, 근거 부족, 접속 실패, 기한 경과는 보류됩니다. 범용 뉴스 전체를 자동 편집하는 도구가 아닙니다.
- 카드나 릴스가 게시되면 해당 원고는 `게시됨`으로 잠기고 이후 수집에서 재검증·이미지 재생성·최신 원고 갱신을 하지 않습니다. 한 형식만 먼저 게시했다면 같은 버전의 남은 형식은 이어서 게시할 수 있습니다.
- 카드만/릴스만/둘 다 게시 버튼은 실제 게시를 수행합니다. `publishing.enabled`는 기존 자동 워커용 설정이며 수동 게시 버튼을 차단하지 않습니다.
- 연결이 끊겨 발행 결과가 불명확하면 자동 재전송하지 않습니다. Instagram과 처리 기록을 확인한 뒤 복구해야 합니다.
- PC와 ComfyUI를 제작 중 켜 두세요. 서버는 loopback에만 바인딩되며 인터넷에 직접 공개하지 마세요.
- 생성 이미지는 실제 제품·현장 사진이 아닙니다. 마지막 카드와 캡션에 이를 표시합니다.
- 제공 이미지를 쓰려면 `config/media-rights.json`에 개별 자산의 권리 근거와 해시를 등록해야 합니다. 금지 문구가 없다는 이유만으로 사용하지 않으며, 미등록·만료·검증 실패 자산은 자동 생성 이미지로 대체됩니다.
- 개인 브랜드 이미지는 제외되어 기본 엔딩이 표시됩니다. 자신의 엔딩 PNG를 `assets/images/brand/follow-generated-v1.png`로 넣으면 마지막 카드와 릴스 끝에 사용합니다. 4:5 권장, 이미지 안에 AI 연출 안내를 포함하세요. 해당 폴더는 Git에서 제외됩니다.
- 글꼴은 저장소에 포함된 Pretendard를 사용합니다. 추가 이미지·계정 정보는 로컬 설정에만 보관하세요.

## 개발 검증

```bash
python -m unittest discover -s tests
```

테스트에는 모의 API를 사용합니다. 전체 테스트 통과가 외부 계정의 실제 게시 권한이나 macOS 호환성을 보증하지 않습니다.
