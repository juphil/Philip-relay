# 04 — 구조도 만들기 (인터랙티브 시스템 다이어그램)

> **무엇**: 시스템을 노드/간선 캔버스로 보는 인터랙티브 HTML 도구의 표준 틀. 외부 의존 0(브라우저+선택적 Python 표준라이브러리).
> **왜**: 프로젝트를 이해하는 가장 빠른 진입점이자, 노드 색이 구현 상태를 나타내는 **살아있는 체크리스트** — 문서가 아니라 작업 지도.
> **검증 범위**: 실제 다중 노드 시스템 구조도에서 검증한 엔진을 범용 템플릿(`templates/diagram/`)으로 제공한다.

---

## 1. 핵심 개념 — 구조도 = 살아있는 체크리스트 (운영 루프)

노드 색 = 구현 상태. **목표 = (외부 협의 제외) 전부 초록.** 작업은 구조도가 정한다:

1. **다음 할 일 선정** = 빨강(`s-todo`) 중 지금 할 수 있는 것 하나 (노랑=외부 대기라 대상 아님, 회색=범위 밖)
2. **구현** → 3. **검증**(실동작, 문법만 X) → 4. **구조도 갱신** = 그 노드 빨강→초록(+배지·tip 현행화), 간선 `todo` 제거, `FLOW_ACTS` 행동 갱신 → 5. **동기화+log** → 1로.

| 상태색 | 클래스 | 의미 |
|---|---|---|
| 초록 | `s-done` | 구현·검증 완료 |
| 빨강 | `s-todo` | 미구현·미배선 = **우리 작업 대상** |
| 노랑 | `s-field` | 외부 협의·설정값 확정 대기 |
| 회색 | `s-ext` | 외부 시스템 (범위 밖) |
| 파랑 | `s-core` | 코어 (프로젝트 본체) |

## 2. 틀 구성 (`templates/diagram/` — 복사할 실물)

| 파일 | 역할 | 수정 빈도 |
|---|---|---|
| **`data.js`** | **노드·간선·전문 내용 — 수정은 보통 여기만** | 자주 |
| `index.html` | 뼈대. 새 프로젝트 시 제목·범례·footer만 교체 | 최초 1회 |
| `app.js` | 엔진(렌더·드래그·간선 회피곡선·툴팁·줌/팬·강조) | 거의 안 함 |
| `style.css` | 스타일 | 가끔 |
| `serve.py`+`start.bat` | 로컬 서버 — "배치 저장"이 data.js에 직접 반영되게 함 | 안 함 |

**가장 빠른 길 = `/philip:diagram` 커맨드** — 틀 복사부터 코드 실물 조사·data.js 작성·검증까지 이 문서 규칙대로 실행한다. 수동 절차:
1. `templates/diagram/` 폴더를 프로젝트에 복사 (예: `docs/구조도/`)
2. `index.html` — `<title>`·`<h1>`·상세영역 제목(`.stitle`)·footer 교체 (★주석에 표시돼 있음)
3. `app.js` 상단 2곳 — 캔버스 크기 `W_TOP/H_TOP/W_DET/H_DET`(내용 규모에 맞게), `KEY`(프로젝트 고유 문자열)
4. `data.js` — 스타터 예제를 실제 시스템으로 교체 (아래 스키마)
5. 검증(§7) 후 `start.bat` 더블클릭

## 3. 여는 법 (두 가지 — 차이 중요)

- **`start.bat` 더블클릭 (권장)** — 로컬 서버(`serve.py`, 8770)로 열림. **"배치 저장" 버튼이 선택창 없이 그 폴더 `data.js`의 `DEFAULT_POS`에 직접 저장**(어느 PC든 동일). 끄기 = 콘솔 창 닫기.
- `index.html` 더블클릭 — 서버 없이 보기만(file://). 배치 저장 불가(내보내기로 폴백), 드래그는 그 브라우저 localStorage에만.
- ★드래그 자동저장(localStorage)은 **그 브라우저에만** 남는다 — 파일에 굳히려면 반드시 **배치 저장** 버튼.
- ★서버 포트는 8770 고정 — 구조도 두 개를 동시에 띄우려면 한쪽 `serve.py`의 `PORT`를 바꿀 것. 저장 키는 `KEY` 파생(`KEY_view`·`KEY_detH`)이라 프로젝트마다 `KEY`만 바꾸면 브라우저 저장 충돌 없음.

## 4. 데이터 스키마 (`data.js` 전역 6개 + 선택 1개 — 이름 고정, app.js가 참조)

- **GROUPS** — 묶음 박스. `{id, title, cls, members:[노드id…]}`. `cls`: `g-mgr/g-pool/g-core/g-out/g-store/g-field/g-algo`(테두리색), `''` 가능. 큰 박스가 다른 그룹들을 감쌀 땐 members에 안쪽 노드 전부 + `pad`/`padTop`으로 여백.
- **NODES** — `{id, stage, x, y, w, h, st, cat, ttl, bdg, sum, fl, tip}`
  - `stage`: `'top'`(위 전체구조) / `'detail'`(아래 확대 영역)
  - `st` 상태색(§1) · `cat` 박스 위 카테고리 · `ttl` 제목 · `bdg` 우상단 배지 · `sum` 한 줄 요약 · `fl` 파일경로 · `tip` 호버 팝업 HTML
  - `tip` 형식: `<h4>제목</h4><div class="file">파일</div><ul><li>…</li></ul>`
- **EDGES** — `[from, to, 라벨, kind, desc]` (5원소). `kind`: `''` 실선(흐름 점 애니메이션) / `'todo'` 빨강 점선 / `'back'` 파랑 점선(회신). `desc` = **그 링크가 하는 일 한 줄**(hover 시 뜸, 코드 기준 동사구).
- **MSGS** — 우측 리스트. `[{g:'그룹 제목', items:[{k, nm, fn, st, rel, tip}]}]`. `st`: `done/warn/todo/ext`. **클릭 = `rel` 노드·간선만 강조**(흐름 하이라이트).
- **FLOW_ACTS** — `{흐름키:{노드id:'그 흐름에서 이 노드가 하는 행동'}}`. 강조 중 노드 hover에 뜸.
- **DEFAULT_POS** — 파일 기본 배치 좌표(전 노드 필수). "배치 저장" 버튼이 이걸 덮어씀.
- **DEFAULT_PORTS**(선택) — 간선 포트 수동 지정. `{"from>to#n": {a:'R0', b:'L2'}}`. 키 = `from>to#n`(같은 from→to 간선이 여럿이면 n = 0,1,…), `a`/`b` = 출발/도착 끝의 포트, 포트 = 면(`L/R/T/B`) + 슬롯(`0/1/2`, 1 = 중앙). 없으면 전부 자동. "배치 저장"이 이것도 덮어씀(줄이 없던 data.js 에는 자동 추가).

## 5. 상호작용 (작성 시 이 동작에 맞춰 셋을 다 채울 것)

우측 리스트 클릭 = 흐름 강조 → `rel` 노드 + **양 끝이 모두 rel에 포함된 간선**만 밝음. 해제 = 같은 항목 재클릭 또는 리스트 상단 **"전체"** 버튼. 리스트 항목 `st` 배지: `done`=✓ · `warn`=부분 · `todo`=미배선 · `ext`=범위밖(**ext는 클릭 불가**). ★`FLOW_ACTS`의 흐름키는 MSGS item의 `k`와 동일해야 연결된다. **강조 전/후 hover가 달라진다**:

| 대상 hover | 평소 | 강조 중 |
|---|---|---|
| 노드 | `tip`(전체 상세) | `FLOW_ACTS[키][노드id]`(그 흐름에서의 행동). 흐름 밖 노드는 안 뜸 |
| 링크 | 간선 `desc` | 흐름명 + `desc`. 흐름 밖 링크는 안 뜸 |

→ **노드엔 `tip`(+흐름 참여 시 `FLOW_ACTS`), 간선엔 `desc`, 흐름(MSGS)엔 `rel`** — 셋 다 채워야 자연스럽다.

조작 요약: 호버=상세 팝업(1초 유지, 팝업 위로 이동 가능) · **수정** 버튼=드래그 이동(놓을 때 localStorage 자동저장) · **수정 모드에서 간선 클릭 = 포트 지정**(양 끝 노드에 면당 3개 손잡이 12개씩 표시, 클릭한 손잡이로 그 끝이 고정. 노란 점 = 고정된 포트, 회색 점 = 지금 자동 배정된 포트. 간선 가운데 **자동** 클릭 = 지정 해제. 목적 노드는 바뀌지 않음. 빈 곳 클릭 = 선택 해제) · 휠=커서 기준 줌 · **휠클릭 드래그=팬** · 수정모드에서 가운데 바 드래그=상하 영역 비율 · **상세 접기** · **원본 복원**(내 편집 삭제→DEFAULT_POS) · **배치 저장**(파일에 굳힘) · **배치 내보내기**(JSON 백업).

## 6. 내용 작성 규칙

1. **코드 기준 정확히** — 실제 동작만, 추측·과장 금지. 파일경로는 실파일과 일치.
2. 대화체·꼬리설명 금지 (`— 부연`, 끝 꼬리 괄호 금지. 인라인 괄호는 허용)
3. 한 `<li>` = 한 평서문 · 동그라미 숫자(①) 금지 → 1·2·3
4. 전문/DB 스키마 = **실 규격 문서 그대로** (필드·타입·크기 추측 금지)
5. 스키마 표는 `<table>`: `<tr><th>필드</th><th>타입</th><th>크기</th><th>설명</th></tr>` + 필드명 `<td class="k">`. 부연은 표 아래 `<div class="file">` 한 줄.

## 7. 추가·수정 절차 + 검증 (수정 후 매번)

새 항목: NODES 추가 → GROUPS members에 id → DEFAULT_POS에 좌표 → EDGES(양끝 실존 id) → 필요시 MSGS rel/tip·FLOW_ACTS → 검증 → 새로고침.

```bash
# (Git Bash 기준 — PowerShell 에선 따옴표가 깨지니 bash 로 실행)
node --check data.js && node --check app.js     # 문법
# 참조 무결성 — EDGES/GROUPS/MSGS.rel/FLOW_ACTS 의 id 가 NODES 에, NODES 가 DEFAULT_POS 에
node -e "const fs=require('fs');eval(fs.readFileSync('data.js','utf8').replace(/^const /gm,'var '));
let bad=[];const ids=new Set(NODES.map(n=>n.id));
EDGES.forEach(e=>{if(!ids.has(e[0])||!ids.has(e[1]))bad.push('EDGE '+e[0]+'->'+e[1])});
GROUPS.forEach(g=>g.members.forEach(m=>{if(!ids.has(m))bad.push('GROUP '+m)}));
MSGS.forEach(g=>g.items.forEach(it=>(it.rel||[]).forEach(r=>{if(!ids.has(r))bad.push('MSG '+it.k+' '+r)})));
NODES.forEach(n=>{if(!DEFAULT_POS[n.id])bad.push('POS '+n.id)});
Object.keys(FLOW_ACTS).forEach(k=>Object.keys(FLOW_ACTS[k]).forEach(id=>{if(!ids.has(id))bad.push('ACT '+id)}));
console.log(bad.length?bad.join('\n'):'OK');process.exit(bad.length?1:0)"
```

완성 선언 전 = 브라우저 실측(렌더·강조 클릭·hover·todo 점선) — `/philip:designcheck` 대상.

## 8. 엔진 메모 (app.js — 보통 안 건드림)

- 간선: 노드 4변 × **면당 슬롯 3개**(25%·50%·75%) 포트. 1단계 면 선택 = 다른 노드 회피·최단(수동 지정 면은 고정), 2단계 슬롯 분배 = 같은 노드 같은 면에 모인 간선을 상대 끝점 위치 순으로 슬롯에 나눠 겹침·교차 회피(1개면 중앙, 2개면 양끝, 3개면 셋 다, 4개 이상은 겹칠 수 있음). 수동 포트(`PORTS`, data.js `DEFAULT_PORTS` + localStorage `KEY_ports`)는 그대로 쓰고 자동 배정에서 그 슬롯을 비운다. 실선=흐르는 점, 점선(todo/back)=점선 자체가 흐름.
- 정렬 스냅: 같은 그룹 노드끼리 x/y 12px 이내 자동 정렬. `fit()` 캔버스 자동 축소.
- 줌·팬·영역구분선·줌상태저장·툴팁 줌일치는 엔진에 포함한다. **"공유용 저장"(배치를 포함한 단일 HTML)은 미포함**이며 필요하면 별도 내보내기 기능으로 구현한다.

## 9. 검증 이력 (이 템플릿)

2026-09-23: 면당 슬롯 3개·자동 분배·수정모드 간선 클릭 포트 지정 추가. 헤드리스(Chrome) 실측: 템플릿(노드 7·간선 5) 같은 면 슬롯 겹침 0, 손잡이 24개 표시, 클릭 → `PORTS` 반영 → 배치 저장 → `data.js` `DEFAULT_PORTS` 기록 → 새로고침 복원, JS 에러 0(favicon 404만). 다중 노드 구조도에서도 동일 검증.
2026-07-06: `node --check` + 참조 무결성 OK + **헤드리스 브라우저 실측**(serve 기동 → 노드 7·그룹 4·간선·우측리스트 렌더, 흐름 강조 클릭 동작, JS 에러 0, 스크린샷 눈 확인). 정밀검토 후 저장 키를 `KEY` 파생으로 교체(프로젝트 간 줌 상태 충돌 제거) — 휠 줌 후 `KEY_view` 저장 실측 재확인.
