"""Philip Relay 외부 지식 레지스트리를 검증하고 요청 시 고정 커밋을 해석한다."""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

DOMAINS = {'game', 'web', 'research'}
MODES = {'advisory', 'required', 'profile'}
AUTHORITIES = {'user-approved', 'official', 'community', 'hypothesis'}


def validate(data):
    errors = []
    if data.get('schema_version') != 1 or not isinstance(data.get('sources'), list):
        return ['schema_version=1과 sources 배열이 필요합니다.']
    ids = set()
    for i, source in enumerate(data['sources']):
        where = f'sources[{i}]'
        required = ('id', 'domain', 'repo', 'ref', 'entry', 'authority', 'mode', 'reviewed_at', 'license')
        for key in required:
            if not source.get(key):
                errors.append(f'{where}.{key} 누락')
        sid = source.get('id')
        if sid in ids:
            errors.append(f'{where}.id 중복: {sid}')
        ids.add(sid)
        if source.get('domain') not in DOMAINS:
            errors.append(f'{where}.domain은 game/web/research 중 하나여야 합니다.')
        if source.get('mode') not in MODES:
            errors.append(f'{where}.mode가 유효하지 않습니다.')
        if source.get('authority') not in AUTHORITIES:
            errors.append(f'{where}.authority가 유효하지 않습니다.')
        if str(source.get('ref', '')).lower() in {'main', 'master', 'head', 'latest'}:
            errors.append(f'{where}.ref는 이동하는 브랜치 대신 커밋 SHA나 불변 태그여야 합니다.')
        entry = str(source.get('entry', '')).replace('\\', '/')
        if entry.startswith('/') or '..' in entry.split('/'):
            errors.append(f'{where}.entry는 저장소 내부 상대경로여야 합니다.')
        if source.get('reviewed_at') and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(source['reviewed_at'])):
            errors.append(f'{where}.reviewed_at은 YYYY-MM-DD 형식이어야 합니다.')
    return errors


def resolve(source):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', 'ls-remote', source['repo'], source['ref']], capture_output=True, text=True,
                            encoding='utf-8', timeout=20, env=env)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(f"{source['id']} ref를 해석하지 못했습니다: {result.stderr.strip()}")
    return result.stdout.split()[0]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('registry', type=Path)
    parser.add_argument('--resolve', action='store_true', help='원격 ref를 커밋 SHA로 해석해 lock 파일 작성')
    parser.add_argument('--lock', type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.registry.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        print(f'레지스트리를 읽을 수 없습니다: {exc}')
        return 1
    errors = validate(data)
    if errors:
        print('지식 레지스트리 오류:\n- ' + '\n- '.join(errors))
        return 1
    print(f'지식 레지스트리 {len(data["sources"])}개 구조 통과')
    if args.resolve:
        if not args.lock:
            print('--resolve에는 --lock 경로가 필요합니다.')
            return 1
        locked = [{'id': s['id'], 'repo': s['repo'], 'ref': s['ref'], 'commit': resolve(s), 'entry': s['entry']}
                  for s in data['sources']]
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        temp = args.lock.with_suffix(args.lock.suffix + '.tmp')
        temp.write_text(json.dumps({'schema_version': 1, 'resolved_at': date.today().isoformat(),
                                    'sources': locked}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(args.lock)
        print(f'고정 버전 {len(locked)}개 기록: {args.lock}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
