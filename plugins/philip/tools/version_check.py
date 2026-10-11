"""Philip Relay 버전 점검 — 플러그인을 고치거나 갱신하기 전에 먼저 실행한다.

원본(GitHub juphil/Philip-relay main) · 로컬 클론 · 설치본(클로드·코덱스)의 버전을 한 표로 보여 주고
다음을 판정한다(SemVer MAJOR.MINOR.PATCH, 단일 버전 = 매니페스트 4곳 + VERSION 맨 위 + git 태그).
  1. 버전 표기 일치: portable = 클로드 = 코덱스 plugin.json = marketplace.json = VERSION 맨 위
  2. 태그: 현재 버전 태그(vX.Y.Z)가 있고, 태그 뒤에 plugins/philip 를 바꾼 커밋이 없는가(있으면 버전 미증가)
  3. 원격: 로컬 클론이 GitHub 원본과 같은가(뒤처짐·앞섬)
  4. 설치본: 이 PC 에 설치된 버전이 GitHub 원본 버전과 같은가
문제가 하나라도 있으면 종료 코드 1.

사용: python version_check.py [--no-fetch]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # philip-relay
PLUGIN = ROOT / 'plugins' / 'philip'
SEMVER = re.compile(r'^\d+\.\d+\.\d+$')


def git(*args):
    r = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, encoding='utf-8')
    return r.stdout.strip() if r.returncode == 0 else ''


def jver(text):
    try:
        data = json.loads(text)
    except ValueError:
        return ''
    if 'plugins' in data:                               # marketplace.json
        return next((p.get('version', '') for p in data['plugins'] if p.get('name') == 'philip'), '')
    return data.get('version', '')


def versions_at(ref=None):
    def read(rel):
        if ref:
            return git('show', f'{ref}:{rel}')
        p = ROOT / rel
        return p.read_text(encoding='utf-8-sig') if p.is_file() else ''
    top = next((l for l in read('VERSION').splitlines() if l.strip()), '')
    m = re.match(r'v?(\d+\.\d+\.\d+)', top)
    return {'휴대형 매니페스트': jver(read('plugins/philip/plugin.json')),
            '클로드 매니페스트': jver(read('plugins/philip/.claude-plugin/plugin.json')),
            '코덱스 매니페스트': jver(read('plugins/philip/.codex-plugin/plugin.json')),
            '마켓플레이스': jver(read('.claude-plugin/marketplace.json')),
            'VERSION 맨 위': m.group(1) if m else ''}


def _semver_key(value):
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else (-1, -1, -1)


def installed(home=None):
    out = {}
    user_home = Path(home or Path.home())
    reg = user_home / '.claude' / 'plugins' / 'installed_plugins.json'
    try:
        for key, rows in json.loads(reg.read_text(encoding='utf-8')).get('plugins', {}).items():
            if key.startswith('philip@'):
                for r in rows:
                    out[f'클로드 설치본({r.get("scope", "?")})'] = f'{r.get("version", "?")} · 커밋 {str(r.get("gitCommitSha", ""))[:7]}'
    except (OSError, ValueError):
        pass
    homes = {user_home / '.codex'}                     # 기본 코덱스 홈 + 실행 환경이 지정한 홈(Orca 등) 둘 다
    if os.environ.get('CODEX_HOME'):
        homes.add(Path(os.environ['CODEX_HOME']))
    for home in sorted(homes):
        cache = home / 'plugins' / 'cache'
        candidates = list(cache.glob('*/philip/*')) if cache.is_dir() else []
        if candidates:
            d = max(candidates, key=lambda path: (_semver_key(path.name), path.name))
            label = '기본' if home == user_home / '.codex' else home.parent.parent.name
            out[f'코덱스 설치본({label})'] = d.name
    return out


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-fetch', action='store_true')
    a = ap.parse_args()
    problems = []
    if not a.no_fetch:
        git('fetch', '-q', '--tags', 'origin')
    local, remote = versions_at(), versions_at('origin/main')
    print('■ 버전 표기(SemVer, 5곳 일치해야 함)')
    print(f'  {"위치":<14} {"로컬 클론":<12} GitHub 원본(origin/main)')
    for k in local:
        print(f'  {k:<14} {local[k] or "-":<12} {remote.get(k) or "-"}')
    core = {k: v.split('+', 1)[0] for k, v in local.items()}   # 코덱스 캐시용 빌드 표기(+codex.<시각>)는 SemVer 상 비교 제외
    missing = [k for k, v in core.items() if not v]
    if missing:
        problems.append(f'버전 표기 없음: {", ".join(missing)}')
    if len(set(v for v in core.values() if v)) != 1:
        problems.append(f'로컬 버전 표기 불일치: {local}')
    if any(v and not SEMVER.match(v) for v in core.values()):
        problems.append('SemVer(X.Y.Z) 형식이 아닌 표기가 있음')
    ver = core['휴대형 매니페스트']
    rver = remote['휴대형 매니페스트'].split('+', 1)[0]
    remote_core = {k: v.split('+', 1)[0] for k, v in remote.items()}
    if len(set(v for v in remote_core.values() if v)) != 1:
        problems.append(f'GitHub 원본 버전 표기 불일치: {remote}')
    if ver and rver and ver != rver:
        problems.append(f'로컬 배포 후보 {ver}와 GitHub 원본 {rver}가 다름 — 아직 배포·동기화 완료 아님')

    tag = git('describe', '--tags', '--abbrev=0', '--match', 'v*')
    since = git('rev-list', '--count', f'{tag}..HEAD', '--', 'plugins/philip', '.claude-plugin') if tag else ''
    current_tag = bool(git('tag', '--list', f'v{ver}'))
    print(f'\n■ 태그: 최근 {tag or "없음"} · 그 뒤 플러그인 변경 커밋 {since or "?"}개 · 현재 버전 태그 v{ver} {"있음" if current_tag else "없음"}')
    if not tag:
        problems.append('버전 태그 없음')
    if ver and not current_tag:
        problems.append(f'현재 버전 태그 v{ver} 없음')
    elif since not in ('', '0') and (tag == f'v{ver}'):
        problems.append(f'{tag} 뒤 플러그인 변경 {since}개인데 버전 미증가')
    dirty = git('status', '--porcelain', '--', 'plugins/philip', '.claude-plugin')
    if dirty:
        print(f'  커밋 안 된 플러그인 변경 {len(dirty.splitlines())}개(아직 배포 전)')

    behind = git('rev-list', '--count', 'HEAD..origin/main') or '?'
    ahead = git('rev-list', '--count', 'origin/main..HEAD') or '?'
    print(f'\n■ 원격: 로컬 클론이 GitHub 보다 뒤처짐 {behind}개 · 앞섬 {ahead}개')
    if behind not in ('0', '?'):
        problems.append(f'로컬 클론이 GitHub 원본보다 {behind}개 뒤처짐 — 먼저 받을 것(philip:git pull)')
    if ahead not in ('0', '?'):
        problems.append(f'로컬 클론이 GitHub 원본보다 {ahead}개 앞섬 — 아직 push 반영 안 됨')

    print('\n■ 이 PC 설치본')
    inst = installed()
    head = git('rev-parse', 'origin/main')
    for k, v in inst.items():
        iv = v.split(' ')[0].split('+', 1)[0]
        sha = v.split('커밋 ')[-1] if '커밋 ' in v else ''
        if iv != rver:
            mark = f'GitHub {rver} 과 다름 → 갱신 필요'
        elif sha and head and not head.startswith(sha):
            behind_inst = git('rev-list', '--count', f'{sha}..origin/main', '--', 'plugins/philip', '.claude-plugin') or '?'
            mark = f'버전은 같지만 GitHub 보다 플러그인 커밋 {behind_inst}개 뒤(버전 미증가 변경) → 갱신 필요'
        else:
            mark = '최신'
        print(f'  {k}: {v}  → {mark}')
        if mark != '최신':
            problems.append(f'{k}: {mark}')
    if not inst:
        print('  설치본 없음')
    print('\n■ 판정: ' + ('이상 없음' if not problems else '조치 필요'))
    for p in problems:
        print(f'  - {p}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
