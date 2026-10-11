# Philip Relay

[English](README.md)


**Portable workflow, memory, and verification for coding agents.**

Philip Relay는 Claude Code와 Codex가 같은 프로젝트를 이어서 작업하도록 돕는 공개 플러그인입니다. 프로젝트 상태 회수, 장기 메모리, 완료 검증, UI 감사, 게임·웹·연구 지식 라우팅, 플러그인 업데이트 왜곡 감사를 한 흐름으로 연결합니다.

> 설치·사용법은 이 문서에서 영어와 한국어로 제공합니다. 스킬 절차와 기본 응답은 현재 한국어 중심이며, 저장소에는 개인 프로젝트의 코드·메모리·게임 지식이 포함되지 않습니다.

## 핵심 원칙

- 한 에이전트의 조사 → 계획 → 실행 → 검증을 기본으로 하고, 독립적인 하위 문제만 병렬화합니다.
- 시작할 때 모든 문서를 넣지 않고 현재 판단에 필요한 자료만 점진적으로 읽습니다.
- 검토 요청과 수정 요청을 구분하며, 자동 업데이트·자동 push·원격 문서의 명령 실행을 하지 않습니다.
- 게임·웹·연구 상세 지식은 별도 저장소에 두고 프로젝트가 승인한 불변 commit만 연결합니다.
- 새 전역 규칙은 적용 범위·반례·더 약한 대안·행동 평가를 통과해야 합니다.

## 설치

### Claude Code

Claude Code에서 다음 명령을 실행합니다.

```text
/plugin marketplace add juphil/Philip-relay
/plugin install philip@philip-relay
```

설치 뒤 새 세션을 열고 `/philip:init <프로젝트 목적>`을 실행합니다.

### Codex

Codex의 플러그인/마켓플레이스 화면에서 이 GitHub 저장소를 마켓플레이스로 추가한 뒤 `philip`을 설치합니다. CLI가 지원되는 버전에서는 다음 형식을 사용할 수 있습니다.

```text
codex plugin marketplace add juphil/Philip-relay
codex plugin add philip@philip-relay
```

설치 후 스킬 목록에서 `philip:init`, `philip:status`, `philip:done`이 보이는지 확인합니다. Codex 버전에 따라 플러그인 관리 UI나 명령 이름이 다르면 해당 버전의 플러그인 화면을 사용하십시오.

## 프로젝트 시작

새 프로젝트와 기존 프로젝트 모두 같은 명령으로 시작합니다.

```text
/philip:init 온라인 협동 게임 개발
```

`init`은 기존 파일을 덮어쓰는 설치기가 아니라, 규칙·todo·메모리·지식 연결을 각각 `완비/부분/없음`으로 판정하고 빠진 부분만 보강하는 멱등 절차입니다. 기존 프로젝트에서는 먼저 변경 범위를 보여 주며, 제품 방향이나 외부 저장소 주소를 추측하지 않습니다.

일상 흐름은 간단합니다.

```text
/philip:status          현재 상태와 정확한 재개 지점 회수
<자연어로 개발 요청>      관련 스킬이 의미에 따라 선택됨
/philip:done            검토·검증·todo·인계·메모리 마감
```

`메모리 업데이트해`, `현재 어디까지 했지?`, `정밀 검토해`처럼 의도가 분명한 자연어도 각각 `memory`, `status`, `check` 절차의 호출 신호입니다. 명시적으로 스킬 이름을 입력해야만 작동하는 구조는 아닙니다. 다만 호스트의 자동 선택 결과가 불확실하면 `/philip:memory`처럼 직접 지정할 수 있습니다.

## 포함된 스킬

| 스킬 | 용도 |
|---|---|
| `init` | 새·기존 프로젝트 운영 표준을 멱등 적용 |
| `status` | 최신 상태와 필요한 근거만 점진적으로 회수 |
| `done` | 정밀검토, 검증, todo, 로그, 메모리까지 완료 처리 |
| `memory` | 장기 결정과 작업 인계를 Claude·Codex 공용으로 갱신 |
| `check` | 현 작업 또는 전체 범위 정밀검토 |
| `prove` | 실행과 실측으로 주장 반증 |
| `replan` | 기존 계획을 보존하며 순서 변경 |
| `brief` | 해결·미해결·근거·다음 결정을 분리해 보고 |
| `git` | 백업 우선의 안전한 pull/push |
| `sync` | Git이 없는 환경의 이동식 매체 동기화 |
| `updatecheck` | 버전 신선도·규칙 왜곡·호환성·행동 평가 감사 |
| `claude` | Codex 프로젝트에 Claude 연결 |
| `codex` | Claude 프로젝트에 Codex 연결 |
| `game-dev` | 게임 설계·엔진·네트워크·검증 지식 라우팅 |
| `web-dev` | 정보구조·컴포넌트·반응형·접근성·시각 QA 라우팅 |
| `research` | 문헌·실험·UX·소프트웨어 R&D 지식 라우팅 |
| `researchnote` | 근거 중심 연구노트와 현황 보고서 작성 |
| `designpick` | 실제 화면 후보를 비교해 UI 방향 결정 |
| `designcheck` | 실제 렌더의 상태·치수·접근성 감사 |
| `designfix` | 승인된 UI 결함 수정과 재검증 |
| `diagram` | 프로젝트 구조를 인터랙티브 HTML로 시각화 |
| `exp` | CV·DL 실험 조건·수치·대장 기록 |
| `judge` | CV·DL 실험 실패 원인을 분리해 판정 |

## 구조와 개인 지식 분리

```text
Philip Relay                 별도 지식 저장소              각 프로젝트
행동·권한·검증·라우팅  →    game/web/research INDEX  →   적용 규칙·잠긴 commit·예외
```

플러그인은 행동 매뉴얼과 지식 연결 규격만 가집니다. 개인적인 게임 지식, 특정 웹 제품의 픽셀 값, 연구 프로젝트 기록은 공개 플러그인에 넣지 않습니다. 프로젝트는 `.psp/knowledge.sources.json`에서 승인한 저장소와 범위를 선언하고 `.psp/knowledge.lock.json`에 실제 commit을 고정합니다.

`.psp/`, `.psp-collections/`, `.claude/psp.config.json`, `psp_reviewed_version`은 기존 프로젝트와의 호환성을 위한 안정적인 내부 상태 스키마입니다. 공개 제품명과 명령 네임스페이스는 `Philip Relay`와 `philip:`입니다.

## 업데이트와 공개 배포

- `VERSION`과 매니페스트의 SemVer를 함께 올리고 `vX.Y.Z` 태그를 만듭니다.
- `philip:updatecheck plugin`으로 새 하드 규칙의 왜곡 가능성과 호스트별 행동을 감사합니다.
- 공개 배포 검사는 개인 경로·비공개 원격·프로젝트 메모리·비밀 파일이 섞이면 실패합니다.
- 설치된 프로젝트는 `.psp/runtime.json`의 `psp_reviewed_version`으로 마지막 호환성 검토 버전을 기록합니다. 버전 차이는 안내하지만 자동으로 플러그인이나 프로젝트를 변경하지 않습니다.

유지관리 절차는 [공개 승격 가이드](docs/maintainers/public-promotion.md)를 참고하십시오.

## 개발 및 검증

```powershell
python plugins/philip/tools/build_skills.py
python plugins/philip/tools/build_skills.py --check
python -m unittest discover -s plugins/philip/tools -p "test_*.py"
python tools/public_release_check.py
```

문제 제보는 재현 절차와 호스트(Claude Code/Codex), OS, 설치 버전을 포함해 주세요. 기여 방법은 [CONTRIBUTING.md](CONTRIBUTING.md), 보안 문제는 [SECURITY.md](SECURITY.md), 고지는 [NOTICE](NOTICE)와 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 따릅니다.

## 라이선스

Apache License 2.0. 자세한 내용은 [LICENSE](LICENSE)를 확인하십시오.
