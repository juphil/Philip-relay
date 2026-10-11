"""Philip Relay 행동 사례의 실행 프롬프트 생성과 구조화 결과 채점."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def export(cases, host, out):
    lines = [f'# Philip Relay behavior evaluation: {host}', '',
             '각 사례를 독립된 새 세션에서 실행하고 실제 도구 호출까지 관찰하세요.',
             '각 결과를 JSON으로 기록하세요: case_id, observed, evidence, writes, notes.', '']
    for case in cases:
        lines += [f'## {case["id"]}', '', case['prompt'], '', f'기대 필드: {json.dumps(case["expected"], ensure_ascii=False)}', '']
    out.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{host} 실행 묶음 {len(cases)}건: {out}')


def score(cases, results):
    expected = {case['id']: case['expected'] for case in cases}
    seen, failures = set(), []
    for row in results.get('results', []):
        cid = row.get('case_id')
        if cid not in expected:
            failures.append(f'알 수 없는 case_id: {cid}')
            continue
        seen.add(cid)
        observed = row.get('observed') or {}
        for key, value in expected[cid].items():
            if observed.get(key) != value:
                failures.append(f'{cid}.{key}: 기대 {value!r}, 관찰 {observed.get(key)!r}')
    for cid in expected.keys() - seen:
        failures.append(f'결과 누락: {cid}')
    print(f'행동 평가 {len(seen)}/{len(expected)}건 기록')
    if failures:
        print('실패:\n- ' + '\n- '.join(failures))
        return 1
    print('모든 기대 행동 통과')
    return 0


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=ROOT / 'evals/behavior_cases.json')
    parser.add_argument('--export-host', choices=('claude', 'codex'))
    parser.add_argument('--out', type=Path)
    parser.add_argument('--results', type=Path)
    args = parser.parse_args()
    cases = load(args.cases)['cases']
    if args.export_host:
        if not args.out:
            parser.error('--export-host에는 --out이 필요합니다.')
        export(cases, args.export_host, args.out)
        return 0
    if args.results:
        return score(cases, load(args.results))
    for case in cases:
        print(f'{case["id"]}: {case["prompt"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
