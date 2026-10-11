"""플러그인 갱신 전에 marketplace·설치 캐시의 로컬 수정을 찾아 로컬 백업한다."""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import version_state

PLUGIN = Path(__file__).resolve().parents[1]
IGNORED_NAMES = {'.codex-marketplace-install.json', '.DS_Store'}


def _ignored(path):
    return (path.name in IGNORED_NAMES or '.in_use' in path.parts or '__pycache__' in path.parts
            or path.suffix in {'.pyc', '.pyo'})


def marketplaces(home):
    home = Path(home)
    values = [home / '.claude/plugins/marketplaces/philip-relay',
              home / '.codex/.tmp/marketplaces/philip-relay']
    return [path for path in values if (path / '.git').exists()]


def installed_caches(home):
    home, found = Path(home), []
    registry = home / '.claude/plugins/installed_plugins.json'
    try:
        rows = json.loads(registry.read_text(encoding='utf-8')).get('plugins', {}).get('philip@philip-relay', [])
        found.extend((Path(row['installPath']), str(row.get('version') or '')) for row in rows if row.get('installPath'))
    except (OSError, ValueError, TypeError):
        pass
    codex_homes = [home / '.codex']
    if os.environ.get('CODEX_HOME'):
        codex_homes.append(Path(os.environ['CODEX_HOME']))
    for codex_home in codex_homes:
        for path in (codex_home / 'plugins/cache/philip-relay/philip').glob('*'):
            if path.is_dir():
                found.append((path, path.name.split('+', 1)[0]))
    unique = []
    for path, version in found:
        item = (path.resolve(), version)
        if item not in unique:
            unique.append(item)
    return unique


def dirty_marketplace(repo):
    result = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain=v1', '-uall'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'{repo} 상태를 읽을 수 없습니다.')
    rows = []
    for line in result.stdout.splitlines():
        path = line[3:].split(' -> ')[-1].strip('"') if len(line) >= 4 else ''
        if path and Path(path).name not in IGNORED_NAMES:
            rows.append({'status': line[:2], 'path': path})
    return rows


def expected_files(source, ref):
    result = subprocess.run(['git', '-C', str(source), 'archive', '--format=zip', ref, 'plugins/philip'],
                            capture_output=True)
    if result.returncode:
        raise ValueError(f'{ref} 기준 파일을 읽을 수 없습니다.')
    prefix, files = 'plugins/philip/', {}
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
        for name in archive.namelist():
            if name.startswith(prefix) and not name.endswith('/'):
                rel = Path(name[len(prefix):])
                if not _ignored(rel):
                    files[rel.as_posix()] = archive.read(name)
    return files


def cache_drift(cache, source, version):
    expected = expected_files(source, f'v{version}')
    actual = {path.relative_to(cache).as_posix(): path.read_bytes()
              for path in cache.rglob('*') if path.is_file() and not _ignored(path.relative_to(cache))}
    changes = []
    for path in sorted(expected.keys() | actual.keys()):
        if path not in actual:
            changes.append({'status': 'missing', 'path': path})
        elif path not in expected:
            changes.append({'status': 'extra', 'path': path})
        elif actual[path] != expected[path]:
            changes.append({'status': 'modified', 'path': path})
    return changes


def _copy_existing(root, rows, destination):
    for row in rows:
        source = root / row['path']
        if source.is_file():
            target = destination / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def audit(home=None, source=None, backup_root=None):
    home = Path(home or Path.home()).resolve()
    source = Path(source).resolve() if source else version_state.find_source_repo(PLUGIN, home=home)
    findings = []
    for repo in marketplaces(home):
        try:
            rows = dirty_marketplace(repo)
        except RuntimeError as error:
            findings.append({'kind': 'marketplace-unverifiable', 'path': str(repo),
                             'error': str(error), 'changes': []})
            continue
        if rows:
            findings.append({'kind': 'marketplace', 'path': str(repo), 'changes': rows})
    if source:
        for cache, version in installed_caches(home):
            try:
                rows = cache_drift(cache, source, version)
            except ValueError as error:
                findings.append({'kind': 'cache-unverifiable', 'path': str(cache), 'version': version,
                                 'error': str(error), 'changes': []})
                continue
            if rows:
                findings.append({'kind': 'cache', 'path': str(cache), 'version': version, 'changes': rows})
    elif installed_caches(home):
        findings.append({'kind': 'source-unavailable', 'path': '', 'changes': []})
    backup = None
    if findings and backup_root:
        backup_root = Path(backup_root)
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), dir=backup_root))
        for index, finding in enumerate(findings, 1):
            root = Path(finding['path']) if finding.get('path') else None
            target = backup / f'{index:02d}-{finding["kind"]}'
            if root and root.exists():
                _copy_existing(root, finding.get('changes', []), target / 'files')
                if finding['kind'] == 'marketplace':
                    patch = subprocess.run(['git', '-C', str(root), 'diff', '--binary', 'HEAD'],
                                           capture_output=True).stdout
                    (target / 'tracked.patch').parent.mkdir(parents=True, exist_ok=True)
                    (target / 'tracked.patch').write_bytes(patch)
        (backup / 'manifest.json').write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding='utf-8')
    return findings, backup


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='philip-relay 원본 클론')
    parser.add_argument('--home', type=Path, help='검사할 사용자 홈(테스트·다른 홈용)')
    parser.add_argument('--backup-root', type=Path, help='변경 발견 시 파일·패치를 보존할 로컬 폴더')
    args = parser.parse_args()
    default_backup = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.cache') / 'psp/update-backups'
    findings, backup = audit(args.home, args.source, args.backup_root or default_backup)
    if findings:
        print(f'갱신 중단: 로컬 변경 또는 비교 불가 설치본 {len(findings)}곳')
        for finding in findings:
            print(f'- {finding["kind"]}: {finding.get("path") or "원본 없음"} ({len(finding.get("changes", []))}개)')
        if backup:
            print(f'백업: {backup}')
        return 1
    print('갱신 사전검사 통과: marketplace·설치 캐시 로컬 변경 0곳')
    return 0


if __name__ == '__main__':
    sys.exit(main())
