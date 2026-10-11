---
description: "공유 git 표준(philip-relay)의 안전 동기화 — 스킬 내려받기(pull) / 내가 만든 스킬 반영·푸시(push). ★파괴적 git 전 반드시 백업, 이름충돌 자동덮어쓰기 금지(실측: reset --hard 가 이름겹친 untracked 를 경고없이 덮음·reflog복구불가). 인자 = pull | push(기본)"
---
$ARGUMENTS. **전제**: philip-relay(원본=github juphil/Philip-relay)는 여러 프로젝트가 공유. **이 명령을 부를 때 나는 이미 스킬을 만들어 로컬에 둔 상태일 수 있다** — 그 파일이 원격에도 **같은 이름**으로 있으면 `git reset --hard` 가 경고 없이 내 것을 원격 것으로 덮는다(실측 확인). ★불변 규칙 3: **①커밋·푸시 전 원격 먼저 통합 ②파괴적 git 전 무조건 백업 ③이름충돌은 자동 덮어쓰기 금지 → 병합/개명.**

**⛔작업 트리 보호(최우선, docs/08_destructive_ops.md)**: `git clean` 은 `-n` 미리보기만, `-x` 는 작업 트리에서 절대 금지(검증된 사고: 작업 트리에서 고아 브랜치를 만들며 `git clean -fdx`를 실행해 깃 밖 모델·결과·실험 원자료가 소실됨). **고아(orphan) 브랜치·다른 브랜치 전용 커밋은 임시 클론(`git clone <원격> %TEMP%\x`)이나 `git worktree add` 에서만** 만든다. 작업 트리 브랜치 전환 전 `git status --porcelain --ignored` 로 덮이거나 지워질 파일이 없는지 확인한다. 이 명령들은 psp 삭제 가드 훅이 차단한다.

**★로컬 수정 보호·버전·왜곡 감사 먼저(갱신·수정 전 매번)**: 플러그인 갱신이면 `python ${CLAUDE_PLUGIN_ROOT}/tools/update_preflight.py`를 먼저 실행한다. marketplace·설치 캐시 직접 수정이 있으면 도구가 로컬 백업하고 중단하므로 원본 반영 여부를 먼저 결정한다. 이어 `python ${CLAUDE_PLUGIN_ROOT}/tools/version_check.py`와 `/philip:updatecheck plugin`을 실행한다. 로컬·GitHub·설치본 버전뿐 아니라 새 하드 규칙의 적용 범위·반례, 프로젝트 프로필 누출, 감사/수정 권한, 호스트별 행동 사례를 검토한다. 로컬이 뒤처졌으면 pull부터다. 마켓플레이스 원본은 **GitHub(`juphil/Philip-relay`)**로 등록한다. **push 하는 변경은 SemVer 4곳과 `docs/update_reviews/vX.Y.Z.md`를 갱신하고 `vX.Y.Z` 태그를 함께 푸시**한다.

0. **★백업 먼저(파괴적 git 전 무조건)**: 로컬 변경·신규 전부를 타임스탬프 폴더(git 밖)로 복사 — `git status --porcelain` 대상 파일 + 내 로컬 커밋분. 이게 있어야 reset/merge 사고를 되돌린다(untracked 유실은 reflog 로 복구 불가하므로 이 백업이 유일한 안전망). 백업 없이 reset/checkout/merge 금지.

1. **fetch + 진단**: `git fetch origin` → `git log --oneline HEAD..origin/main`(원격이 앞섰나) · `git log --oneline origin/main..HEAD`(내 로컬 커밋) · `git status --short`(미커밋·신규).

2. **★이름 충돌 검사(핵심 — 유실 방지)**: 내 신규/수정 파일 각 경로가 **원격 트리에도 있나** — `git ls-tree -r --name-only origin/main` 와 대조.
   - **충돌 있음** → **reset/덮어쓰기 절대 금지.** 내 백업본 vs `git show origin/main:<경로>` 를 **비교**해 (a) 내용 병합하거나 (b) 내 것을 **새 이름**으로 바꾼다. 사람 확인 후에만 진행.
   - **충돌 없음** → 내 신규 파일은 아래 통합에서 보존됨(안전).

3. **통합(원격 먼저·비파괴 우선)**:
   - 원격만 앞서고 내 변경=미커밋·충돌없음 → `git stash` → `git merge --ff-only origin/main` → `git stash pop`.
   - 내 **로컬 커밋**이 있으면 → `git rebase origin/main` (★reset --hard 금지 = 커밋 유실).
   - `git reset --hard origin/main` 은 **오직** [백업 완료 + 충돌 없음 + 내 것 전부 untracked] 3조건 모두일 때만 허용.
   - 통합 후 **검증**: 백업과 `diff` 로 내 신규/수정 파일이 다 살아있나 확인.

4. **내 변경 얹기(push 모드)**: 원본 `procedures/`와 필요한 docs/tools/templates, `README`·`VERSION`·업데이트 감사 문서를 갱신하고 `tools/build_skills.py`로 공식 스킬 진입점을 생성한다. `tools/update_audit.py`와 관련 테스트를 실행한다. 행동 변경이면 Claude·Codex 결과를 각각 기록하고, 실행하지 못한 호스트는 미검증으로 남긴다. [공용 설치 절차](../docs/07_agent_bridge.md)에 따라 검증·설치한다. 프로젝트 `.claude/commands/`에 사본을 만들지 않는다. 커밋은 **내 파일만 명시 `git add`**한다.

5. **푸시 직전 재fetch(경합)**: 그 사이 원격 또 움직였으면 2로. 안 움직였으면 `git push origin main` → `git log --oneline origin/main -1` 로 반영 확인.

6. **pull 모드**: 0(백업)→1→2(충돌검사)→3(통합)→새 커맨드 설치·reload 까지. commit/push 안 함. 내가 만든 로컬 스킬이 원격과 충돌하면 2번대로 병합(그냥 덮지 않음).

**보고**: ①백업 위치 ②충돌 검사 결과 ③원격서 받은 것 ④내가 얹은 것 ⑤푸시·설치 ⑥되돌리기(백업+reflog). "백업 → 받고 → 충돌검사 → 얹고 → 재확인 → 푸시" 순서 지켰음을 명시.
