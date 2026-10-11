/* 구조도 엔진 — 로직 (내용은 data.js, 스타일은 style.css. 이 파일은 보통 안 건드림)
   프로젝트별 조정: 아래 W_TOP/H_TOP(상단 캔버스)·W_DET/H_DET(상세 캔버스) 크기, KEY(저장 키) */
const W_TOP=1700, H_TOP=740, W_DET=1460, H_DET=116;
const KEY='arch_pos_v1';   // 프로젝트별 고유 키로 변경(브라우저 저장 충돌 방지)
const cTop=document.getElementById('cTop'), cDet=document.getElementById('cDetail');
const eTop=document.getElementById('eTop'), eDet=document.getElementById('eDetail');
const tip=document.getElementById('tip');
const byId={}; NODES.forEach(n=>byId[n.id]=n);
const groupOf={}; GROUPS.forEach(g=>g.members.forEach(id=>groupOf[id]=g.id));
let editing=false, hiSet=null, hiKey=null;
// 간선 포트 수동 지정: {간선키: {a:'R0', b:'L2'}}  포트 = 면(L/R/T/B) + 슬롯(0/1/2, 1 = 중앙). data.js 의 DEFAULT_PORTS 가 기본, 내 편집은 localStorage
const PORTS = Object.assign({}, (typeof DEFAULT_PORTS!=='undefined' && DEFAULT_PORTS) || {});
try{ const pp=JSON.parse(localStorage.getItem(KEY+'_ports')||'null'); if(pp) Object.assign(PORTS, pp); }catch(e){}
let selEdge=null;   // 수정모드에서 클릭한 간선 키
const SNAP=12;
// 줌/팬 모델: 캔버스를 직접 translate+scale (transform-origin 0 0). _scale/_tx/_ty 보관
let userTop=false;
const clmp=v=>Math.max(0.2,Math.min(3,v));
function applyT(c,s,tx,ty){ s=clmp(s); c._scale=s; c._tx=tx; c._ty=ty;
  c.style.transformOrigin='0 0';
  c.style.transform='translate('+tx+'px,'+ty+'px) scale('+s+')'; }
function snapTargets(n){
  const gid=groupOf[n.id];
  if(gid) return GROUPS.find(g=>g.id===gid).members.filter(id=>id!==n.id).map(id=>byId[id]).filter(Boolean);
  return NODES.filter(o=>o!==n && o.stage===n.stage && !groupOf[o.id]);
}

// 기본 배치 적용 후 localStorage(내 편집) 우선
NODES.forEach(n=>{ if(DEFAULT_POS[n.id]){ n.x=DEFAULT_POS[n.id].x; n.y=DEFAULT_POS[n.id].y; } });
try{ const p=JSON.parse(localStorage.getItem(KEY)||'null');
  if(p) NODES.forEach(n=>{ if(p[n.id]){ n.x=p[n.id].x; n.y=p[n.id].y; } }); }catch(e){}

cTop.style.width=W_TOP+'px'; cTop.style.height=H_TOP+'px';
cDet.style.width=W_DET+'px'; cDet.style.height=H_DET+'px';
eTop.setAttribute('viewBox',`0 0 ${W_TOP} ${H_TOP}`);
eDet.setAttribute('viewBox',`0 0 ${W_DET} ${H_DET}`);

function mkNode(n){
  const d=document.createElement('div');
  d.className='node '+n.st; d.dataset.id=n.id;
  d.style.left=n.x+'px'; d.style.top=n.y+'px'; d.style.width=n.w+'px'; d.style.minHeight=n.h+'px';
  d.innerHTML=`<div class="cat">${n.cat}</div>
    <div class="ttl">${n.ttl}</div>${n.bdg?`<span class="bdg">${n.bdg}</span>`:''}
    <div class="sum">${n.sum}</div>${n.fl?`<div class="fl">${n.fl}</div>`:''}`;
  (n.stage==='top'?cTop:cDet).appendChild(d);
  d.addEventListener('mouseenter',()=>{
    const sc=(n.stage==='top'?cTop:cDet)._scale||1;
    if(hiSet){ if(hiSet.has(n.id)) showTipHTML(flowTipHTML(hiKey,n),d,sc); }  // 경로 하이라이트 중: 관련 노드만, 행동 텍스트
    else showTipHTML(n.tip,d,sc);                                            // 평소: 노드 상세
  });
  d.addEventListener('mouseleave',hideTipNow);
  d.addEventListener('pointerdown',e=>startDrag(e,n,d));
  n._el=d;
}
function mkGroup(g){
  const d=document.createElement('div');
  d.className='group '+g.cls; d.dataset.gid=g.id;
  d.innerHTML=`<div class="gl">${g.title}</div>`;
  cTop.appendChild(d); g._el=d; layoutGroup(g);
  d.addEventListener('pointerdown',e=>startGroupDrag(e,g));
}
function layoutGroup(g){
  const ms=g.members.map(id=>byId[id]).filter(Boolean);
  if(!ms.length) return;
  const pad=g.pad||14, top=g.padTop||18;
  const x1=Math.min(...ms.map(n=>n.x))-pad, y1=Math.min(...ms.map(n=>n.y))-top;
  const x2=Math.max(...ms.map(n=>n.x+n.w))+pad, y2=Math.max(...ms.map(n=>n.y+n.h))+pad;
  Object.assign(g._el.style,{left:x1+'px',top:y1+'px',width:(x2-x1)+'px',height:(y2-y1)+'px'});
}

// ── 간선 라우팅 (전부 곡선, 다른 노드 회피, 없으면 최단 포트) ──
const NM=8;
// 한 면에 슬롯 3개(25%·50%·75%). 포트 문자열 = 면 + 슬롯('R'만 쓰면 중앙 'R1')
const SLOT_F=[0.25,0.5,0.75];
function portInfo(n,port){ const d=port[0], k=port.length>1?+port[1]:1, f=SLOT_F[k]??0.5;
  const px=n.x+n.w*f, py=n.y+n.h*f;
  if(d==='R')return{p:[n.x+n.w,py],nx:1,ny:0};
  if(d==='L')return{p:[n.x,py],nx:-1,ny:0};
  if(d==='T')return{p:[px,n.y],nx:0,ny:-1};
  return{p:[px,n.y+n.h],nx:0,ny:1}; }
function edgeKey(i){ const e=EDGES[i]; let k=0; for(let j=0;j<i;j++) if(EDGES[j][0]===e[0]&&EDGES[j][1]===e[1]) k++; return e[0]+'>'+e[1]+'#'+k; }
function ptInObs(x,y,obs){ for(const r of obs){ if(x>=r.x-NM&&x<=r.x+r.w+NM&&y>=r.y-NM&&y<=r.y+r.h+NM) return true; } return false; }
function bezierClear(c,obs){ for(let i=1;i<18;i++){ const t=i/18,m=1-t;
  const x=m*m*m*c.p1[0]+3*m*m*t*c.c1[0]+3*m*t*t*c.c2[0]+t*t*t*c.p2[0];
  const y=m*m*m*c.p1[1]+3*m*m*t*c.c1[1]+3*m*t*t*c.c2[1]+t*t*t*c.p2[1];
  if(ptInObs(x,y,obs)) return false; } return true; }
function curve(a,sa,b,sb){
  const A=portInfo(a,sa), B=portInfo(b,sb), p1=A.p, p2=B.p;
  const dist=Math.hypot(p2[0]-p1[0],p2[1]-p1[1]), k=Math.max(30,dist*0.4);
  return {p1,p2,dist,c1:[p1[0]+A.nx*k,p1[1]+A.ny*k],c2:[p2[0]+B.nx*k,p2[1]+B.ny*k]}; }
function mkEdge(c){
  const mx=0.125*c.p1[0]+0.375*c.c1[0]+0.375*c.c2[0]+0.125*c.p2[0];
  const my=0.125*c.p1[1]+0.375*c.c1[1]+0.375*c.c2[1]+0.125*c.p2[1];
  return {d:`M${c.p1[0]},${c.p1[1]} C${c.c1[0]},${c.c1[1]} ${c.c2[0]},${c.c2[1]} ${c.p2[0]},${c.p2[1]}`, mid:[mx,my]}; }
// 1단계: 면 선택(수동 지정 면은 고정, 나머지는 다른 노드 회피·최단). 2단계: 같은 노드 같은 면에 모인 간선을 슬롯 3개에 나눠 겹침 회피
function pickSides(a,b,fixA,fixB){
  const obs=NODES.filter(n=>n.stage===a.stage && n!==a && n!==b);
  const dirs=['R','L','T','B'];
  const dx=(b.x+b.w/2)-(a.x+a.w/2), dy=(b.y+b.h/2)-(a.y+a.h/2);
  let pa,pb; if(Math.abs(dx)>=Math.abs(dy)){ pa=dx>=0?'R':'L'; pb=dx>=0?'L':'R'; }
  else { pa=dy>=0?'B':'T'; pb=dy>=0?'T':'B'; }
  if(fixA) pa=fixA; if(fixB) pb=fixB;
  const nat=curve(a,pa,b,pb);
  if(bezierClear(nat,obs)) return [pa,pb];
  let best=null, shortest=nat; shortest._s=[pa,pb];
  for(const sa of (fixA?[fixA]:dirs)) for(const sb of (fixB?[fixB]:dirs)){
    const c=curve(a,sa,b,sb);
    if(c.dist<shortest.dist){ shortest=c; shortest._s=[sa,sb]; }
    if(bezierClear(c,obs) && (!best||c.dist<best.dist)){ best=c; best._s=[sa,sb]; }
  }
  return (best||shortest)._s;
}
function routeAll(){
  // 반환: 간선 인덱스별 {pa,pb,fa,fb}(포트 문자열·수동 여부). 수동 지정은 그대로, 자동은 면 선택 후 슬롯 분배
  const R=EDGES.map(()=>null), use={};   // use[nodeId+side] = [{i,end,fixed,slot,ord}]
  EDGES.forEach((e,i)=>{ const na=byId[e[0]], nb=byId[e[1]]; if(!na||!nb) return;
    const ov=PORTS[edgeKey(i)]||{};
    const [sa,sb]=pickSides(na,nb, ov.a&&ov.a[0], ov.b&&ov.b[0]);
    R[i]={pa:ov.a||sa, pb:ov.b||sb, fa:!!ov.a, fb:!!ov.b};
    // 정렬 기준: 상대 끝점의 위치(가로 면이면 y, 세로 면이면 x) → 같은 면의 간선이 교차하지 않게 순서대로 슬롯
    const oa=(sa==='L'||sa==='R')?(nb.y+nb.h/2):(nb.x+nb.w/2), ob=(sb==='L'||sb==='R')?(na.y+na.h/2):(na.x+na.w/2);
    (use[na.id+R[i].pa[0]] ||= []).push({i,end:'a',fixed:!!ov.a,slot:ov.a?+(ov.a[1]??1):null,ord:oa});
    (use[nb.id+R[i].pb[0]] ||= []).push({i,end:'b',fixed:!!ov.b,slot:ov.b?+(ov.b[1]??1):null,ord:ob});
  });
  Object.values(use).forEach(list=>{
    const auto=list.filter(u=>!u.fixed).sort((p,q)=>p.ord-q.ord);
    if(auto.length===0) return;
    const taken=new Set(list.filter(u=>u.fixed).map(u=>u.slot));
    const free=[0,1,2].filter(k=>!taken.has(k));
    let slots;
    if(free.length===0) slots=auto.map((_,j)=>j%3);                                   // 세 슬롯 다 수동 점유 → 겹침 허용
    else if(auto.length===1) slots=[free.includes(1)?1:free[Math.floor(free.length/2)]];
    else if(auto.length===2 && free.length>=2) slots=[free[0],free[free.length-1]];
    else slots=auto.map((_,j)=>free[Math.min(free.length-1,Math.floor(j*free.length/auto.length))]);   // 4개 이상은 겹칠 수 있음
    auto.forEach((u,j)=>{ const r=R[u.i]; const side=(u.end==='a'?r.pa:r.pb)[0];
      if(u.end==='a') r.pa=side+slots[j]; else r.pb=side+slots[j]; });
  });
  return R;
}
function edgePath(a,b,pa,pb){ return mkEdge(curve(a,pa,b,pb)); }
function drawEdges(){
  const NS='http://www.w3.org/2000/svg';
  [eTop,eDet].forEach(svg=>{ while(svg.lastChild) svg.removeChild(svg.lastChild);
    svg.insertAdjacentHTML('beforeend',
      `<defs>
       <marker id="ah-${svg.id}" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto" markerUnits="userSpaceOnUse">
        <path d="M0,0 L6,3 L0,6 z" fill="var(--muted)"/></marker>
       <marker id="ah-${svg.id}-t" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto" markerUnits="userSpaceOnUse">
        <path d="M0,0 L6,3 L0,6 z" fill="var(--todo)"/></marker>
       <marker id="ah-${svg.id}-b" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto" markerUnits="userSpaceOnUse">
        <path d="M0,0 L6,3 L0,6 z" fill="var(--accent)"/></marker></defs>`);
  });
  const routes=routeAll();
  EDGES.forEach(([a,b,lbl,kind,desc],ei)=>{
    const na=byId[a], nb=byId[b]; if(!na||!nb) return;
    const svg = na.stage==='detail'?eDet:eTop;
    const rt=routes[ei], ekey=edgeKey(ei);
    const {d,mid}=edgePath(na,nb,rt.pa,rt.pb);
    const on = !hiSet || (hiSet.has(a)&&hiSet.has(b));
    const path=document.createElementNS(NS,'path');
    path.setAttribute('d',d);
    let mk='ah-'+svg.id;
    if(kind==='todo'){ path.setAttribute('class','todo'); mk+='-t'; }
    else if(kind==='back'){ path.setAttribute('class','back'); mk+='-b'; }
    path.setAttribute('marker-end',`url(#${mk})`);   // 화살표색 = 간선 stroke 변수(muted/todo/accent)와 동일
    if(!on) path.classList.add('edim');
    if(editing && selEdge===ekey) path.classList.add('sel');
    svg.appendChild(path);
    if(kind!=='todo' && kind!=='back'){
      const fp=document.createElementNS(NS,'path'); fp.setAttribute('d',d);
      fp.setAttribute('class','flow'+(on?'':' edim')); svg.appendChild(fp);
    }
    if(lbl){ const t=document.createElementNS(NS,'text');
      t.setAttribute('x',mid[0]); t.setAttribute('y',mid[1]-3);
      t.setAttribute('text-anchor','middle'); if(kind==='todo') t.setAttribute('class','todo');
      if(!on) t.classList.add('edim');
      t.textContent=lbl; svg.appendChild(t); }
    // 간선 hover — 투명 두꺼운 hit-path 깔아 그 링크가 하는 일(desc) 툴팁
    const hit=document.createElementNS(NS,'path'); hit.setAttribute('d',d); hit.setAttribute('class','ehit');
    hit.addEventListener('mouseenter',ev=>{
      if(editing) return;
      const sc=(na.stage==='top'?cTop:cDet)._scale||1;
      if(hiSet){ if(on) showTipAt(flowEdgeTipHTML(hiKey,na,nb,lbl,desc),ev.clientX,ev.clientY,sc); }  // 하이라이트 중: 관련 링크만, 흐름 맥락
      else showTipAt(edgeTipHTML(na,nb,lbl,kind,desc),ev.clientX,ev.clientY,sc);                       // 평소: 링크 상세
    });
    hit.addEventListener('mouseleave',hideTipNow);
    hit.addEventListener('pointerdown',ev=>{ if(!editing) return; ev.stopPropagation(); selEdge=(selEdge===ekey)?null:ekey; drawEdges(); });
    svg.appendChild(hit);
    if(editing && selEdge===ekey) drawPortHandles(svg,na,nb,rt,ekey,mid);
  });
}
// 선택한 간선의 양 끝 노드에 포트 손잡이 12개(면당 3개). 클릭 = 그 끝을 그 포트로 고정. 목적 노드는 바뀌지 않는다.
function drawPortHandles(svg,na,nb,rt,ekey,mid){
  const NS='http://www.w3.org/2000/svg';
  [[na,'a',rt.pa,rt.fa],[nb,'b',rt.pb,rt.fb]].forEach(([n,end,cur,fixed])=>{
    for(const side of ['L','R','T','B']) for(let k=0;k<3;k++){
      const port=side+k, pi=portInfo(n,port);
      const c=document.createElementNS(NS,'circle');
      c.setAttribute('cx',pi.p[0]); c.setAttribute('cy',pi.p[1]); c.setAttribute('r',5);
      c.setAttribute('class','port'+(port===cur?(fixed?' on':' cur'):''));
      c.addEventListener('pointerdown',ev=>{ ev.stopPropagation();
        PORTS[ekey]=Object.assign({},PORTS[ekey]||{}); PORTS[ekey][end]=port; savePorts(); drawEdges(); });
      svg.appendChild(c);
    }
  });
  if(PORTS[ekey]){   // 수동 지정 해제 = 간선 가운데 '자동'
    const t=document.createElementNS(NS,'text'); t.setAttribute('x',mid[0]); t.setAttribute('y',mid[1]+14);
    t.setAttribute('text-anchor','middle'); t.setAttribute('class','pbtn'); t.textContent='자동';
    t.addEventListener('pointerdown',ev=>{ ev.stopPropagation(); delete PORTS[ekey]; savePorts(); drawEdges(); });
    svg.appendChild(t);
  }
}
function savePorts(){ try{ localStorage.setItem(KEY+'_ports',JSON.stringify(PORTS)); }catch(e){} }
function render(){ GROUPS.forEach(layoutGroup); drawEdges(); }

// ── 호버 팝업 (호버 떼면 바로 닫힘) ──
let tipTimer=null;
function clearTipTimer(){ if(tipTimer){ clearTimeout(tipTimer); tipTimer=null; } }
function hideTipNow(){ clearTipTimer(); tip.style.display='none'; }
function showTipHTML(html,el,scale){ if(editing||!html) return; clearTipTimer();
  tip.innerHTML=html; tip.style.fontSize=(13*(scale||1))+'px'; tip.style.display='block';
  const r=el.getBoundingClientRect(), tw=tip.offsetWidth, th=tip.offsetHeight;
  let x=r.right+10; if(x+tw>innerWidth-8) x=r.left-tw-10; if(x<8) x=8;
  let y=r.top; if(y+th>innerHeight-8) y=innerHeight-th-8; if(y<8) y=8;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
tip.addEventListener('mouseenter',clearTipTimer);
tip.addEventListener('mouseleave',hideTipNow);
// 간선용 — 커서 위치에 툴팁(간선은 박스가 아니라 커서 기준)
function showTipAt(html,cx,cy,scale){ if(editing||!html) return; clearTipTimer();
  tip.innerHTML=html; tip.style.fontSize=(13*(scale||1))+'px'; tip.style.display='block';
  const tw=tip.offsetWidth, th=tip.offsetHeight;
  let x=cx+14; if(x+tw>innerWidth-8) x=cx-tw-14; if(x<8) x=8;
  let y=cy+12; if(y+th>innerHeight-8) y=innerHeight-th-8; if(y<8) y=8;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
function edgeTipHTML(na,nb,lbl,kind,desc){
  const k = kind==='todo'?' · <span style="color:var(--todo)">미배선</span>'
          : kind==='back'?' · <span style="color:var(--accent)">회신</span>':'';
  return `<h4>${na.ttl} <span style="color:var(--dim)">→</span> ${nb.ttl}</h4>`+
    `<div class="file">링크${lbl?' · '+lbl:''}${k}</div><ul><li>${desc||'연결'}</li></ul>`;
}

// ── 줌/팬: 캔버스를 translate+scale 로 직접 이동·확대 (fit=한번 맞춤, 이후 휠/팬 자유) ──
function fitTop(){
  const pT=cTop.parentElement, stages=document.querySelector('.stages');
  // scale 은 '상세 토글과 무관한 고정 기준'(전체 stages 높이 − 상세영역 높이)로만 계산 → 접든 펴든 불변
  const refH=stages.clientHeight-(H_DET+2);
  const sT=Math.min(1,(pT.clientWidth-16)/W_TOP,(refH-8)/H_TOP);
  applyT(cTop,sT,Math.max(8,(pT.clientWidth-W_TOP*sT)/2),Math.max(0,(pT.clientHeight-H_TOP*sT)/2));
}
function fitDet(){
  if(document.body.classList.contains('no-detail')) return;
  const pD=cDet.parentElement, sD=Math.min(1,(pD.clientWidth-16)/W_DET,(pD.clientHeight-8)/H_DET);
  applyT(cDet,sD,Math.max(8,(pD.clientWidth-W_DET*sD)/2),Math.max(0,(pD.clientHeight-H_DET*sD)/2));
}
function fit(){ if(!userTop) fitTop(); fitDet(); }   // 휠/팬으로 상단 줌 바꾼 뒤엔 resize 가 상단 줌 유지
window.addEventListener('resize',fit);

// ── 드래그 (노드 / 그룹), 축소비율 보정 + 정렬 스냅 + 자동저장 ──
let drag=null;
function startDrag(e,n,el){ if(!editing||e.button!==0) return; e.preventDefault(); e.stopPropagation();
  drag={type:'node',n,el,sx:e.clientX,sy:e.clientY,ox:n.x,oy:n.y,sc:(el.parentElement._scale||1)};
  el.setPointerCapture(e.pointerId);
}
function startGroupDrag(e,g){ if(!editing||e.button!==0) return; e.preventDefault(); e.stopPropagation();
  const orig=g.members.map(id=>byId[id]).filter(Boolean).map(n=>({n,x:n.x,y:n.y}));
  if(!orig.length) return;
  drag={type:'group',g,sx:e.clientX,sy:e.clientY,orig,sc:(g._el.parentElement._scale||1)};
  g._el.setPointerCapture(e.pointerId);
}
document.addEventListener('pointermove',e=>{ if(!drag) return;
  if(drag.type==='group'){
    let dx=(e.clientX-drag.sx)/drag.sc, dy=(e.clientY-drag.sy)/drag.sc;
    const minx=Math.min(...drag.orig.map(o=>o.x)), miny=Math.min(...drag.orig.map(o=>o.y));
    if(minx+dx<0) dx=-minx; if(miny+dy<0) dy=-miny;
    drag.orig.forEach(o=>{ o.n.x=Math.round(o.x+dx); o.n.y=Math.round(o.y+dy);
      o.n._el.style.left=o.n.x+'px'; o.n._el.style.top=o.n.y+'px'; });
    render(); return;
  }
  let nx=Math.max(0,drag.ox+(e.clientX-drag.sx)/drag.sc), ny=Math.max(0,drag.oy+(e.clientY-drag.sy)/drag.sc);
  let bestX=nx,dX=SNAP, bestY=ny,dY=SNAP;
  snapTargets(drag.n).forEach(o=>{
    if(Math.abs(nx-o.x)<dX){ dX=Math.abs(nx-o.x); bestX=o.x; }
    if(Math.abs(ny-o.y)<dY){ dY=Math.abs(ny-o.y); bestY=o.y; }
  });
  nx=bestX; ny=bestY;
  drag.n.x=Math.round(nx); drag.n.y=Math.round(ny);
  drag.el.style.left=drag.n.x+'px'; drag.el.style.top=drag.n.y+'px';
  render();
});
function saveLayout(){ try{ const p={}; NODES.forEach(n=>p[n.id]={x:n.x,y:n.y});
  localStorage.setItem(KEY,JSON.stringify(p)); }catch(e){} savePorts(); }
document.addEventListener('pointerup',()=>{ if(drag) saveLayout(); drag=null; });

// ── 빌드 ──
GROUPS.forEach(mkGroup);
NODES.forEach(mkNode);
NODES.forEach(n=>{ n.h=n._el.offsetHeight; });
render();
fit();

// ── 휠 줌(커서 기준) + 팬(좌클릭 드래그·빈 영역) + 영역 구분선 + 줌/팬 저장·복원 ──
const paneTop=cTop.parentElement, paneDet=cDet.parentElement;
function saveView(){ try{ localStorage.setItem(KEY+'_view',JSON.stringify({
  top:{s:cTop._scale,tx:cTop._tx,ty:cTop._ty}, det:{s:cDet._scale,tx:cDet._tx,ty:cDet._ty}})); }catch(e){} }
// 휠: 커서 아래 콘텐츠 좌표를 고정한 채 확대/축소
function wheelZoom(e,canvas,pane,top){ e.preventDefault();
  const s0=canvas._scale||1, s=clmp(s0*(e.deltaY<0?1.12:1/1.12));
  const r=pane.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  const cx=(mx-(canvas._tx||0))/s0, cy=(my-(canvas._ty||0))/s0;
  applyT(canvas,s,mx-cx*s,my-cy*s); if(top)userTop=true; saveView(); }
paneTop.addEventListener('wheel',e=>wheelZoom(e,cTop,paneTop,true),{passive:false});
paneDet.addEventListener('wheel',e=>wheelZoom(e,cDet,paneDet,false),{passive:false});
// 팬: 좌클릭 드래그. 노드/그룹 위(편집모드)는 startDrag/startGroupDrag 의 stopPropagation 으로 안 옴
let pan=null;
function panStart(e,canvas,pane){ if(e.button!==0) return;
  if(editing && selEdge){ selEdge=null; drawEdges(); }   // 빈 곳 클릭 = 간선 선택 해제
  pan={canvas,x:e.clientX,y:e.clientY,tx:canvas._tx||0,ty:canvas._ty||0}; pane.style.cursor='grabbing'; }
paneTop.addEventListener('pointerdown',e=>panStart(e,cTop,paneTop));
paneDet.addEventListener('pointerdown',e=>panStart(e,cDet,paneDet));
document.addEventListener('pointermove',e=>{ if(!pan) return;
  applyT(pan.canvas,pan.canvas._scale,pan.tx+(e.clientX-pan.x),pan.ty+(e.clientY-pan.y));
  if(pan.canvas===cTop) userTop=true; });
document.addEventListener('pointerup',()=>{ if(pan){ paneTop.style.cursor=''; paneDet.style.cursor=''; pan=null; saveView(); } });
// 영역 구분선(수정모드): 위아래로 끌어 상단/상세 영역 비율 변경 (영역만, 박스 크기는 휠로)
const resizer=document.getElementById('resizer'), detailStage=document.querySelector('.stage.detail');
try{ const dh=localStorage.getItem(KEY+'_detH'); if(dh) detailStage.style.height=dh; }catch(e){}
let rz=null;
resizer.addEventListener('pointerdown',e=>{ if(!editing||e.button!==0) return; e.preventDefault();
  rz={sy:e.clientY,h:detailStage.getBoundingClientRect().height}; resizer.setPointerCapture(e.pointerId); });
document.addEventListener('pointermove',e=>{ if(!rz) return;
  const stagesH=document.querySelector('.stages').clientHeight;
  let nh=rz.h+(rz.sy-e.clientY); nh=Math.max(70,Math.min(stagesH-120,nh));
  detailStage.style.height=nh+'px'; });
document.addEventListener('pointerup',()=>{ if(rz){ try{localStorage.setItem(KEY+'_detH',detailStage.style.height);}catch(e){} rz=null; fitDet(); } });
// 줌/팬 복원 (빌드·fit 끝난 뒤)
(function(){ let v=null; try{ v=JSON.parse(localStorage.getItem(KEY+'_view')||'null'); }catch(e){}
  if(!v) return;
  if(v.top){ applyT(cTop,v.top.s,v.top.tx,v.top.ty); userTop=true; }
  if(v.det && !document.body.classList.contains('no-detail')) applyT(cDet,v.det.s,v.det.tx,v.det.ty); })();

// ── 버튼 ──
const btn=document.getElementById('btnEdit'), btnReset=document.getElementById('btnReset');
btn.addEventListener('click',()=>{ editing=!editing;
  document.body.classList.toggle('editing',editing);
  btn.classList.toggle('on',editing); btn.textContent=editing?'완료':'수정';
  if(editing) hideTipNow(); else { selEdge=null; saveLayout(); }
  drawEdges();
});
btnReset.addEventListener('click',()=>{ if(!confirm('내 편집(위치)을 지우고 기본 배치로 되돌릴까요?'))return;
  localStorage.removeItem(KEY); localStorage.removeItem(KEY+'_view'); localStorage.removeItem(KEY+'_detH'); localStorage.removeItem(KEY+'_ports'); location.reload(); });
const btnDetail=document.getElementById('btnDetail');
btnDetail.addEventListener('click',()=>{ const off=document.body.classList.toggle('no-detail');
  btnDetail.textContent=off?'상세 펴기':'상세 접기'; fit(); });

// ── 우측 리스트 (클릭 = 관련 흐름 강조) ──
const SB={done:'✓',warn:'부분',todo:'미배선',ext:'범위밖'};
const RELATED={}, MSGMETA={};
function flowTipHTML(key,n){
  const act=((typeof FLOW_ACTS!=='undefined'&&FLOW_ACTS[key])||{})[n.id], m=MSGMETA[key]||{};
  return `<h4>${m.nm||''} <span style="color:var(--dim);font-weight:400;font-size:11px">${m.fn||''}</span></h4>`+
    `<div class="file">${n.cat} · ${n.ttl}</div><ul><li>${act||'이 경로에 참여'}</li></ul>`;
}
// 간선 흐름 버전 — 하이라이트 중 관련 링크 hover 시(흐름명 + 그 링크 동작)
function flowEdgeTipHTML(key,na,nb,lbl,desc){
  const m=MSGMETA[key]||{};
  return `<h4>${m.nm||''} <span style="color:var(--dim);font-weight:400;font-size:11px">${m.fn||''}</span></h4>`+
    `<div class="file">${na.ttl} → ${nb.ttl}${lbl?' · '+lbl:''}</div><ul><li>${desc||'이 경로의 링크'}</li></ul>`;
}
function applyHi(){ NODES.forEach(n=>{ if(!n._el)return;
  n._el.classList.toggle('dim', !!hiSet&&!hiSet.has(n.id));
  n._el.classList.toggle('hi',  !!hiSet&&hiSet.has(n.id)); }); }
function setHi(key){ hiKey=(key===hiKey)?null:key; hiSet=(hiKey&&RELATED[hiKey])?new Set(RELATED[hiKey]):null;
  document.querySelectorAll('.tlist .ti').forEach(el=>el.classList.toggle('on',el.dataset.key===hiKey));
  applyHi(); drawEdges(); }
function buildPanel(){
  const box=document.getElementById('tlist');
  box.innerHTML='<h5>전문 · 테이블 <button id="tClear">전체</button></h5>';
  MSGS.forEach(grp=>{
    const gh=document.createElement('div'); gh.className='gh'; gh.textContent=grp.g; box.appendChild(gh);
    grp.items.forEach(it=>{
      RELATED[it.k]=it.rel||null; MSGMETA[it.k]={nm:it.nm,fn:it.fn};
      const d=document.createElement('div'); d.className='ti t-'+it.st; d.dataset.key=it.k;
      d.innerHTML=`<span class="nm">${it.nm}</span><span class="fnm">${it.fn}</span><span class="sb">${SB[it.st]}</span>`;
      if(it.st!=='ext'){
        d.addEventListener('click',()=>setHi(it.k));
        d.addEventListener('mouseenter',()=>showTipHTML(it.tip,d));
        d.addEventListener('mouseleave',hideTipNow);
      }
      box.appendChild(d);
    });
  });
  document.getElementById('tClear').addEventListener('click',()=>setHi(null));
}
buildPanel();

// ── 배치 내보내기 (다운로드 폴더의 philip_arch_layout.json) ──
document.getElementById('btnExport').addEventListener('click',()=>{
  const p={}; NODES.forEach(n=>p[n.id]={x:n.x,y:n.y});
  const blob=new Blob([JSON.stringify({pos:p,ports:PORTS})],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='philip_arch_layout_'+Date.now()+'.json'; document.body.appendChild(a); a.click();
  setTimeout(()=>{ URL.revokeObjectURL(a.href); a.remove(); },800);
});

// ── 배치 저장 — 로컬 서버(start.bat)로 열었으면 그 폴더 data.js 의 DEFAULT_POS·DEFAULT_PORTS 에 바로 덮어씀.
// PC·경로·선택창 전부 무관. file:// 로 직접 연 경우만 안내 + 내보내기 폴백.
async function saveLayoutToFile(){
  const btn=document.getElementById('btnSave');
  const pos={}; NODES.forEach(n=>pos[n.id]={x:n.x,y:n.y});
  if(location.protocol==='http:'||location.protocol==='https:'){
    try{
      const r=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pos,ports:PORTS})});
      const t=await r.text(); if(!r.ok) throw new Error(t);
      saveLayout();
      const o=btn.textContent; btn.textContent='저장됨 ✓'; setTimeout(()=>btn.textContent=o,1300);
    }catch(e){ alert('저장 실패: '+(e.message||e)); }
    return;
  }
  // file:// 로 직접 열림 — 브라우저가 파일 쓰기를 막음. 서버로 열라고 안내 + 내보내기로 폴백.
  alert('바로 저장하려면 같은 폴더의 "구조도_열기.bat" 으로 여세요.\n(지금은 file:// 라 브라우저가 파일 쓰기를 막습니다.)\n\n임시로 배치 파일을 내려받습니다.');
  document.getElementById('btnExport').click();
}
document.getElementById('btnSave').addEventListener('click',saveLayoutToFile);
