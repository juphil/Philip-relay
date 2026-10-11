# behavior_reminder.py — 구방식용 사건 기반 행동 포인터 훅(UserPromptSubmit)
# 시간마다 전체 문서를 재주입하지 않는다. 규칙 내용이 바뀐 경우에만 관련 원본 재독을 알린다.
import hashlib
import json
import os
import sys
from pathlib import Path

try:  # Windows 콘솔(cp949)이 한글 못 찍어 print가 죽는 것 방지(필수 — session_start와 동일)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
rules = [ROOT / x for x in ('AGENTS.md', 'CLAUDE.md') if (ROOT / x).is_file()]
if not rules:
    sys.exit(0)

state_path = ROOT / '.psp/.behavior_state.json'
digest = hashlib.sha256(b'\0'.join(p.read_bytes() for p in rules)).hexdigest()
try:
    state = json.loads(state_path.read_text(encoding='utf-8'))
except Exception:
    state = {}
if state.get('rules_hash') == digest:
    sys.exit(0)
try:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({'rules_hash': digest}), encoding='utf-8')
except Exception:
    pass

print("[행동매뉴얼 변경 감지] 프로젝트 규칙과 연결된 원본 중 이번 작업에 관련된 부분을 다시 읽으세요.")
sys.exit(0)
