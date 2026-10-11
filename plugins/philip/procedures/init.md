---
description: 새·기존 프로젝트에 Philip Relay 운영 표준과 버전·지식 연결 기준을 멱등 적용한다. 인자 = 프로젝트 목적
---
이 프로젝트를 Philip Relay 운영 표준에 **맞춘다(reconcile)**. 순서 고정, 각 단계 끝에 1줄 보고.
★**빈 프로젝트 부트스트랩만이 아니라, 이미 일부 적용된 프로젝트에서 "빠진 부분만 채우는" idempotent 재조정 커맨드다.** 각 구성요소(CLAUDE.md·config·todo·메모리·Obsidian)를 **있음/없음/부분** 3판정해서, **완비된 것은 손대지 말고 빠졌거나 반쯤 된 것만** 적용한다. 재실행해도 안전(멱등). **덮어쓰기 금지** — 이미 있는 파일은 건드리지 말고 소급 경로(§6)로.
예: Philip Relay 스캐폴딩은 다 있는데 Obsidian만 안 됐으면 → §5 Obsidian만 적용하고 나머지는 "이미 완비" 보고.

템플릿은 이 플러그인 안에 있다(클론 불필요): `${CLAUDE_PLUGIN_ROOT}/templates/`. 여기서 읽어 프로젝트에 쓴다.
- `templates/CLAUDE.md.template` · `templates/todo/{roadmap,milestone_index,phase,_inbox}.md.template` · `templates/memory/{MEMORY.md,memory_file.template}.md` · `templates/knowledge/{sources,lock}.json.template` · `templates/hooks/settings.hooks.json`
경로가 안 잡히면 `claude plugin list`로 `philip` 설치를 확인하고, 그래도 없으면 레포(https://github.com/juphil/Philip-relay)의 `plugins/philip/templates/`를 참조한다.

## 0. 파악 + 표준 완비 진단 (빠진 것만 채우기 위한 사전 스캔)
- **프로젝트 목적**을 확보한다(커맨드 인자로 왔으면 그걸로, 없으면 이것만 물어라 — 유일한 필수 질문. **단, 목적 파일이 이미 서 있으면 재확인 생략**).
- 세션의 `[Philip Relay 버전]`을 확인한다. 설치본이 원격과 다르면 자동 갱신하지 말고 `/philip:updatecheck project` 결과와 마이그레이션 영향을 먼저 알린다.
- **도메인 라우터 판정**(복수 가능): Game / Web / Research. 엔진·프레임워크 추가 팩(Unity, CV·DL 등)은 별도로 판정한다.
- ★**완비 진단 — 각 구성요소를 있음/없음/부분으로 판정**하고, 이후 단계에서 **빠진 것만** 손댄다(있는 건 "이미 완비"로 스킵 보고):
  | 구성요소 | 확인 대상 | 판정 |
  |---|---|---|
  | CLAUDE.md | 루트 `CLAUDE.md` 존재·슬롯 채워짐 | §1 |
  | config | `.claude/psp.config.json`(guard+roadmap) | §2 |
  | 훅 배선 | `.claude/settings.json`에 hooks 병합됨 | §3 |
  | todo | `todo/roadmap.md`(+ m1 index) | §4 |
  | 메모리 | 메모리 루트 `MEMORY.md`(+ project_overview) | §5 |
  | 지식 연결 | `.psp/knowledge.sources.json`·`knowledge.lock.json` | §5-1 |
  | Philip Relay 호환성 | `.psp/runtime.json`의 `psp_reviewed_version` | §7 |
  | Obsidian(선택) | `<메모리폴더>/.obsidian/app.json`·Dataview 설치·볼트 등록 | §5 하단 |
- 이미 있는 것은 **생성 대신** §6 소급 경로(마이그레이션)로 보정만.

## 1. CLAUDE.md
- 없을 때만: `templates/CLAUDE.md.template` → 루트 `CLAUDE.md`.
- `<슬롯>` 채움: 프로젝트명·정체성·불가침 1~2개(목적에서 도출해 **사용자 1회 확인**)·**용어 고정 3~5개 초안**·버전.
- 팩 정리: 공통 코어는 그대로, 엔진·실험 추가 팩은 해당하는 것만 남긴다. 상세 지식은 본문에 복사하지 않고 `/philip:game-dev`, `/philip:web-dev`, `/philip:research`로 연결한다.
- ~90줄 넘으면 잘못 넣은 것 — 절차성 내용은 커맨드로 뺀다.

## 2. 플러그인 연동 (config)
- `philip` 플러그인은 이미 이 커맨드가 도는 시점에 설치돼 있다(그래서 `/philip:init`이 떴다). **커맨드·훅 파일 복사 안 한다.**
- 미설치 안내가 필요하면: `/plugin marketplace add juphil/Philip-relay` → `/plugin install philip@philip-relay`(user 스코프).
- 프로젝트에 **`.claude/psp.config.json`** 생성(없을 때만):
  `{ "guard": { "protect": [<도메인 팩 + 프로젝트 고유 보호 목록>], "allow": [] }, "roadmap": "todo/roadmap.md" }`
  - 도메인 팩 보호 예: CV·DL = `datasets/*`·`dataset/*`·`checkpoints/*`·`*.ckpt`·`*.pt` / Unity = 씬·에셋 경로. 이력 보관 `*_KEEP/*`는 엔진 기본 보호.
  - 오프라인(폐쇄망·git 없음) 프로젝트면 `"sync_root"` 추가하고 `/philip:sync` 사용.
- CLAUDE.md의 커맨드 표기는 `/philip:status` 네임스페이스로.

## 3. 훅 (설정 병합) — ⛔**플러그인 경로면 이 단계는 하지 않는다**
- 플러그인이 `hooks/hooks.json`으로 보호·삭제 가드·세션·사건 기반 포인터·규칙 동기 훅을 **이미 자동 배선**한다. 프로젝트 `.claude/settings.json`에 아무것도 넣지 않는 것이 정상이다.
- `templates/hooks/settings.hooks.json`은 **구방식(폐쇄망 등 플러그인 못 쓰는 환경) 전용**이다. 이 템플릿은 `.claude/hooks/*.py` 사본을 가리키므로, 플러그인 프로젝트에 그대로 병합하면 **없는 py를 실행하려다 모든 Edit이 막힌다**(과거 호환성 실측에서 확인). 구방식 복사(§2 하단)를 실제로 한 경우에만 병합한다.
- python 없으면 훅 자체가 생략됨을 사용자에게 알림(나머지 정상 — 훅은 강화 장치).

## 4. todo
- 없을 때만: `templates/todo/roadmap.md.template` → `todo/roadmap.md`. 목적을 **마일스톤 3~7개**로 초안(표 행만, 각 1줄).
- **m1만** 폴더 생성(`milestone_index.md.template` → `todo/m1_*/index.md` 스텁 + `phase.md.template`로 phase1 한 개). 나머지 마일스톤은 행만(집만 짓기).
- `_inbox.md.template` → `todo/_inbox.md`.
- 마일스톤 초안은 사용자에게 보여 **확인 1회**(순서·이름).

## 5. 메모리
- 메모리 루트 확인(하네스 자동 메모리 경로가 있으면 그것, 없으면 `memory/` 생성).
- ★**메모리 이식 pull(다른 PC서 같은 프로젝트 시작 대비 — 새 머신 부트스트랩 포함)**: url·slug를 §6과 같이 **자동 해결**(url=config.memory.url > 머신 기본 `~/.claude/memory_repo.txt` / slug=config.memory.slug > 프로젝트 루트 폴더명).
  - ★**새 머신 부트스트랩(핵심 — 이 파일은 머신 로컬이라 새 PC엔 없음)**: url이 **둘 다 없으면**, 사용자에게 "이 머신에 메모리 이식 레포 URL을 등록할까요?"를 **묻는다**. 주면 `~/.claude/memory_repo.txt`에 그 URL 한 줄을 쓴다(이 머신 1회 셋업 → 이후 이 머신 **모든 프로젝트** 자동 이식). 겸사 `~/.claude/machine.txt`에 이 머신 이름도 물어 저장(push 출처 태그용). 사용자가 원치 않으면 로컬만.
  - url 해결되고 **로컬 메모리가 비었으면**(새 머신) 레포에 그 slug가 있으면 복원 — `python "${CLAUDE_PLUGIN_ROOT}/tools/mem_sync.py" pull --url <url> --slug <slug> --memdir <메모리폴더>` (레포 경로 기본값 = `<USERPROFILE>/.claude/claude-memory`, `--repo ~/...` 금지 — 과거 호환성 실측). 레포 클론 없으면 **url로 자동 clone**, pull은 **로컬 먼저 백업** 후 반영. 로컬에 이미 메모리 있으면 pull 강행 금지(덮어쓰기 위험) → 물어라. 복원되면 아래 생성 단계 스킵.
- (신규 프로젝트만) 없을 때: `templates/memory/MEMORY.md.template` → 루트 `MEMORY.md`.
- (신규 프로젝트만) `project_overview.md` 1개 생성(정체성·불가침·포인터 — 목적 기반, **상태 서술 금지**). 형식은 `templates/memory/memory_file.template.md`.
- **(선택) Obsidian 연동 — 빠진 부분만 채운다(부분 적용)**: 사용자가 원하면(또는 이미 일부 연동돼 있으면) 아래를 **각각 확인해 없는 것만** 적용한다. **먼저 메모리 폴더 백업 + md5 기록**(잃는 메모리 0 원칙, 이 절 전체의 전제).
  1. `<메모리폴더>/.obsidian/app.json`·`core-plugins.json` 없으면 → `templates/obsidian/`에서 복사(위키링크 고정·자동프로퍼티 오염 방지).
  2. `.obsidian/community-plugins.json` 없으면 → 템플릿(`["dataview"]`) 복사.
  3. `.obsidian/plugins/dataview/main.js` 없으면 → 05 절차로 릴리스 3파일 설치(노트 무변경 읽기전용).
  4. 볼트루트에 `_DASHBOARD.md` 없으면 → 템플릿 복사.
  5. `~/AppData/Roaming/obsidian/obsidian.json`에 이 경로 볼트 미등록이면 → 추가(id=랜덤hex, 기존 vaults 보존).
  - 다 되어 있으면 "Obsidian 이미 완비"로 스킵. 끝나면 **md5 대조로 기존 메모리 변경 0 검증** 후 보고. `[[name]]` 네이티브 해석 → 그래프·백링크·끊긴링크. 링크 무결성은 `tools/mem_graph.py`로도 점검. 규격 [05](../docs/05_obsidian.md).
  - ★frontmatter를 자동으로 쓰는 플러그인(Breadcrumbs·Templater 등)은 배제 — 프로젝트 메모리 스키마 오염.

## 5-1. 외부 지식 연결
- Game/Web/Research 중 하나라도 쓰면, 파일이 없을 때만 `templates/knowledge/sources.json.template`과 `lock.json.template`을 `.psp/knowledge.sources.json`·`.psp/knowledge.lock.json`으로 복사한다.
- 실제 저장소 주소를 추측해 채우지 않는다. 사용자가 승인한 source를 `docs/09_knowledge_system.md` 규격으로 등록한다.
- 구조 검사는 `python "${CLAUDE_PLUGIN_ROOT}/tools/knowledge_check.py" .psp/knowledge.sources.json`. 원격 ref 해석과 lock 작성은 지식 연결·갱신이 승인된 경우에만 한다.

## 6. (기존 프로젝트 소급일 때만) 마이그레이션
- 기존 CLAUDE.md: 하드 규칙 기준 압축 — 잘려나가는 절차 규칙은 해당 커맨드에 있는지 대조, 없으면 그 커맨드에 편입. 원본은 루트 `workbench_records_KEEP/`에 보존.
- todo: **현행 마일스톤만** 새 양식으로(상태=index 표 단일화). 과거 문서는 안 건드림.
- 메모리: 인덱스 각 줄에 회수 트리거("…물을 때") 없으면 보강. 진행 상태 서술은 todo 포인터로 교체.

## 7. 검증 (완료 선언 전 필수 — 문제 발견 시 그 자리에서 교정)
- `/philip:check 전체` 1회 — 깨진 링크·슬롯 미기입·중복 서술을 보고한다. init 범위의 결함은 이 요청의 적용 권한 안에서 고치고 재검사한다.
- **스킬 인식**: `/philip:` 23종이 보이는지 확인한다. 숫자만 믿지 말고 실제 이름 목록을 생성된 procedures와 대조한다.
- **python 확인**: 없으면 훅 생략됐음을 보고.
- **훅 실동작**: 보호 파일 차단, SessionStart의 `[Philip Relay 버전]`, 규칙 변경 시 사건 기반 포인터를 확인한다.
- 지식 레지스트리 구조와 잠긴 ref를 확인한다. 실제 프로젝트 호환성 검토가 끝난 뒤 `.psp/runtime.json`의 기존 필드를 보존하며 `psp_reviewed_version`·`psp_reviewed_at`을 기록한다.
- 사용자 보고: 만든 것 목록 / 확인해볼 것(훅 차단·세션 주입·커맨드 인식) / 첫 작업 제안.

## 이후 일상 (사용자에게 알려줄 것)
- 새 세션·상태 = **/philip:status**. 작업 끝 = **/philip:done** · 계획 변경 = **/philip:replan** · 코드 감사 = **/philip:check** · 사실 확인 = **/philip:prove** · UI 감사/수정 = **/philip:designcheck** / **/philip:designfix** · 지식 = **/philip:game-dev**·**/philip:web-dev**·**/philip:research** · 업데이트 = **/philip:updatecheck** · CV·DL 실험 = **/philip:judge**·**/philip:exp** · 기억 = **/philip:memory**.
- 떠오른 것은 `todo/_inbox.md`에 한 줄. 이력 보존물은 `workbench_records_KEEP/` 한 곳.
- 같은 잔소리 두 번 = "커맨드로 만들어" 한 번.
- **개선 규약**: 커맨드·훅·템플릿 개선은 `/philip:updatecheck plugin`의 왜곡·행동평가 감사를 거쳐 원본 레포에 반영한다. VERSION 증가와 배포는 별도 승인 범위대로 수행하며 프로젝트 로컬 사본은 만들지 않는다.
