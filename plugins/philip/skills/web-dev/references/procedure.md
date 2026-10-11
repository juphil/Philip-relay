---
description: 웹·UI 개발 지식 라우터 — 정보구조·시각체계·컴포넌트·반응형·접근성·시각 QA 문서를 선택한다
---
$ARGUMENTS에 필요한 웹·UI 지식을 선택해 적용한다. Philip Relay 공통 규칙은 작업 방식만 정하고, 제품별 치수·화면 구성은 프로젝트 프로필이나 외부 지식에서 가져온다.

1. 작업을 `information-architecture / visual-system / components-and-states / responsive / accessibility / visual-qa`로 분류한다.
2. [웹/UI 공통 매뉴얼](docs/06_web_ui_manual.md)과 [지식 연결 표준](docs/09_knowledge_system.md)을 읽는다.
3. `.psp/knowledge.sources.json`의 `web` source에서 `web/INDEX.md`를 거쳐 leaf 문서 1~3개만 고른다. `.psp/knowledge.lock.json`의 commit과 일치하지 않으면 적용을 멈추고 드리프트를 보고한다.
   - 레지스트리·lock·web source가 없으면 연결된 지식이 없다고 명시하고 `philip:init`의 지식 템플릿과 연결 항목을 안내한다. 승인되지 않은 최신 웹 자료를 자동 기본값으로 삼지 않는다.
4. 프로젝트에 UI 프로필이 있으면 그 프로필의 토큰·구성·상태를 우선한다. 다른 프로젝트의 등록 화면, 촬영 칸 수, 카메라 비율 같은 값을 공통 기본값으로 가져오지 않는다.
5. 레퍼런스는 `복제 목표 / 제약 / 영감 / 안티패턴` 중 어떤 모드인지 먼저 확정한다. 복제 목표일 때만 구조·값을 그대로 옮긴다.
6. 감사 요청은 `/philip:designcheck`, 수정까지 승인된 요청은 `/philip:designfix`로 분리한다.

**보고**: 선택한 분류 / source id·commit·leaf / 적용 프로필 / 레퍼런스 모드 / 감사와 수정 권한 범위 / 실측 근거.
