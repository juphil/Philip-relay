#!/usr/bin/env python3
# exp_ledger.py — 실험 대장 (범용 · philip-relay CV·DL 팩) [연구·기록]
"""매 실험의 '헤드라인 1줄'을 고정 칼럼 표에 append → 실험 이력을 한눈에 비교·회귀감지.
조합/에폭별 전수 수치는 결과파일(jsonl 등)이 소유, 여기는 실험 단위 요약 대장.
프로젝트 무관 범용: 핵심 칼럼 고정 + 하이퍼파라미터는 params(key=value;…) 자유필드.

칼럼(고정): date, exp_id, metric, value, src, rows, src_md5, params, note
  - metric/value = 헤드라인 지표(예: F1, mAP, val_acc) 이름·값
  - src/rows/src_md5 = 전수 수치 원본 파일·행수·무결성(대장→원본 역추적)
  - params = 이 실험의 스윕/설정 요약(model=x;lr=1e-3;thr=0.3 …)

사용:
  # 결과 jsonl 에서 metric 최고행 자동 기록(각 행이 metric 필드 포함 가정)
  python exp_ledger.py add --src runs/exp_a.jsonl --exp-id exp_a --metric F1 --note "..."
  # 수동
  python exp_ledger.py add --exp-id x --metric F1 --value 0.93 --params "model=arcface;thr=0.3"
  python exp_ledger.py show [--by-metric]   # 대장 출력
  python exp_ledger.py compare              # 최고 대비 델타 랭킹
  python exp_ledger.py verify               # src md5 무결성(전수 수치 변조 감지)
환경: LEDGER 경로는 --ledger 또는 EXP_LEDGER 환경변수(기본 ./LEDGER.csv).
"""
import os, sys, csv, json, argparse, datetime, hashlib

COLS = ["date", "exp_id", "metric", "value", "src", "rows", "src_md5", "params", "note"]


def _ledger_path(args):
    return getattr(args, "ledger", None) or os.environ.get("EXP_LEDGER", "LEDGER.csv")


def _md5(path):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(65536), b""):
                h.update(b)
        return h.hexdigest()[:12]
    except OSError:
        return ""


def _load(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig"))) if os.path.exists(path) else []


def _save(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def _fval(r):
    try:
        return float(r.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def add(args):
    path = _ledger_path(args)
    rows = _load(path)
    rec = {c: "" for c in COLS}
    rec.update(date=args.date or datetime.date.today().isoformat(),
               exp_id=args.exp_id, metric=args.metric,
               params=args.params or "", note=args.note or "")
    if args.src:
        recs = [json.loads(l) for l in open(args.src, encoding="utf-8") if l.strip()]
        best = max(recs, key=lambda r: r.get(args.metric, r.get("value", 0)))
        rec["value"] = best.get(args.metric, best.get("value", ""))
        rec["src"] = os.path.basename(args.src)
        rec["rows"] = len(recs)
        rec["src_md5"] = _md5(args.src)
        if not rec["params"]:                       # params 미지정이면 최고행 요약 자동
            rec["params"] = ";".join(f"{k}={v}" for k, v in best.items()
                                     if k not in (args.metric, "value", "P", "R"))[:120]
        print(f"[src] {rec['src']} {len(recs)}행 중 {args.metric} 최고 {rec['value']} (md5 {rec['src_md5']})")
    elif args.value is not None:
        rec["value"] = args.value
    # 비교 + 회귀 경고
    prev = [r for r in rows if r.get("metric") == args.metric and r.get("value")]
    if prev:
        bp = max(prev, key=_fval)
        d = _fval(rec) - _fval(bp)
        tag = "▲개선" if d > 5e-4 else ("▼회귀 ★" if d < -5e-4 else "≈동급")
        print(f"[비교] {args.metric} {rec['value']} vs 직전최고 {bp['value']}({bp['exp_id']})  Δ{d:+.4f}  {tag}")
        if d < -5e-4:
            print("  ★회귀 — 왜 내렸나 원인 귀속(/psp_judge). 무엇을 바꿨는지 조건 대조.")
    rows.append(rec)
    _save(path, rows)
    print(f"[대장] {path} (총 {len(rows)}줄)")


def show(args):
    rows = _load(_ledger_path(args))
    if not rows:
        print("대장 비어있음."); return
    if args.by_metric:
        rows.sort(key=_fval, reverse=True)
    key = ["date", "exp_id", "metric", "value", "rows", "src", "note"]
    w = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in key}
    print("  " + " ".join(f"{c:<{w[c]}}" for c in key))
    for r in rows:
        print("  " + " ".join(f"{str(r.get(c,'')):<{w[c]}}" for c in key))


def compare(args):
    rows = [r for r in _load(_ledger_path(args)) if r.get("value")]
    if not rows:
        print("비교할 실험 없음."); return
    rows.sort(key=_fval, reverse=True)
    best = rows[0]
    print(f"최고: {best['metric']} {best['value']}  [{best['exp_id']}]  {best.get('params','')}  (src {best.get('src')})")
    for r in rows:
        print(f"  {r['exp_id']:<16} {r['value']:<9} Δ{_fval(r)-_fval(best):+.4f}  [{r.get('note','')}]")


def verify(args):
    path = _ledger_path(args); base = os.path.dirname(os.path.abspath(path)) or "."
    ok = bad = miss = 0
    for r in _load(path):
        src = r.get("src")
        if not src:
            continue
        p = os.path.join(base, src)
        if not os.path.exists(p):
            print(f"  ✗ 원본 없음: {src} [{r.get('exp_id')}]"); miss += 1
        elif r.get("src_md5") and _md5(p) != r.get("src_md5"):
            print(f"  ✗ 변조: {src} [{r.get('exp_id')}]"); bad += 1
        else:
            ok += 1
    print(f"무결성: 일치 {ok} · 불일치 {bad} · 원본없음 {miss}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--exp-id", required=True); a.add_argument("--metric", default="F1")
    a.add_argument("--src"); a.add_argument("--value"); a.add_argument("--params")
    a.add_argument("--date", default=""); a.add_argument("--note", default="")
    a.set_defaults(func=add)
    s = sub.add_parser("show"); s.add_argument("--by-metric", action="store_true"); s.set_defaults(func=show)
    sub.add_parser("compare").set_defaults(func=compare)
    sub.add_parser("verify").set_defaults(func=verify)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
