# -*- coding: utf-8 -*-
"""
mem_graph.py — 메모리 링크 무결성 점검 (Obsidian 그래프의 CLI 판)

[[name]] 위키링크망을 스캔해 philip:memory 의 위생 점검(끊긴 링크·고아·중복)을 자동화한다.
Obsidian 볼트로 열면 같은 걸 그래프로 시각화 — 이 도구는 그 감사를 커맨드/CI 에서 돌리는 용도.

사용:  python mem_graph.py <memory_dir>
       (인자 없으면 현재 폴더)

출력: unresolved(끊긴 링크) · orphans(고립 노드) · hubs(참조 상위) · 요약 카운트.
주의: [[X]] 를 문법 예시로 쓴 문서(예: 메모리 규격 설명)는 끊긴 링크로 잡힐 수 있다 — 사람이 판단.
"""
import sys, os, re, glob, io

# Windows cp949 파이프에서도 안전하게 utf-8 출력
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

mem = sys.argv[1] if len(sys.argv) > 1 else "."
files = [f for f in glob.glob(os.path.join(mem, "*.md"))
         if os.path.basename(f).upper() != "MEMORY.MD"]
if not files:
    print("메모리 .md 파일 없음:", os.path.abspath(mem)); sys.exit(1)

names = {os.path.splitext(os.path.basename(f))[0] for f in files}
link_re = re.compile(r'\[\[([^\]]+)\]\]')
outgoing, incoming = {}, {n: set() for n in names}

for f in files:
    n = os.path.splitext(os.path.basename(f))[0]
    txt = open(f, encoding="utf-8", errors="replace").read()
    links = {l.split('|')[0].split('#')[0].strip() for l in link_re.findall(txt)}
    outgoing[n] = links
    for l in links:
        if l in incoming:
            incoming[l].add(n)

unresolved = {n: [l for l in ls if l not in names]
              for n, ls in outgoing.items() if any(l not in names for l in ls)}
orphans = sorted(n for n in names if not incoming[n] and not outgoing[n])
hubs = sorted(names, key=lambda n: len(incoming[n]), reverse=True)[:8]

print("메모리 파일: %d개  |  링크 있는 노드: %d  |  고아: %d  |  끊긴 링크 보유: %d"
      % (len(files), sum(1 for n in names if incoming[n] or outgoing[n]),
         len(orphans), len(unresolved)))

print("\n[끊긴 링크] (존재하지 않는 [[대상]] — Obsidian 회색 표시. 오타/미작성/문법예시)")
if not unresolved:
    print("  없음")
for n, m in sorted(unresolved.items()):
    print("  %s → %s" % (n, ", ".join(m)))

print("\n[고아 노드] (들어오는·나가는 링크 0 — 연결하거나 독립사실로 인정)")
print("  " + (", ".join(orphans) if orphans else "없음"))

print("\n[허브 top8] (많이 참조되는 지식 중심)")
for h in hubs:
    print("  %-42s ← %d refs" % (h, len(incoming[h])))
