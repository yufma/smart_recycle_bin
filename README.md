# Smart Recycle Bin

스마트 분리수거함 프로젝트의 프론트엔드와 백엔드를 함께 관리하는 저장소입니다.

## 폴더 구성

```text
smart_recycle_bin/
├── frontend/   # 사용자 화면과 프론트엔드 코드
└── backend/    # 서버와 API 코드
```

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
