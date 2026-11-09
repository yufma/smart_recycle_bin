# Smart Recycle Bin

스마트 분리수거함과 관리자 웹 앱 **inloop**를 함께 관리하는 저장소입니다.

## 폴더 구성

```text
smart_recycle_bin/
├── admin-dashboard/      # inloop 관리자 앱
│   ├── src/              # React 화면
│   ├── server/           # 로컬 API · SQLite · 동선 알고리즘
│   ├── browser/          # 공개 체험용 브라우저 실행 환경
│   ├── assets/           # 공개 체험 도면 사진 원본
│   ├── datasets/         # 인하대 공개 지도 자료
│   ├── tests/            # 자동 검사
│   ├── tools/            # 도면·체험 묶음 생성과 장치 연결 도구
│   └── android/          # Android WebView 앱
└── backend/              # AI 분류
    ├── models/           # 모델 가중치 · ESP32-S3 양자화 모델
    ├── predict.py        # 사진 분류 실행
    └── README.md         # 모델 사용법 · 학습·검증 기록
```

## 관리자 대시보드 MVP

**[inloop 공개 체험](https://yufma.github.io/smart_recycle_bin/)** · 설치 없이 **시연 계정으로 둘러보기**로 시작할 수 있습니다. 방문자마다 자기 브라우저에 독립된 더미 데이터가 저장됩니다.

[`admin-dashboard/`](admin-dashboard/)에 로컬 서버와 GitHub Pages에서 실행하는 관리자 앱 **inloop**가 있습니다. 최신 소스는 **`main`**, 공개 화면은 **`gh-pages`** 브랜치에 있습니다.

- 기본 3층 건물과 여러 시연 건물의 쓰레기통 번호, 칸별 적재율과 초록·주황·빨강 상태
- 관리자실에서 출발해 분리수거장에서 종료하는 경로와 ‘빨리 끝내기 / 인력 아끼기’ 배분
- 주황색 쓰레기통을 경로에 포함할지 선택
- 건물 배치 편집, 로그인·회원가입, 수거 기록, 백업·복원
- 더미관·용현캠퍼스·정석학술정보관 6개 층의 독립된 체험 데이터
- 관리자별·쓰레기통별 수거 완료와 경로 유지, 기록 날짜의 초록색 표시 및 기간 검색
- 실물 쓰레기통 1대용 센서 수신 API와 별도로 표시되는 시뮬레이션

Windows에 Python 3.10 이상과 Node.js 20.19 이상을 설치한 뒤 `admin-dashboard/실행하기.cmd`를 실행하세요. 최초 실행 시 필요한 의존성과 화면을 준비하고 `http://127.0.0.1:8765`를 엽니다. 로그인 화면의 **시연 계정으로 둘러보기**로 시작할 수 있습니다.

상세 실행 방법, 대회 시연 순서, 실물 센서 연결 방식은 [관리자 앱 안내](admin-dashboard/README.md)를 참고하세요. 로컬 계정·개인 배치·수거 기록·장치 연결 키는 실행한 PC에만 저장되며 Git에 포함되지 않습니다. 공개 사이트에는 지도·도면 사진과 별도의 가상 배치를 사용합니다. 기존 AI 모델과 장치 펌웨어에서 센서 수신 API로 값을 보내는 연결은 별도로 구성해야 합니다.

2026-11-02 디자인 적용: 메인 화면을 수거 요약 → 센서·쓰레기통 현황 → 관리자별 동선 순서로 정리했습니다. 모바일 메뉴, 키보드 조작, 오류 복구와 경로 재계산 안내도 보완했습니다. [변경 내용과 검증](admin-dashboard/README.md#2026-11-02-디자인-적용), [공통 디자인 기준](.interface-design/system.md)을 참고하세요.

2026-10-31 보완: 센서 전송 도구의 칸 선택, 칸별 측정 유효 시간, 운반 용량 초과 차단을 수정했습니다. 재현 조건과 변경 동작은 [관리자 앱 수정 사항](admin-dashboard/README.md#2026-10-31-수정-사항)에 정리했습니다.

## 개발 시작

- 관리자 화면은 `admin-dashboard/src/`, API·동선 계산은 `admin-dashboard/server/`에서 수정합니다.
- AI 모델과 사진 분류는 `backend/`에서 관리합니다. [모델 실행 방법](backend/README.md)을 참고하세요.
- 도서관 사진은 `admin-dashboard/assets/jeongseok-floorplans/`, 캠퍼스 자료는 `admin-dashboard/datasets/`에 있습니다.
- `dist/`, `site-dist/`, 공개 체험용 `backend.zip`·`manifest.json`은 소스에서 다시 만드는 결과물이며 Git에 넣지 않습니다. [빌드·배포 방법](admin-dashboard/README.md#공개-체험--github-pages)을 참고하세요.

## 환경 설정

환경 변수는 각 작업 폴더의 `.env` 파일에 보관합니다. 공유할 설정 항목은 실제 비밀값 없이 `.env.example`로 작성합니다. 의존성 폴더와 빌드 결과물은 `.gitignore`에서 제외합니다.

## 변경사항 올리기

최신 `main`에서 작업 브랜치를 만들고 변경한 파일만 커밋합니다. 검사 후 `main`에 병합하며, 웹 공개 결과물은 `gh-pages`에 올립니다.

```sh
git switch main
git pull --ff-only origin main
git switch -c codex/작업-이름
git status
# 변경한 파일을 선택해 git add 후 커밋합니다.
git commit -m "변경 내용 설명"
git push -u origin HEAD
```
