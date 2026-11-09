# Reloop 관리자 화면 디자인 기준

적용 범위: `admin-dashboard/`. 대회에서 실물 쓰레기통 1대와 더미 건물로 수거 흐름을 보여 주는 MVP다.

## 목적과 화면 순서

시설 관리자가 센서 수신 상태와 수거 대상을 확인하고, 주황색 포함 여부·인원·운반 조건에 맞는 경로를 계산한다.
메인 화면은 **수거 요약 + 실물 센서 → 상태별 필터 → 쓰레기통 카드 → 관리자별 경로** 순서다.
관리자실, 수거 지점, 분리수거장이라는 실제 작업 순서가 화면의 중심이다.

## 색과 글자

- 동작: 숲색 `#245746`, 수거 요약: 짙은 숲색 `#173e32`, 요약의 강조: 잎색 `#ddecbb`.
- 바탕 `#f4f6f2`, 패널 `#ffffff`, 본문 `#213c31`, 보조 글 `#607068`, 경계 `#dce4dd`.
- 빨강·주황·초록은 수거 필요·주의·정상이라는 의미를 가진다. 문구와 숫자를 함께 표시한다.
- 기존 로컬 Pretendard를 유지한다. 한글 가독성과 오프라인 시연을 우선한다.
- 화면 제목 26–30px, 섹션 제목 18–19px, 주요 본문·조작 13–14px, 보조 표기 11–12px.
- 적재율·시간·수량에는 고정 폭 숫자를 사용한다.

## 공통 부품

- 4px 간격 단위, 패널 안쪽 20–32px, 카드 간 16–20px.
- 버튼 모서리 8px, 카드 12px, 주요 패널 16px, 대화상자 20px.
- 기본 버튼 높이 44px, 보조 버튼 36px 이상. 서로 겹치지 않는 조작 영역과 뚜렷한 초점 표시.
- 패널은 얇은 경계와 약한 그림자. 큰 장식 효과와 반복 진입 애니메이션을 추가하지 않는다.
- 기본 HTML 입력과 기존 공통 컴포넌트를 재사용한다. 디자인만을 위한 라이브러리 교체는 하지 않는다.
- 수거 계획은 같은 `RoutePanel`을 메인과 관리자 화면에서 재사용한다.

## 반응형·접근성

- 1020px 이하: 사이드바를 닫힌 상태에서 숨기고, 키보드 초점을 관리하는 메뉴 대화상자로 연다.
- 760px 이하: 요약과 센서를 위아래로 배치한다. 480px 이하: 쓰레기통 카드를 한 열로 보여 준다.
- 대화상자는 배경을 비활성화하고 Tab 순환, Escape 닫기, 원래 버튼으로 초점 복귀를 지원한다.
- 지도 지점은 Enter·Space로 선택한다. 계산 방식은 기본 라디오 입력으로 방향키 이동을 지원한다.
- 동작 실패는 사라지는 알림 외에 지속되는 안내도 표시한다.
- 오래된 경로·미수신 값을 현재 값으로 표현하지 않는다.
- 사용자가 움직임 줄이기를 설정하면 전환·장식 애니메이션을 중지한다.

## 참고한 스킬

- [interface-design](https://github.com/Dammyjay93/interface-design/blob/main/.claude/skills/interface-design/SKILL.md): 정보 우선순위·공통 규칙.
- [state-sweep](https://github.com/Tranz007/ux-skills/blob/main/skills/state-sweep/SKILL.md): 상태 전환·복구.
- [fixing-accessibility](https://github.com/ibelick/ui-skills/blob/main/skills/fixing-accessibility/SKILL.md): 키보드·입력·초점.
- [frontend-design](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md): 제품에 맞는 시각 방향.

개별 스킬의 취향이나 수치를 그대로 적용하기보다 프로젝트 목적과 실제 화면 검증을 우선한다.
