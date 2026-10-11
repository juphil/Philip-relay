# session_start.py — SessionStart 주입 훅 (플러그인판)
# 세션 시작마다 "현재 위치 + 현행 마일스톤 phase 표"를 stdout으로 출력 → 컨텍스트에 자동 삽입.
# 효과: "매 턴 todo 확인해라"라는 상비 규칙이 필요 없어짐(읽으라고 시키는 대신 읽혀서 도착).
# roadmap 경로가 다른 프로젝트는 <프로젝트>/.claude/psp.config.json 으로 지정:
#   { "roadmap": "todo/game_roadmap.md" }
# roadmap 파일이 없으면 조용히 종료(비 Philip Relay 프로젝트에서 무해).
import json, os, re, sys
from pathlib import Path

try:  # Windows 콘솔(cp949)이 한글 못 찍어 print가 죽는 것 방지(필수)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# cwd 의존 금지 — 타 cwd에서 실행되면 조용히 무출력되는 함정. 프로젝트 루트를 절대경로로 고정.
ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

roadmap_rel = "todo/roadmap.md"
try:
    cfg = json.loads((ROOT / ".claude" / "psp.config.json").read_text(encoding="utf-8-sig"))
    roadmap_rel = cfg.get("roadmap") or roadmap_rel
except Exception:
    pass

ROADMAP = ROOT / roadmap_rel

def main():
    try:
        tools = Path(__file__).resolve().parents[1] / 'tools'
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from update_notice import notice
        print(notice(ROOT))
    except Exception:
        pass
    if not ROADMAP.exists():
        return
    text = ROADMAP.read_text(encoding="utf-8", errors="ignore")

    # "현재 = <토큰>" 줄 추출
    cur = next((l for l in text.splitlines() if l.strip().startswith("현재")), "")
    print("[세션 컨텍스트 자동 주입 — todo SSOT]")
    if cur:
        print(cur.strip())

    # 상태 SSOT 표 앞부분 주입: "현재 = <토큰>"의 토큰으로 todo/<토큰>* 폴더를 찾고(mN·프로젝트명 둘 다 지원),
    # 없으면(플랫 구조) todo/index.md 로 폴백.
    idx = None
    m = re.search(r"현재\s*=\s*([A-Za-z0-9_]+)", cur or "")
    if m:
        for d in (ROOT / "todo").glob(f"{m.group(1)}*"):
            if (d / "index.md").exists():
                idx = d / "index.md"
                break
    if idx is None and (ROOT / "todo" / "index.md").exists():
        idx = ROOT / "todo" / "index.md"
    if idx:
        lines = idx.read_text(encoding="utf-8", errors="ignore").splitlines()
        print(f"\n[{idx.relative_to(ROOT).as_posix()} — 상태 표]")
        print("\n".join(lines[:40]))  # 표+변경로그 상단이면 충분

if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # 주입 실패가 세션을 막으면 안 됨
