# Smart Recycle Bin

스마트 분리수거함 프로젝트의 프론트엔드와 백엔드를 함께 관리하는 저장소입니다.

## 폴더 구성

```text
smart_recycle_bin/
├── frontend/        # 사용자 화면과 프론트엔드 코드
├── backend/         # 서버, AI 모델 및 관련 자료
└── admin-dashboard/ # 대회 시연용 관리자 앱 (React + FastAPI + SQLite)
```

## 관리자 대시보드 MVP

[`admin-dashboard/`](admin-dashboard/)에 로컬 서버에서 실행하는 관리자 앱이 있습니다.

- 3층 더미 건물의 쓰레기통 번호와 초록·주황·빨강 포화 상태
- 관리자실에서 출발·복귀하는 수거 경로와 관리자 인원별 작업 배분
- 주황색 쓰레기통을 경로에 포함할지 선택
- 건물 배치 편집, 로그인·회원가입, 수거 기록, 백업·복원
- 실물 쓰레기통 1대용 센서 수신 API와 별도로 표시되는 시뮬레이션

Windows에 Python 3.10 이상과 Node.js 20.19 이상을 설치한 뒤 `admin-dashboard/실행하기.cmd`를 실행하세요. 최초 실행 시 필요한 의존성과 화면을 준비하고 `http://127.0.0.1:8765`를 엽니다. 로그인 화면의 **시연 계정으로 둘러보기**로 시작할 수 있습니다.

상세 실행 방법, 대회 시연 순서, 실물 센서 연결 방식은 [관리자 앱 안내](admin-dashboard/README.md)를 참고하세요. 계정 데이터·수거 기록·도면·장치 연결 키는 실행한 PC에만 저장되며 Git에 포함되지 않습니다. 기존 AI 모델과 장치 펌웨어에서 센서 수신 API로 값을 보내는 연결은 별도로 구성해야 합니다.

## 개발 시작

1. 프론트엔드 코드는 `frontend/`에 추가합니다.
2. 백엔드 코드는 `backend/`에 추가합니다.
3. 사용하는 언어와 프레임워크를 정한 뒤 각 폴더의 README에 설치·실행 방법을 기록합니다.
4. API 경로, 요청·응답 형식, 개발 서버 주소를 정해 두 작업을 연결합니다.

## 환경 설정

환경 변수는 각 작업 폴더의 `.env` 파일에 보관합니다. 공유할 설정 항목은 실제 비밀값 없이 `.env.example`로 작성합니다. 의존성 폴더와 빌드 결과물은 `.gitignore`에서 제외합니다.

## 변경사항 올리기

저장소 폴더에서 변경한 파일을 확인한 뒤 커밋하고 업로드합니다.

```sh
git status
git add frontend backend README.md .gitignore .gitattributes
git commit -m "Describe the change"
git push origin main
```
