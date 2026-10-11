# 05 — Obsidian 메모리 연동 + 메모리 이식(portable)

## 메모리 이식 (다른 PC·서버로 클로드 맥락 들고 다니기)
클로드 메모리는 `~/.claude/projects/<프로젝트 절대경로 인코딩>/memory/`에 저장 = **머신·경로 종속**. 경로를 머신마다 통일할 수 있으면 그 폴더를 private git으로 동기화하면 끝. 통일 못 하면 **slug 랜딩** 방식:
- private 레포(★반드시 private) `claude-memory/`에 프로젝트별 `slug/` 폴더로 둔다(예: `my_project/`). `.md` + `.obsidian` 설정만(workspace.json·플러그인 바이너리 제외 — `.gitignore`).
- 각 머신은 `slug/` ↔ 그 머신의 로컬 메모리 폴더를 `tools/mem_sync.py`로 랜딩:
  - `push` = 로컬 → 레포(로컬 무변경=읽기전용, git commit; `--gitpush`로 원격까지). `/philip:memory` 6단계가 config에 `memory` 있으면 자동.
  - `pull` = 레포 → 로컬(★**로컬 먼저 백업** 후 반영). `/philip:init` 5단계가 새 머신에서 복원.
- ★**설정 최소화 — 머신에 기본 레포 한 번이면 끝**: `~/.claude/memory_repo.txt`(한 줄 = private 레포 URL)를 머신당 1회 두면, 그 머신의 **모든 프로젝트가 `/philip:memory` 시 자동 이식**(slug=프로젝트 루트 폴더명). 프로젝트별 수동 등록 불필요.
  - 프로젝트별 override가 필요하면(다른 레포·다른 slug) `.claude/psp.config.json`에 `"memory": { "url": "...", "slug": "..." }`(config가 머신 기본보다 우선). config는 프로젝트 코드와 함께 이동한다.
  - url 해결 = config.memory.url > `~/.claude/memory_repo.txt` / slug = config.memory.slug > 프로젝트 폴더명. 둘 다 없으면 이식 안 함(로컬만).
  - `mem_sync.py`도 프로젝트 루트에서 실행하면 같은 우선순위를 직접 적용한다. 단일 `memory_dirs`는 `--url --slug --memdir`을 생략할 수 있고, 여러 묶음만 `--memdir --collection`을 명시한다.
- ★**새 PC 부트스트랩(구멍 주의)**: `~/.claude/memory_repo.txt`·`machine.txt`는 **머신 로컬 = 새 PC엔 없다**. 그래서 새 PC에서 `/philip:init` 하면 url이 안 잡히는데, **init이 그때 사용자에게 레포 URL을 물어 `memory_repo.txt`에 1회 기록**(+머신 이름)한 뒤 clone+pull로 복원한다. 즉 새 PC에서도 `/philip:init` 한 번이면 스킬이 머신 셋업까지 해준다(사용자가 URL만 답). config.memory.url을 프로젝트 repo에 커밋해두면 그 프로젝트는 URL 질문 없이 바로 복원된다.
- ★**사용자는 git 안 친다 — 스킬이 clone/pull/push 대신 처리**: 로컬 클론(고정 `~/.claude/claude-memory`)이 없으면 mem_sync가 `--url`로 자동 clone. 사용법 = 스킬뿐:
  - 저장·공유: `/philip:memory` (저장 후 자동 push).
  - 새 머신 복원: `/philip:init` (로컬 비었으면 자동 clone+pull).
- 배포 서버 시나리오: 그 서버에 psp 플러그인 설치 후 프로젝트 열고 `/philip:init` → 스킬이 claude-memory clone + 그 머신 위치에 pull → 클로드가 과거 맥락 보유. (코드 없이 열람만이면 레포를 Obsidian으로 열어도 됨.)
- 주의: ①private 필수 ②원문 시크릿(키·비번) 금지 ③두 머신 동시편집=git 충돌(파일 단위라 드묾, philip:git 안전 flow) ④pull은 로컬 있으면 덮어쓰기 위험 → 비었을 때만/물어보고.

---

# Obsidian 연동 (그래프·링크 위생)

메모리 포맷(`[[name]]` 위키링크 + YAML frontmatter + 마크다운 · 파일명=슬러그=링크타깃)은 **Obsidian 네이티브와 동일**하다. 변환 없이 메모리 폴더를 볼트로 열면 링크망을 시각화·감사할 수 있다.

## 무엇이 좋아지나
- **그래프 뷰**: `[[]]` 링크망 시각화 — 고아(외딴점)·허브(지식중심)가 한눈에.
- **백링크**: forward `[[]]`만 쓰는 구조에 "무엇이 이걸 가리키나"를 자동 계산(양방향 공짜).
- **끊긴 링크 감지**: 존재하지 않는 `[[name]]`을 회색으로 표시 = philip:memory 의 "끊긴 링크 점검" 자동화.

## 한계 (정직)
- Obsidian은 **사람(큐레이터)용 도구**다. **클로드 런타임 회수는 여전히 `MEMORY.md`의 description 트리거에 의존** — 그래프가 회수를 좋게 하진 않는다(감사·유지보수·시각화가 좋아짐).
- Dataview 등 커뮤니티 플러그인 대시보드는 Obsidian 안에서만 렌더된다 → 클로드가 읽는 raw `MEMORY.md`를 대체하지 못한다(사람용 감사/생성기로만).

## psp 포맷 오염 방지 (필수)
- 볼트 설정 = `templates/obsidian/{app.json,core-plugins.json}` → `<메모리폴더>/.obsidian/`. `useMarkdownLinks:false`(위키링크 고정)·자동 프로퍼티 추가 안 함.
- `.obsidian/`는 `.json`이라 클로드 메모리(`*.md`) 스캔에 안 걸린다. 메모리 폴더가 git에 든다면 `.obsidian/workspace.json`은 제외.
- Obsidian이 파일 rename 시 `[[]]`를 자동 갱신(`alwaysUpdateLinks:true`) — 슬러그 일관 유지에 유리하나, 대량 변경은 인지하고 할 것.

## 링크 무결성 도구 (CLI)
그래프 없이 커맨드/CI 에서 감사:
```
python "${CLAUDE_PLUGIN_ROOT}/tools/mem_graph.py" <메모리폴더>
```
출력: 끊긴 링크(오타·미작성·문법예시) · 고아 노드 · 허브 top8. `/philip:memory` 5단계에서 링크를 건드렸을 때 실행한다.
주의: `[[X]]`를 문법 예시로 쓴 문서는 끊긴 링크로 잡힐 수 있다 — 사람이 판단.

## 볼트 여는 법
1. Obsidian 설치(머신당 1회): `winget install Obsidian.Obsidian`.
2. `/philip:init`의 (선택) Obsidian 연동으로 `.obsidian/` 설정 + 볼트 등록, 또는 앱에서 "폴더를 볼트로 열기" → 메모리 폴더 선택.
3. 왼쪽 그래프 아이콘 = 링크망. 회색 점 = 끊긴 링크, 외딴 점 = 고아.

## 추천 플러그인 (읽기전용 = 노트 무변경, 메모리 안전)
- **Dataview** (커뮤니티 최다급) — frontmatter를 쿼리. 우리 `metadata.type`·description으로 타입별 목록·고아·최근수정 대시보드. **노트를 수정하지 않음**(렌더만). `templates/obsidian/_DASHBOARD.md`가 준비된 대시보드.
- 설치(머신당 1회, 바이너리라 템플릿 불가): 릴리스 3파일을 볼트에 넣는다 —
  ```
  P="<메모리폴더>/.obsidian/plugins/dataview"; mkdir -p "$P"
  for f in main.js manifest.json styles.css; do
    curl -sL "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download/$f" -o "$P/$f"; done
  ```
  `templates/obsidian/community-plugins.json`(=`["dataview"]`)을 `.obsidian/`에 두면 활성. Obsidian에서 "커뮤니티 플러그인 켜기" 1회 + 리로드.
- **주의(psp 안전)**: 노트에 **frontmatter를 자동으로 쓰는 플러그인은 배제**(Breadcrumbs·Templater 등 = 스키마 오염). Dataview·Graph 계열 읽기전용만. 적용 전 메모리 폴더 백업 + 사후 md5 대조로 "변경 0" 검증하는 절차를 지킨다.
