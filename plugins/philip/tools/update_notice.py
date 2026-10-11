"""Philip Relay 설치 버전·원격 최신 버전·프로젝트 검토 버전을 짧게 표시한다."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import version_state

PLUGIN = Path(__file__).resolve().parents[1]
TTL = 24 * 60 * 60


def semver(text):
    match = re.search(r'(?m)^v?(\d+\.\d+\.\d+)', text or '')
    return match.group(1) if match else ''


def current_version():
    try:
        return json.loads((PLUGIN / '.codex-plugin/plugin.json').read_text(encoding='utf-8-sig'))['version']
    except (OSError, ValueError, KeyError):
        try:
            return json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8-sig'))['version']
        except (OSError, ValueError, KeyError):
            return ''


def version_tuple(value):
    return tuple(map(int, value.split('.'))) if re.fullmatch(r'\d+\.\d+\.\d+', value or '') else ()


def cache_path():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.cache')
    return base / 'philip-relay' / 'update-check.json'


def remote_version(force=False, plugin=PLUGIN, home=None):
    cache = cache_path()
    try:
        data = json.loads(cache.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    installed, cached = current_version(), data.get('version', '')
    local_ahead = version_tuple(installed) and version_tuple(cached) and version_tuple(installed) > version_tuple(cached)
    if not force and not local_ahead and time.time() - float(data.get('checked_at', 0)) < TTL and cached:
        return data['version'], '캐시'
    version, commit, _ = version_state.remote_release(plugin, home=home)
    if version:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({'checked_at': time.time(), 'version': version, 'commit': commit},
                                    ensure_ascii=False), encoding='utf-8')
        return version, 'Git 인증 원격'
    if commit and data.get('commit') != commit:
        return '', '원격 커밋 변경'
    return (data.get('version', ''), '오래된 캐시') if data.get('version') else ('', '오프라인')


def remote_commit_changed(plugin=PLUGIN, home=None):
    _, commit, source = version_state.remote_release(plugin, home=home)
    if not commit or not source:
        return None
    local = version_state.git(source, 'rev-parse', 'HEAD')
    return local != commit if local else None


def reviewed_version(project):
    try:
        data = json.loads((project / '.psp/runtime.json').read_text(encoding='utf-8-sig'))
        return str(data.get('psp_reviewed_version') or '')
    except (OSError, ValueError):
        return ''


def notice(project=None, force=False):
    installed = current_version() or '알 수 없음'
    remote, source = remote_version(force=force)
    parts = [f'[Philip Relay 버전] 설치 {installed}']
    if remote:
        parts.append(f'원격 {remote}({source})')
        if version_tuple(remote) > version_tuple(installed):
            parts.append('업데이트 필요: philip:updatecheck 후 플러그인 갱신')
        elif installed != remote:
            parts.append('설치본이 원격보다 앞서거나 캐시가 낡음: 배포 상태 확인')
    else:
        changed = True if source == '원격 커밋 변경' else remote_commit_changed()
        if changed is True:
            parts.append('원격 커밋 변경 감지(정확한 버전은 updatecheck 필요)')
        elif changed is False:
            parts.append('원격 커밋 동일·VERSION 조회 불가')
        else:
            parts.append('원격 확인 불가(작업 차단 안 함)')
    if project:
        reviewed = reviewed_version(Path(project))
        if reviewed:
            parts.append(f'이 프로젝트 검토 {reviewed}' + ('' if reviewed == installed else ' -> 호환성 재검토 필요'))
        elif (Path(project) / '.psp/runtime.json').is_file():
            parts.append('이 프로젝트 검토 버전 미기록')
    return ' · '.join(parts)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    print(notice(args.project, args.force))


if __name__ == '__main__':
    main()
