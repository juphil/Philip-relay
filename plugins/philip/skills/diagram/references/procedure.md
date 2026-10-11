---
description: 구조도 생성·갱신 — 프로젝트를 노드/간선 인터랙티브 HTML(살아있는 체크리스트)로. 인자 = 대상 폴더(기본 docs/구조도)
---
현재 프로젝트의 구조도를 만들거나 갱신하라. 규격·조작법 전문과 틀 6파일은 **이 플러그인에 동봉**: Philip Relay 플러그인 폴더(설치 캐시 `~/.claude/plugins/cache/philip-relay/philip/<버전>/` 또는 Philip Relay 로컬 클론의 `plugins/philip/`)의 `docs/04_diagram.md` · `templates/diagram/`.

0. **분기** — 대상 폴더(인자 없으면 `docs/구조도/`)에 이미 `index.html`+`data.js`가 있으면 **갱신 모드**(2~4만 수행), 없으면 신규.
1. **틀 복사(신규)** — 위 플러그인 폴더의 `templates/diagram/` 6파일을 프로젝트로 복사 → `index.html` ★표시 4곳(title·h1·상세영역 제목·footer) 프로젝트명으로 교체 → `app.js` 상단 `KEY`를 프로젝트 고유 문자열로(줌·배치 저장 키가 여기서 파생됨), 캔버스 크기(`W_TOP/H_TOP/W_DET/H_DET`)는 내용 규모 잡힌 뒤 조정.
2. **실물 조사(⛔추측 금지)** — 코드를 실제로 열어 지도를 잡는다: 진입점(외부→우리) / 코어(본체 로직) / 어댑터(입출력 얇은 층) / 저장소 / 외부 시스템 / 미확정(외부 대기). 노드의 `fl`(파일경로)·`tip` 내용은 **실파일·실함수만** — 문서·기억으로 채우지 마라.
3. **data.js 작성** — 전역 6개(GROUPS/NODES/EDGES/MSGS/FLOW_ACTS/DEFAULT_POS) 스키마대로(04 §4). 간선 포트는 자동(면당 슬롯 3개 분배)이며 손으로 고칠 땐 수정모드에서 간선 클릭 → 손잡이 클릭 → 배치 저장(`DEFAULT_PORTS`).
   - 상태색은 **실측으로만**: `s-done`(구현+검증 확인) · `s-todo`(미배선=작업 대상) · `s-field`(외부 확정 대기) · `s-ext`(외부) · `s-core`(코어). 검증 안 된 것을 초록으로 칠하지 마라.
   - 셋트 필수: 노드 `tip` + 간선 `desc`(그 링크가 하는 일 한 줄, 동사구) + 흐름 `rel`(간선은 **양 끝이 모두** rel에 있어야 강조됨) + `FLOW_ACTS`(흐름키 = MSGS item의 `k`와 동일).
   - 작성 규칙: 코드 기준 정확 · 대화체/꼬리괄호 금지 · 한 `<li>` 한 평서문 · 동그라미 숫자 금지 · 스키마 표는 실 규격 그대로.
4. **검증 — 전부 통과 전 완료 선언 금지**: `node --check` 양 파일 → 참조 무결성(04 §7 스크립트: EDGES/GROUPS/MSGS.rel/FLOW_ACTS id가 NODES에, NODES가 DEFAULT_POS에) → **브라우저 실측**(start.bat 또는 헤드리스: 렌더·흐름 강조 클릭·hover·JS 에러 0) → UI라서 `/philip:designcheck` 대상.
5. **보고** — 노드 수·색 분포(초록/빨강/노랑/회색)·**빨강 목록(=다음 작업 후보)** + 여는 법 1줄(start.bat 더블클릭).

⚠ 이후 운영: 기능이 완성·검증될 때마다 그 노드 빨강→초록 + 배지·tip·FLOW_ACTS 현행화 — 구조도는 시스템 지도 위의 구현 상태다(todo 표와 역할 분리: todo=순서·계획 SSOT, 구조도=지도).
