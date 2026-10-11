# guard_assets.py — PreToolUse 차단 훅 (L1 물리 강제, 플러그인판)
# Edit/Write/MultiEdit 대상이 보호 목록에 걸리면 exit 2 → 하네스가 편집을 거부하고
# stderr 사유가 에이전트에게 전달된다(에이전트가 규칙을 "기억"할 필요 자체를 제거).
# 엔진은 전 프로젝트 공통 — 프로젝트별 목록은 <프로젝트>/.claude/psp.config.json 에서 읽는다:
#   { "guard": { "protect": ["datasets/*", ...], "allow": ["특정/예외.pth", ...] } }
# 설정 파일이 없으면 [공통] 기본 목록만 적용(비 Philip Relay 프로젝트에서도 무해).
import json, os, sys, fnmatch
from pathlib import Path

try:  # Windows 콘솔(cp949) 한글 차단 사유가 깨지지 않게(필수)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# [공통 — 항상] 웹·시크릿(.dev.vars=Cloudflare wrangler 로컬 시크릿)·백업 보존물
PROTECT = [
    ".env*", "*.dev.vars", ".dev.vars", "migrations/*",
    "*_KEEP/*", "*_backup_*/*",
    "_quarantine/*", "_psp_quarantine/*",   # safe_delete 격리본 — 복원 원본이라 직접 편집 금지(docs/08)
]
ALLOW = []

# 프로젝트별 목록 병합 (cwd 의존 금지 — CLAUDE_PROJECT_DIR 절대경로)
try:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cfg = json.loads((Path(root) / ".claude" / "psp.config.json").read_text(encoding="utf-8-sig"))
    g = cfg.get("guard") or {}
    PROTECT += [str(x) for x in g.get("protect", [])]
    ALLOW += [str(x) for x in g.get("allow", [])]
except Exception:
    pass  # 설정 없음/깨짐 → 공통 목록만

def norm(p): return p.replace("\\", "/")

try:
    # 바이너리로 읽어 UTF-8 디코드 + 선행 BOM/공백 제거(Windows 파이프가 BOM을 흘리면
    # json.load 가 실패 → 조용히 통과되어 L1 차단이 무력화되는 사고 방지). 한글 경로도 안전.
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    data = json.loads(raw.lstrip("﻿").strip() or "{}")
except Exception:
    sys.exit(0)  # 입력 해석 불가 → 차단하지 않음(과차단 방지)

path = norm(str((data.get("tool_input") or {}).get("file_path", "")))
if not path:
    sys.exit(0)

if any(fnmatch.fnmatch(path, norm(a)) or norm(a) in path for a in ALLOW):
    sys.exit(0)

for pat in PROTECT:
    p = norm(pat)
    # 폴더 패턴은 경로 "세그먼트" 경계로만 매치 — 단순 부분문자열이면 dataset_tools/ 같은 무관 경로 과차단
    seg = "/" + p.strip("*/") + "/"
    if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path.split("/")[-1], p) or ("/*" in p and seg in "/" + path):
        print(f"[가드] 보호 파일 직접 편집 차단: {path}\n"
              f"사유: 이 파일 유형은 도구/사용자 절차로만 수정한다(.claude/psp.config.json guard 목록). "
              f"필요하면 사용자에게 에디터 절차를 안내할 것.", file=sys.stderr)
        sys.exit(2)

sys.exit(0)
