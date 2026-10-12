# -*- coding: utf-8 -*-
"""
mem_sync.py — 클로드 메모리 이식(portable memory): 로컬 메모리 폴더 <-> private git 레포(슬러그 폴더)

문제: 클로드 메모리는 `~/.claude/projects/<절대경로 인코딩>/memory/` 에 저장 = 머신·경로 종속.
해결: 안정적 slug 로 private git 레포에 두고, 각 머신에서 그 머신의 로컬 메모리 폴더로 랜딩.

사용:
  push : 로컬 메모리 -> 레포/.psp-collections/<slug>/<collection>/ (collection 생략 시 기존 레포/<slug>/)
         --gitpush: commit 후 원격 먼저 pull --rebase 통합→push(멀티PC 거부 방지)
  pull : 위 저장 경로 -> 로컬 메모리 (덮어쓰기 전 백업, 삭제 전파 없음)

  python mem_sync.py push --repo <레포경로> --slug <slug> --memdir <로컬 메모리 폴더>
  python mem_sync.py pull --repo <레포경로> --slug <slug> --memdir <로컬 메모리 폴더> [--backup <백업루트>]

동기화 대상: *.md + .obsidian/{app,core-plugins,community-plugins}.json (설정만).
제외: .obsidian/workspace.json(기기별)·plugins/*/(바이너리, 재설치 가능).
프라이버시: 레포는 반드시 private. 원문 시크릿(키·비번)은 메모리에 두지 말 것.
"""
import sys, os, re, glob, shutil, argparse, subprocess, time, io, socket, json, tempfile
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

OBS_CFG = ["app.json", "core-plugins.json", "community-plugins.json"]

def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')

def git_relative(path, repo):
    """Return a repository-relative POSIX path suitable for Git pathspecs."""
    return Path(path).resolve().relative_to(Path(repo).resolve()).as_posix()

def claude_home():
    """`~/.claude` 의 진짜 위치. Windows 는 USERPROFILE 기준(HOME 이 다른 곳으로 잡힌 머신이 있다 —
    실측: HOME=%APPDATA%\\SPB_Data 라 Git Bash 의 `~` 가 사용자 폴더가 아니었고, 문서대로 친
    `~/.claude/claude-memory` 가 엉뚱한 위치에 레포를 하나 더 만들었다)."""
    base = os.environ.get("USERPROFILE") if os.name == "nt" else None
    return os.path.join(base or os.path.expanduser("~"), ".claude")

def default_repo():
    return os.path.join(claude_home(), "claude-memory")

def norm_path(p):
    """경로 정규화 — expanduser + (Windows에서) MSYS/Cygwin 경로를 네이티브로.
    Git Bash 는 `~` 를 셸이 먼저 `/c/Users/...` 로 펴버려서 expanduser 로는 못 잡는다.
    그 상태로 subprocess cwd 에 넘기면 엉뚱한 위치에서 git 이 돌아 조용히 실패한다(실측)."""
    if not p:
        return p
    p = os.path.expanduser(p)
    if os.name == "nt":
        m = re.match(r"^/(?:cygdrive/)?([A-Za-z])(/.*)?$", p)
        if m:
            p = m.group(1).upper() + ":" + (m.group(2) or "/")
        p = os.path.normpath(p)
    return p

def _json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def resolve_project_defaults(a):
    """명시 인자가 없을 때 프로젝트 설정과 머신 기본값에서 url·slug·단일 메모리 폴더를 푼다."""
    project = Path(getattr(a, 'project', None) or os.getcwd()).resolve()
    cfg = _json(project / '.claude/psp.config.json') or _json(project / '.codex/psp.config.json')
    memory = cfg.get('memory') if isinstance(cfg.get('memory'), dict) else {}
    if not getattr(a, 'url', None):
        a.url = memory.get('url')
        default_url = Path(claude_home()) / 'memory_repo.txt'
        if not a.url and default_url.is_file():
            a.url = default_url.read_text(encoding='utf-8-sig').splitlines()[0].strip()
    if not getattr(a, 'slug', None):
        a.slug = memory.get('slug') or project.name
    if not getattr(a, 'memdir', None):
        runtime = _json(project / '.psp/runtime.json')
        dirs = runtime.get('memory_dirs', [])
        if isinstance(dirs, list) and len(dirs) == 1:
            candidate = Path(dirs[0])
            a.memdir = str(candidate if candidate.is_absolute() else project / candidate)
        elif isinstance(dirs, list) and len(dirs) > 1:
            # 여러 폴더 중 하나를 추측해 고르면 다른 묶음의 인덱스를 덮어쓸 수 있다(10-11 실측: 3개 중 작은 memory/ 선택 → 원격 MEMORY.md 71항목을 1항목으로 덮어쓰는 계획).
            raise ValueError('runtime memory_dirs가 여러 개라 메모리 폴더를 추측하지 않습니다. --memdir(추가 폴더면 --collection도)를 명시하세요: '
                             + ', '.join(map(str, dirs)))
        elif (project / 'memory').is_dir():
            a.memdir = str(project / 'memory')
        else:
            raise ValueError('--memdir를 생략하려면 프로젝트에 단일 memory_dirs 또는 memory/ 폴더가 있어야 합니다.')
    return a

def ensure_repo(repo, url):
    """레포 로컬 클론이 없으면 url 로 clone. 스킬이 git 을 대신 처리(사용자는 git 안 침)."""
    if os.path.isdir(os.path.join(repo, ".git")):
        return True
    if not url:
        print("레포 로컬 클론 없음 & --url 미제공:", repo); return False
    parent = os.path.dirname(repo.rstrip("/\\")) or "."
    os.makedirs(parent, exist_ok=True)
    r = sh(["git", "clone", url, repo], parent)
    print("clone %s -> %s : %s" % (url, repo, "ok" if r.returncode == 0 else r.stderr.strip()))
    return r.returncode == 0

def machine_name(override):
    """출처 태그: --machine > ~/.claude/machine.txt > 호스트명."""
    if override:
        return override
    mf = os.path.join(claude_home(), "machine.txt")
    try:
        if os.path.isfile(mf):
            n = open(mf, encoding="utf-8").read().strip()
            if n:
                return n
    except Exception:
        pass
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"

def copy_md_and_cfg(src, dst, mirror=False):
    """src -> dst 로 *.md + .obsidian 설정만 복사. mirror=True 면 src에 없는 dst의 *.md 삭제(삭제 전파).
    반환: (복사한 md 리스트, 삭제한 md 리스트)."""
    os.makedirs(dst, exist_ok=True)
    src_names = {os.path.basename(f) for f in glob.glob(os.path.join(src, "*.md"))}
    removed = []
    if mirror:
        for f in glob.glob(os.path.join(dst, "*.md")):
            if os.path.basename(f) not in src_names:
                os.remove(f); removed.append(os.path.basename(f))
    md = []
    for f in glob.glob(os.path.join(src, "*.md")):
        shutil.copy2(f, os.path.join(dst, os.path.basename(f)))
        md.append(os.path.basename(f))
    scfg = os.path.join(src, ".obsidian")
    if os.path.isdir(scfg):
        dcfg = os.path.join(dst, ".obsidian"); os.makedirs(dcfg, exist_ok=True)
        for c in OBS_CFG:
            p = os.path.join(scfg, c)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(dcfg, c))
    return sorted(md), sorted(removed)

def backup(memdir, backup_root):
    if not os.path.isdir(memdir) or not glob.glob(os.path.join(memdir, "*.md")):
        return ""   # 로컬 비었음(새 머신) = 백업할 것 없음
    os.makedirs(backup_root, exist_ok=True)
    bk = tempfile.mkdtemp(prefix='membackup_', dir=backup_root)
    shutil.copytree(memdir, bk, dirs_exist_ok=True)
    return bk

def cmd_push(a):
    slugdir = sync_target(a)
    if not a.apply and not os.path.isdir(os.path.join(a.repo, '.git')):
        print('로컬 저장소가 없어 비교할 수 없습니다. 승인된 clone 후 계획을 재확인하세요.'); return 2
    if not ensure_repo(a.repo, getattr(a, "url", None)):
        return 3
    if not os.path.isdir(a.memdir):
        print("메모리 폴더 없음:", a.memdir); return 2
    slugdir = sync_target(a)
    changes = safe_transfer(a.memdir, slugdir, a)
    if changes is None:
        return 0
    paths = [git_relative(target, a.repo) for _, target, _ in changes]
    if paths:
        dirty = sh(['git', 'status', '--porcelain', '--', *paths], a.repo)
        if dirty.returncode or dirty.stdout.strip():
            print('적용 대상에 기존 미커밋 변경이 있습니다. 충돌 확인 후 다시 실행하세요.')
            return 5
        apply_transfer(changes)
        r = sh(['git', 'add', '--', *paths], a.repo)
        if r.returncode:
            print('git add 실패:', r.stderr.strip()); return 5
        mach = machine_name(getattr(a, 'machine', None))
        c = sh(['git', 'commit', '--only', '-m', 'mem push %s @%s %s' %
                (a.slug, mach, time.strftime('%Y-%m-%d %H:%M')), '--', *paths], a.repo)
        if c.returncode:
            message = (c.stdout.strip() + '\n' + c.stderr.strip()).strip() or f'git 종료 코드 {c.returncode}'
            print('커밋 실패 — push 중단:', message); return 5
        print('계획에 포함된 파일만 커밋했습니다.')
    else:
        print('파일 변경 없음. 요청된 원격 전송은 별도로 확인합니다.')
    # A failed earlier commit can leave equal files in the index/worktree.
    expected_paths = [git_relative(Path(slugdir) / p.relative_to(Path(a.memdir)), a.repo)
                      for p in Path(a.memdir).rglob('*.md')]
    if expected_paths:
        pending = sh(['git', 'status', '--porcelain', '--', *expected_paths], a.repo)
        if pending.returncode or pending.stdout.strip():
            print('메모리 파일의 미커밋 변경이 남아 있어 전송을 중단합니다. 커밋 실패 원인을 해결하세요.')
            return 5
    if a.gitpush:
        # ★원격 먼저 통합(다른 머신이 push했을 수 있음) 후 push — non-fast-forward 거부 방지
        has_remote = bool(sh(["git", "remote"], a.repo).stdout.strip())
        if has_remote:
            pr = sh(["git", "pull", "--rebase", "--autostash"], a.repo)
            if pr.returncode != 0:
                sh(["git", "rebase", "--abort"], a.repo)
                print("git pull --rebase 실패(충돌 가능) — push 중단, 수동 확인 필요:", pr.stderr.strip()[:200])
                return 4
            p = sh(["git", "push"], a.repo)
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
            if p.returncode != 0:
                return 4
        else:
            print('원격이 없어 요청한 전송을 완료하지 못했습니다.'); return 4
    else:
        print("(원격 push 생략 — --gitpush 로 켜거나 레포에서 직접 push)")
    return 0

def cmd_pull(a):
    sync_target(a)
    if not a.apply and not os.path.isdir(os.path.join(a.repo, '.git')):
        print('로컬 저장소가 없어 비교할 수 없습니다. 승인된 clone 후 계획을 재확인하세요.'); return 2
    fresh = not os.path.isdir(os.path.join(a.repo, ".git"))
    if not ensure_repo(a.repo, getattr(a, "url", None)):
        return 3
    slugdir = sync_target(a)
    if a.gitpull and a.apply and not fresh:
        p = sh(["git", "pull"], a.repo)
        print("git pull:", "ok" if p.returncode == 0 else p.stderr.strip())
        if p.returncode != 0:
            return 4
    if not os.path.isdir(slugdir):
        print("레포에 slug 없음:", slugdir); return 2
    changes = safe_transfer(slugdir, a.memdir, a)
    if changes is None:
        return 0
    # ★로컬 먼저 백업(메모리 손실 방지)
    broot = a.backup or os.path.join(os.path.dirname(a.memdir.rstrip("/\\")), "_membackup")
    bk = backup(a.memdir, broot)
    print("로컬 백업:", bk if bk else "(로컬 없음=새 머신)")
    # 덮어쓰기 경고: 로컬과 다른 파일
    diffs = []
    for f in glob.glob(os.path.join(slugdir, "*.md")):
        lf = os.path.join(a.memdir, os.path.basename(f))
        if os.path.isfile(lf) and open(lf, "rb").read() != open(f, "rb").read():
            diffs.append(os.path.basename(f))
    apply_transfer(changes)
    md, removed = [r for _, _, r in changes], []
    print("pull: %d개 md -> %s" % (len(md), a.memdir))
    if diffs:
        print("⚠ 로컬과 달라 덮어쓴 파일(%d): %s  (백업에서 복구 가능)" % (len(diffs), ", ".join(diffs)))
    if removed:
        print("⚠ 레포에 없어 로컬서 삭제한 파일(%d): %s  (백업에서 복구 가능)" % (len(removed), ", ".join(removed)))
    return 0

def sync_target(a):
    parts = [a.slug] + ([a.collection] if getattr(a, 'collection', None) else [])
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', p) for p in parts):
        raise ValueError('slug와 collection은 영문·숫자·밑줄·하이픈만 허용합니다.')
    repo = Path(a.repo).resolve()
    if getattr(a, 'collection', None):
        legacy = repo.joinpath(*parts)
        target = repo.joinpath('.psp-collections', *parts).resolve()
        if legacy.exists():
            raise ValueError(f'구 컬렉션 경로가 있습니다: {legacy}. 기존 루트 메모리와 섞일 수 있으므로 백업 후 새 경로 {target}로 별도 이관하세요. 자동 이동하지 않습니다.')
    else:
        target = repo.joinpath(*parts).resolve()
    if not target.is_relative_to(repo):
        raise ValueError('동기화 대상이 저장소 밖을 가리킵니다.')
    return str(target)


def safe_transfer(src, dst, a):
    """Preview before mutation. Never propagate deletions; back up replacements."""
    source, dest = Path(src).resolve(), Path(dst).resolve()
    if source == dest or source.is_relative_to(dest) or dest.is_relative_to(source):
        raise ValueError('원본과 대상 경로는 서로 포함될 수 없습니다.')
    files = list(source.rglob('*.md'))
    files += [source / '.obsidian' / name for name in OBS_CFG if (source / '.obsidian' / name).is_file()]
    changes = []
    for file in files:
        rel = file.relative_to(source)
        target = dest / rel
        if file.is_symlink() or not file.resolve().is_relative_to(source) or target.is_symlink() or not target.resolve().is_relative_to(dest):
            raise ValueError('심볼릭 링크를 통한 동기화는 지원하지 않습니다.')
        if not target.exists() or target.read_bytes() != file.read_bytes():
            changes.append((file, target, str(rel)))
    dropped = index_drops(source, dest, changes)
    if dropped and not getattr(a, 'allow_index_drop', False):
        raise ValueError('MEMORY.md 를 덮어쓰면 대상 폴더에 남아 있는 메모리 %d개가 인덱스에서 빠집니다(예: %s). '
                         '원본·대상 폴더가 맞는지 확인하고, 의도한 경우에만 --allow-index-drop 을 붙이세요.'
                         % (len(dropped), ', '.join(dropped[:5])))
    print(json.dumps({'source': str(source), 'target': str(dest),
                      'write': [r for _, _, r in changes], 'delete': [],
                      'retained': sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*.md') if not (source / p.relative_to(dest)).exists())}, ensure_ascii=False))
    if not getattr(a, 'apply', False):
        print('계획만 확인했습니다. 확인한 계획 적용은 --apply를 사용하세요.')
        return None
    existing = [(f, t, r) for f, t, r in changes if t.exists()]
    if existing:
        backup_dir = Path(tempfile.mkdtemp(prefix='psp-memory-backup-'))
        for _, target, rel in existing:
            saved = backup_dir / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        print('덮어쓰기 전 백업:', backup_dir)
    return changes


def _index_links(path):
    try:
        text = path.read_text(encoding='utf-8-sig')
    except OSError:
        return set()
    return {m.group(1).split('#', 1)[0] for m in re.finditer(r'\]\(([^)\s]+\.md)(?:#[^)]*)?\)', text)}


def index_drops(source, dest, changes):
    """MEMORY.md 덮어쓰기로, 대상에 남는(삭제 비전파) 파일을 가리키던 링크가 사라지는지 본다."""
    if not any(rel == 'MEMORY.md' for _, _, rel in changes):
        return []
    old, new = _index_links(dest / 'MEMORY.md'), _index_links(source / 'MEMORY.md')
    return sorted(link for link in old - new if (dest / link).is_file() and not (source / link).exists())


def apply_transfer(changes):
    for source, target, _ in changes:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Preserve content and permissions, but not the source mtime. Copying the mtime can let
        # Git's stat cache miss a same-size change during rapid consecutive syncs.
        shutil.copyfile(source, target)
        shutil.copymode(source, target)
        if source.read_bytes() != target.read_bytes():
            raise OSError(f'동기화 내용 검증 실패: {target}')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    for m in ("push", "pull"):
        s = sub.add_parser(m)
        s.add_argument('--project', help='url·slug·단일 메모리 폴더 기본값을 읽을 프로젝트 루트(기본=현재 폴더)')
        s.add_argument("--repo", help="레포 로컬 클론 경로(기본=<USERPROFILE>/.claude/claude-memory, 없으면 --url 로 자동 clone). "
                                      "★셸이 편 `~` 를 넘기지 말 것 — HOME 이 사용자 폴더가 아닌 머신에서 엉뚱한 위치에 클론이 생긴다(실측)")
        s.add_argument("--url", help="private git 레포 URL — 로컬 클론이 없을 때 자동 clone용")
        s.add_argument("--slug", help="프로젝트 안정 슬러그(생략=config memory.slug > 프로젝트 폴더명)")
        s.add_argument("--memdir", help="로컬 메모리 폴더(생략=runtime의 단일 memory_dirs > memory_dirs 없을 때 프로젝트 memory/. 여러 개면 명시 필수)")
        s.add_argument('--collection', help='폴더별 고정 이름. 생략하면 기존 slug 경로를 사용')
        s.add_argument('--apply', action='store_true', help='계획 확인 후 복사 적용. 삭제는 전파하지 않음')
        s.add_argument('--allow-index-drop', action='store_true',
                       help='MEMORY.md 덮어쓰기로 대상에 남는 메모리가 인덱스에서 빠지는 것을 의도적으로 허용')
        if m == "push":
            s.add_argument("--gitpush", action="store_true", help="commit 후 원격 push 까지")
            s.add_argument("--machine", help="출처 머신 이름(기본=~/.claude/machine.txt 또는 호스트명)")
        else:
            s.add_argument("--gitpull", action="store_true", help="복사 전 git pull")
            s.add_argument("--backup", help="백업 루트(기본=메모리 폴더 옆 _membackup)")
    a = ap.parse_args()
    try:
        resolve_project_defaults(a)
    except ValueError as error:
        print("중단:", error)
        sys.exit(6)
    # ★ 경로 정규화: ~ 확장(셸이 안 펴는 PowerShell) + MSYS 경로 환산(셸이 이미 편 Git Bash)
    a.repo = norm_path(a.repo) if a.repo else default_repo()
    a.memdir = norm_path(a.memdir)
    if getattr(a, "backup", None):
        a.backup = norm_path(a.backup)
    try:
        sys.exit(cmd_push(a) if a.mode == "push" else cmd_pull(a))
    except ValueError as error:   # 계획 단계 안전 거부(경로 포함·심볼릭 링크·인덱스 손실) — 아무것도 바꾸지 않은 상태
        print("중단:", error)
        sys.exit(6)
