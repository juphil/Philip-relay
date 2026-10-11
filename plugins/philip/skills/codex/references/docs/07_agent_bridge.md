# 클로드·코덱스 양방향 적용

`/philip:codex`는 클로드 프로젝트에 코덱스를, `/philip:claude`는 코덱스 프로젝트에 클로드를 추가한다. 기존 환경을 삭제하지 않는다. 코덱스에서는 스킬 선택기의 `philip:codex`·`philip:claude` 또는 같은 이름의 자연어 요청으로 사용한다. 터미널 슬래시 자동완성은 클라이언트에 따라 다르다.

## 적용
1. 실제 프로젝트, `CODEX_HOME`, `CLAUDE_CONFIG_DIR`를 확인한다. Orca 등의 별도 홈을 일반 홈으로 바꾸지 않는다.
2. 이 문서의 상위 두 단계인 `philip/`을 `<플러그인>`으로 사용한다. 훅을 실행하는 셸에서 `python`이 Python 3을 가리키는지 확인한다. 검증용 `verify_runtime.py`는 설치된 코덱스의 실험적 app-server API에 의존하므로 미지원 버전은 오류를 보고하고 업그레이드 후 재검증한다.
3. `python <플러그인>/tools/agent_bridge.py <codex|claude> --project <프로젝트>`는 읽기 전용 계획이다. 승인된 적용에는 `--apply`를 붙인다.
4. **CLAUDE.md 와 AGENTS.md 는 같은 내용을 유지하되 독립 변경을 버리지 않는다.** 한쪽을 편집한 PostToolUse 사건에서는 편집한 파일을 명시적 원본으로 삼고 반대편 기존 내용을 OS 로컬 Philip Relay 백업에 보존한 뒤 동기화한다. 세션 시작 때 두 파일이 다르면 수정 시각으로 승자를 고르지 않고 충돌만 알리며 어느 쪽도 쓰지 않는다. 사람이 두 파일을 따로 고쳤다면 내용을 검토해 병합한다.
4-1. 없는 대상 규칙은 원본 참조로 만든다. 클로드 진입점은 공식 `@AGENTS.md` 가져오기를 사용한다. 기존 규칙 본문은 보존하고 Philip Relay 관리 블록만 추가·갱신한다. 상위·하위 규칙도 확인하고 다른 프로젝트 내용을 섞지 않는다.
5. 메모리는 기존 연결 설정·명시 인자·클로드 프로젝트 메모리·프로젝트 memory·과거 claude/memory를 확인해 링크한다. 기존 메모리 위에 복원하거나 원격으로 자동 전송하지 않는다. `.psp/memory_inventory.md`에 하위 폴더까지 모든 마크다운 파일을 원본 링크와 해시로 기록하며, 기존 인덱스에서 빠진 파일도 포함한다. 양방향 재적용은 기존 memory_dirs·handoff_index·memory_collections를 보존한다. 별도 홈·과거 머신의 경로는 실제 위치를 확인해 `--memory`로 추가한다. 하위 독립 프로젝트의 메모리는 그 프로젝트에서 적용하며 임의로 합치지 않는다. 아직 저장하지 않은 대화 내용은 philip:memory로 인계 기록을 남긴다.
6. 계정 토큰·인증 파일·대화 DB·실행 중인 작업·승인 생략 설정은 복사하지 않는다. MCP·사용자 스킬은 목록과 의존성을 확인하고 요청 범위에서 별도 연결한다. 비밀값을 출력하지 않는다.
7. 코덱스 홈의 클로드 전용 Orca/Clawd 훅과 실행 파일이 없는 any-buddy만 백업 후 정리한다. 코덱스 훅과 다른 훅은 보존한다. 보호 훅을 끄거나 임의의 오류를 숨기지 않는다.
8. 한국어 규칙을 양쪽 프로젝트 진입점 및 세션·프롬프트 훅으로 상시 전달한다. 앱의 고정 버튼 문구 변경과 구분한다.

## 공용 설치
원본은 `philip-relay/plugins/philip/`. `python tools/build_skills.py`로 양쪽의 공식 `skills/<이름>/SKILL.md`와 skill-local `references/procedure.md`를 재생성한다. `procedures/`가 편집 SSOT이고 생성된 reference는 개별 스킬 이식 시에도 절차가 빠지지 않게 한다. 구 commands 폴더를 함께 노출하면 자동 이식 스킬이 중복 생성되므로 사용하지 않는다.
- **설치 원본은 GitHub(`juphil/Philip-relay`) 한 곳**이다. 클로드와 코덱스는 같은 플러그인 폴더(`plugins/philip/` — 스킬·절차·훅·도구 전부 공용)를 쓰고, 각 도구가 요구하는 매니페스트만 따로 있다(`.claude-plugin/plugin.json`·`.codex-plugin/plugin.json`). 두 매니페스트의 버전은 **같은 번호**(v2.9.0부터 `+codex` 꼬리 폐지 — 릴리스마다 번호가 올라가 캐시 갱신용 꼬리가 불필요).
- 코덱스: `codex plugin marketplace add juphil/Philip-relay` 후 `codex plugin add philip@philip-relay`. 갱신 = 먼저 `python <현재 Philip Relay>/tools/update_preflight.py` 통과 → `codex plugin marketplace upgrade philip-relay` → `codex plugin add philip@philip-relay`. `CODEX_HOME`이 따로 있는 실행 환경(Orca 등)은 그 홈에도 같은 순서로 한다.
- 클로드: `claude plugin marketplace add juphil/Philip-relay` 후 `claude plugin install philip@philip-relay --scope user`. 갱신 = 먼저 `python <현재 Philip Relay>/tools/update_preflight.py` 통과 → `claude plugin marketplace update philip-relay` → `claude plugin update philip@philip-relay` → 재시작. Windows에서 claude.ps1이 실행 정책으로 막히면 설치된 claude.cmd를 쓴다.
- **로컬 폴더를 마켓플레이스로 등록하거나 설치·marketplace 사본을 직접 편집하지 않는다.** 갱신 전 `update_preflight.py`가 직접 수정·추가·누락을 검사하고, 발견하면 로컬 백업 위치를 남긴 뒤 중단한다. 원본 반영 여부를 결정한 다음에만 갱신하며, 전후 `version_check.py`로 GitHub·설치본 버전을 대조한다.
- 원격 공유는 별도 승인된 커밋·푸시 후 반영한다. 로컬 적용만 하고 원격 배포 완료라고 말하지 않는다.
- 훅 신뢰는 하네스 정식 검토 절차로 처리한다. 신뢰 해시를 위조하거나 신뢰 검사 생략 옵션으로 우회하지 않는다.
- 설치한 훅 코드·정의를 검토하고 적용 승인을 받은 경우 `tools/verify_runtime.py --approve-reviewed-philip-hooks`로 런타임이 반환한 현재 해시를 공식 설정 API에 등록할 수 있다. Philip Relay 이외의 훅은 승인하지 않는다. 검토하지 않은 훅에 이 옵션을 쓰지 않는다.

## 검증
- 백업·JSON·원본 메모리 해시·규칙 보존·링크 검사, 양방향 적용과 재실행 변경 0 확인.
- 실제 셸에서 정상 편집·보호 파일·다중 패치·이동·상대 경로·한글 공백 경로 테스트. 정상 처리와 보호 차단 모두 종료 0이며, 차단은 JSON permissionDecision=deny로 검증한다. 파워셸 종료 코드·한글 인코딩 차이를 피한다.
- 세션의 메모리·todo·Philip Relay 설치/원격/프로젝트 검토 버전 출력, 규칙 변경·변경 시작·검토·완료 주장 사건 포인터, 설치된 24개 스킬 확인.
- 새 세션에서 훅 신뢰와 실제 이벤트를 확인하고 미검증 부분은 따로 보고한다.

## 채택 근거와 범위
| 결정 | 근거 |
|---|---|
| CLAUDE.md에서 AGENTS.md 가져오기 | [Anthropic 공식 메모리 안내](https://code.claude.com/docs/en/memory#import-additional-files)의 @AGENTS.md 예제 |
| 사용자 전역 기본값과 프로젝트 지침 분리 | [OpenAI 공식 AGENTS.md 안내](https://learn.chatgpt.com/docs/agent-configuration/agents-md)의 전역→프로젝트 로딩 순서 |
| SKILL.md 및 플러그인 이름공간 | [Anthropic 공식 스킬 안내](https://code.claude.com/docs/en/skills), [OpenAI 공식 이식 안내](https://developers.openai.com/plugins/guides/submit-claude-plugin) |
| 명시적 JSON 차단·추가 컨텍스트·훅 신뢰 | [OpenAI 공식 훅 규격](https://learn.chatgpt.com/docs/hooks), [Anthropic 공식 훅 규격](https://code.claude.com/docs/en/hooks) |

백업·읽기 전용 계획·반복 적용의 변경 0은 이 도구의 검증 가능한 운영 보장이다. 특정 업체의 의무 규정이라고 표현하지 않는다. 상시 한국어와 사건 기반 행동 포인터는 사용자 운영 선호이며 업계 공통 규정이 아니다. 다른 사용자 전체가 사용한다고 검증하지 않은 관행을 실무 표준이라고 단정하지 않는다.
