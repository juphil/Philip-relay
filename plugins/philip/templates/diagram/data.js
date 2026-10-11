/* 구조도 데이터 (내용 수정은 이 파일만) — 아래는 스키마 시연용 미니 예제.
   새 프로젝트: 이 예제를 지우고 실제 시스템으로 교체. 규칙 = philip-relay/04_diagram.md
   전역 6개(GROUPS·NODES·EDGES·MSGS·FLOW_ACTS·DEFAULT_POS)+선택 DEFAULT_PORTS 는 이름 그대로 유지 — app.js 가 참조. */

const GROUPS = [
  // {id, title, cls, members:[노드id…]}  cls: g-mgr/g-pool/g-core/g-out/g-store/g-field/g-algo(테두리색), '' 가능
  {id:'g_in',   title:'입력 · 외부', cls:'',       members:['ext_src','client']},
  {id:'g_core', title:'코어',       cls:'g-core', members:['core_a']},
  {id:'g_out',  title:'출력 어댑터', cls:'g-out',  members:['out_db']},
  {id:'g_field',title:'외부 확정 대기', cls:'g-field', members:['f_spec']},
];

const NODES = [
  // {id, stage:'top'|'detail', x, y, w, h, st, cat, ttl, bdg, sum, fl, tip}
  // st: s-done(초록 구현·검증) s-todo(빨강 미배선=우리작업) s-field(노랑 외부대기) s-ext(회색 외부) s-core(파랑 코어)
  {id:'client', stage:'top', x:24, y:60, w:150, h:60, st:'s-ext', cat:'외부', ttl:'클라이언트', bdg:'외부',
   sum:'명령을 보내는 쪽', fl:'외부 시스템',
   tip:`<h4>클라이언트</h4><div class="file">외부 시스템</div><ul>
   <li>코어에 요청을 보내고 결과를 회신받음</li></ul>`},

  {id:'ext_src', stage:'top', x:24, y:180, w:150, h:60, st:'s-ext', cat:'외부', ttl:'데이터 소스', bdg:'외부',
   sum:'입력 데이터 공급', fl:'외부 시스템',
   tip:`<h4>데이터 소스</h4><ul><li>코어가 읽어 갈 입력 공급</li></ul>`},

  {id:'core_a', stage:'top', x:320, y:110, w:170, h:70, st:'s-core', cat:'코어', ttl:'처리 엔진', bdg:'core',
   sum:'핵심 처리 로직', fl:'src/engine.py',
   tip:`<h4>처리 엔진</h4><div class="file">src/engine.py</div><ul>
   <li>입력을 받아 핵심 처리를 수행</li>
   <li>결과를 출력 어댑터로 전달</li></ul>`},

  {id:'out_db', stage:'top', x:640, y:110, w:150, h:64, st:'s-todo', cat:'출력', ttl:'DB 기록', bdg:'B1',
   sum:'결과 저장 (미배선)', fl:'src/db_writer.py',
   tip:`<h4>DB 기록</h4><div class="file">src/db_writer.py</div><ul>
   <li>처리 결과를 테이블에 INSERT</li>
   <li>현재 미배선 — 다음 작업 대상</li></ul>`},

  {id:'f_spec', stage:'top', x:320, y:280, w:170, h:56, st:'s-field', cat:'대기', ttl:'인터페이스 규격', bdg:'외부확정',
   sum:'상대측 규격 확정 대기', fl:'',
   tip:`<h4>인터페이스 규격</h4><ul><li>상대측이 확정해야 값이 정해짐</li></ul>`},

  // 상세(detail) 스테이지 — 코어 내부 확대
  {id:'d_step1', stage:'detail', x:30, y:24, w:180, h:56, st:'s-core', cat:'1단계', ttl:'전처리', bdg:'',
   sum:'입력 정규화', fl:'src/engine.py',
   tip:`<h4>전처리</h4><ul><li>입력을 표준 형태로 정규화</li></ul>`},
  {id:'d_step2', stage:'detail', x:300, y:24, w:180, h:56, st:'s-core', cat:'2단계', ttl:'판정', bdg:'',
   sum:'규칙 적용·결과 산출', fl:'src/engine.py',
   tip:`<h4>판정</h4><ul><li>규칙을 적용해 최종 결과 산출</li></ul>`},
];

const EDGES = [
  // [from, to, 라벨, kind, desc]  kind: ''실선(흐름점) 'todo'빨강점선 'back'파랑점선(회신)
  ['client','core_a','요청','', '클라이언트가 처리 요청을 전달'],
  ['ext_src','core_a','데이터','', '엔진이 소스에서 입력을 읽음'],
  ['core_a','out_db','결과','todo', '엔진 결과를 DB 기록으로 전달 (미배선)'],
  ['core_a','client','회신','back', '처리 결과를 클라이언트로 회신'],
  ['d_step1','d_step2','','', '정규화된 입력을 판정 단계로 전달'],
];

const MSGS = [
 // 우측 리스트. {g:'그룹 제목', items:[{k,nm,fn,st,rel,tip}]}  st: done/warn/todo/ext
 // 클릭 = rel 노드·간선만 강조(흐름 하이라이트). tip = 스키마 표 등 상세.
 {g:'요청 흐름', items:[
  {k:'flow_req', nm:'REQ', fn:'처리 요청', st:'done', rel:['client','core_a','out_db'],
   tip:`<h4>처리 요청 흐름</h4><div class="file">클라이언트 → 엔진 → DB</div>
   <table><tr><th>필드</th><th>타입</th><th>크기</th><th>설명</th></tr>
   <tr><td class="k">REQ_ID</td><td>String</td><td>20</td><td>요청 식별자</td></tr>
   <tr><td class="k">PAYLOAD</td><td>String</td><td>100</td><td>처리 대상</td></tr></table>`},
 ]},
];

const FLOW_ACTS = {
  // {흐름키:{노드id:'그 흐름에서 이 노드가 하는 행동'}} — 하이라이트 중 노드 hover 에 뜸
  flow_req: {
    client: '요청 전문을 만들어 전송',
    core_a: '요청을 파싱해 처리 실행',
    out_db: '처리 결과 행을 INSERT (미배선)',
  },
};

const DEFAULT_POS = {"client": {"x": 24, "y": 60}, "ext_src": {"x": 24, "y": 180}, "core_a": {"x": 320, "y": 110}, "out_db": {"x": 640, "y": 110}, "f_spec": {"x": 320, "y": 280}, "d_step1": {"x": 30, "y": 24}, "d_step2": {"x": 300, "y": 24}};
// 간선 포트 수동 지정(선택) — {"from>to#0": {a:'R0', b:'L2'}} 포트 = 면(L/R/T/B)+슬롯(0/1/2). 수정모드에서 간선 클릭 → 손잡이 클릭으로 바꾸고 배치 저장.
const DEFAULT_PORTS = {};
