# Public Promotion Guide

Philip Relay is a curated public release, not a mirror of a private development repository.

1. Fix the private baseline commit and classify each changed file as reusable core, public-only packaging, personal knowledge/profile, project state, or private material.
2. Promote only reusable core into a clean temporary checkout. Keep public README, license, contribution, and security documents owned by this repository.
3. Keep real private identifiers in the private release policy. The public checker contains only generic secret, path, email, private-IP, link, orphan, duplicate, and generated-artifact checks.
4. Run `python tools/public_release_check.py`, unit tests, and a human diff review before a normal push. Do not auto-push.
5. Report the current tree separately from Git history. Removing data from HEAD does not remove it from prior commits or tags; history rewriting requires a separate destructive-operation review and explicit approval.

## 한국어

Philip Relay 공개 저장소는 개인 개발 저장소의 미러가 아닙니다. 공개 업데이트는 검토된 변경만 선별 승격하는 릴리스입니다.

## 경계

공개 가능:

- 범용 procedure, hook, template, test, 행동 평가
- 출처와 적용 조건이 분명한 일반 문서
- 공개 설치·기여·보안·릴리스 문서

공개 금지:

- 개인 프로젝트 코드, todo, memory, 프로필, 화면 수치, 내부 경로
- 비공개 원격 주소, 토큰, 계정·장치 정보
- 라이선스와 출처를 확인하지 않은 지식·자산
- 생성 캐시, 로컬 설치본, 백업 파일

## 승격 순서

1. 개인 개발 쪽에서 공개 후보 commit 범위와 변경 파일을 고정합니다.
2. 각 파일을 `범용 코어 / 별도 지식 / 프로젝트 전용 / 비공개`로 분류합니다.
3. 범용 코어만 깨끗한 임시 작업 트리에 적용합니다. 저장소 전체 복사나 자동 미러링은 사용하지 않습니다.
4. 명령 네임스페이스, 공개 원격 주소, 버전, 라이선스를 공개 기준으로 변환합니다.
5. `python tools/public_release_check.py`와 README의 전체 검증을 실행합니다.
6. 변경 diff를 사람이 다시 읽고, SemVer와 업데이트 감사 문서를 확정합니다.
7. 일반 push 후 GitHub 원격 commit과 태그를 재확인합니다. 강제 push는 사용하지 않습니다.

개인 개발 저장소를 업데이트했다고 공개본이 자동 변경되지는 않습니다. 이 비대칭이 개인 지식 유출을 막는 안전 경계입니다.
