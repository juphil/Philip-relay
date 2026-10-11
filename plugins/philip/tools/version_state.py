"""Philip Relay 원본 저장소와 원격 릴리스 상태를 Git 인증 경로로 찾는다."""
import os
import re
import subprocess
from pathlib import Path


def semver(text):
    match = re.search(r'(?m)^v?(\d+\.\d+\.\d+)', text or '')
    return match.group(1) if match else ''


def _is_repo(path):
    return path.is_dir() and (path / '.git').exists() and (path / 'plugins/philip').is_dir()


def repository_candidates(plugin, home=None):
    """현재 소스 클론 뒤에 현재 호스트의 marketplace, 다른 호스트 순으로 반환한다."""
    plugin = Path(plugin).resolve()
    home = Path(home or Path.home()).resolve()
    candidates = []
    for parent in (plugin, *plugin.parents):
        if _is_repo(parent):
            candidates.append(parent)
            break
    codex = home / '.codex/.tmp/marketplaces/philip-relay'
    claude = home / '.claude/plugins/marketplaces/philip-relay'
    host_order = (codex, claude) if '.codex' in str(plugin).casefold() else (claude, codex)
    candidates.extend(host_order)
    unique = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if _is_repo(resolved) and resolved not in unique:
            unique.append(resolved)
    return unique


def find_source_repo(plugin, home=None):
    candidates = repository_candidates(plugin, home)
    return candidates[0] if candidates else None


def git(repo, *args, timeout=10):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def remote_head(repo):
    fields = git(repo, 'ls-remote', 'origin', 'refs/heads/main', timeout=12).split()
    return fields[0] if fields else ''


def version_at(repo, ref):
    return semver(git(repo, 'show', f'{ref}:VERSION'))


def remote_release(plugin, home=None):
    """원격 main SHA와 그 SHA의 VERSION을 찾는다. stale 첫 사본의 HEAD를 원격으로 오인하지 않는다."""
    candidates = repository_candidates(plugin, home)
    heads = []
    for repo in candidates:
        head = remote_head(repo)
        if head and head not in heads:
            heads.append(head)
    if not heads:
        return '', '', None
    head = heads[0]
    for repo in candidates:
        version = version_at(repo, head)
        if version:
            return version, head, repo
    return '', head, candidates[0] if candidates else None
