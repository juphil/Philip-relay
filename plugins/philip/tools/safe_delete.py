"""기본은 되돌릴 수 있는 삭제, 명시적으로 승인된 정확한 대상은 영구 삭제도 지원한다.

psp 공통 규칙 '삭제·덮어쓰기 = 미리보기 → 재검토 → 되돌릴 수 있는 방식'의 실행 도구.
기본 실행은 미리보기만 한다(무엇이 몇 개·얼마나 옮겨지는지). 목록을 다시 읽고 의도한 것만 있을 때
같은 명령에 --yes 를 붙여 실행한다.

옮기는 곳
- 휴지통: Windows 고정 디스크 + 항목당 1GB 이하일 때만. 휴지통 용량 초과·이동식 디스크(USB)에서는
  Windows 가 묻지 않고 영구 삭제할 수 있어서 그 경우는 격리 폴더로 보낸다.
- 격리 폴더: 같은 드라이브의 <프로젝트 루트>/_quarantine/<YYYYMMDD_HHMMSS>/<원래 상대 경로>
  (프로젝트 밖이면 <드라이브>/_psp_quarantine/...). manifest.tsv 에 원래 경로·크기·SHA-256 기록.
  --restore <세션> 으로 원위치 복원, --purge-older-than <일> 로 보존 기간이 지난 세션만 비운다(최소 30일).

사용
  python safe_delete.py <경로...>                 # 미리보기
  python safe_delete.py <경로...> --yes           # 실행(휴지통 우선, 안 되면 격리)
  python safe_delete.py <경로...> --quarantine --yes   # 격리 폴더로만
  python safe_delete.py <경로...> --permanent          # 영구 삭제 미리보기
  python safe_delete.py <경로...> --permanent --confirmed-by-user --yes
  python safe_delete.py --list [--root R]          # 격리 세션 목록
  python safe_delete.py --restore 20261008_103000 --yes
  python safe_delete.py --purge-older-than 30 --yes
"""
import argparse
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RECYCLE_MAX_BYTES = 1 << 30          # 항목당 1GB 초과는 휴지통 대신 격리(휴지통 용량 초과 시 영구 삭제 위험)
HASH_MAX_BYTES = 200 << 20           # 200MB 이하 파일만 SHA-256 기록(큰 파일은 크기·수정시각)
MIN_PURGE_DAYS = 30
QDIR = '_quarantine'


def project_root(start):
    env = os.environ.get('CLAUDE_PROJECT_DIR')
    if env and Path(env).is_dir():
        return Path(env).resolve()
    try:
        out = subprocess.run(['git', '-C', str(start), 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def tree_size(p):
    if p.is_file() or p.is_symlink():
        return p.lstat().st_size, 1
    total = count = 0
    for dp, _, fn in os.walk(p):
        for f in fn:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
                count += 1
            except OSError:
                pass
    return total, count


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def fixed_drive(p):
    if os.name != 'nt':
        return False
    drive = os.path.splitdrive(str(p))[0] + '\\'
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(drive) == 3   # DRIVE_FIXED
    except Exception:
        return False


def to_recycle_bin(p):
    """Windows 셸 휴지통 이동(FOF_ALLOWUNDO). 성공 = 원래 경로가 사라졌는지로 판정."""
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd', ctypes.c_void_p), ('wFunc', ctypes.c_uint), ('pFrom', ctypes.c_wchar_p),
                    ('pTo', ctypes.c_wchar_p), ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', ctypes.c_int),
                    ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', ctypes.c_wchar_p)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, str(p) + '\0\0', None,
                         FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, 0, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted and not p.exists()


def quarantine_base(p, root):
    if root and os.path.splitdrive(str(root))[0].lower() == os.path.splitdrive(str(p))[0].lower():
        try:
            p.relative_to(root)
            return root / QDIR, p.relative_to(root)
        except ValueError:
            pass
    drive = Path(os.path.splitdrive(str(p))[0] + os.sep)
    return drive / '_psp_quarantine', Path(*p.parts[1:])


def to_quarantine(p, root, session):
    base, rel = quarantine_base(p, root)
    dest = base / session / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    files = [p] if p.is_file() else [Path(dp) / f for dp, _, fn in os.walk(p) for f in fn]
    for f in files:
        try:
            st = f.stat()
            digest = sha256(f) if st.st_size <= HASH_MAX_BYTES else '-'
            rows.append(f'{f}\t{st.st_size}\t{time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}\t{digest}')
        except OSError:
            rows.append(f'{f}\t?\t?\t-')
    shutil.move(str(p), str(dest))
    origin = base / session / 'origin_root.txt'            # 복원 기준 경로(프로젝트 루트 또는 드라이브 루트)
    if not origin.exists():
        origin.write_text(str(base.parent) if base.name == QDIR else p.anchor, encoding='utf-8')   # 프로젝트 루트 / 드라이브 루트(C:\)
    with open(base / session / 'manifest.tsv', 'a', encoding='utf-8') as m:
        if m.tell() == 0:
            m.write('원래경로\t크기\t수정시각\tSHA-256\n')
        m.write('\n'.join(rows) + '\n')
    return dest


def _protected_permanent_root(path, root):
    """실수 비용이 지나치게 큰 광범위 루트는 대화 승인과 별개로 이 도구에서 다루지 않는다."""
    path = path.resolve()
    protected = {Path(path.anchor).resolve(), Path.home().resolve()}
    if root:
        protected.add(Path(root).resolve())
    return path in protected


def remove(paths, yes, only_quarantine, permanent=False, confirmed_by_user=False):
    if permanent and only_quarantine:
        print('--permanent 와 --quarantine 은 함께 사용할 수 없습니다.')
        return 2
    if permanent and yes and not confirmed_by_user:
        print('영구 삭제 실행에는 정확한 대상에 대한 현재 사용자 승인을 확인한 뒤 --confirmed-by-user 를 함께 사용하세요.')
        return 2
    targets = []
    for raw in paths:
        p = Path(raw).expanduser()
        p = Path(os.path.abspath(p))
        if not p.exists() and not p.is_symlink():
            print(f'  없음(건너뜀): {p}')
            continue
        if permanent and _protected_permanent_root(p, project_root(p.parent)):
            print(f'광범위 루트는 영구 삭제할 수 없습니다: {p}')
            return 2
        size, count = tree_size(p)
        targets.append((p, size, count))
    if not targets:
        print('옮길 대상이 없습니다.')
        return 1
    root = project_root(targets[0][0].parent)
    total = sum(s for _, s, _ in targets)
    print(f'대상 {len(targets)}개 · 파일 {sum(c for *_, c in targets)}개 · {total / 1e6:.1f}MB')
    for p, s, c in targets:
        how = ('영구 삭제' if permanent else
               ('휴지통' if (not only_quarantine and fixed_drive(p) and s <= RECYCLE_MAX_BYTES) else '격리 폴더'))
        print(f'  [{how}] {p}  ({c}파일 · {s / 1e6:.1f}MB)')
    if not yes:
        if permanent:
            print('\n영구 삭제 미리보기만 했습니다. 사용자가 위 정확한 대상을 승인한 경우에만 '
                  '--permanent --confirmed-by-user --yes 로 실행하세요.')
        else:
            print('\n미리보기만 했습니다. 목록을 다시 읽고 의도한 것만 있으면 같은 명령에 --yes 를 붙여 실행하세요.')
        return 0
    session = time.strftime('%Y%m%d_%H%M%S')
    recycled = 0
    session_dirs = set()
    for p, s, _ in targets:
        if permanent:
            if p.is_file() or p.is_symlink():
                p.unlink()
            else:
                shutil.rmtree(p)
            print(f'  사용자 승인 영구 삭제: {p}')
            continue
        if not only_quarantine and fixed_drive(p) and s <= RECYCLE_MAX_BYTES and to_recycle_bin(p):
            print(f'  휴지통으로 이동: {p}')
            recycled += 1
            continue
        dest = to_quarantine(p, root, session)
        session_dirs.add(quarantine_base(p, root)[0] / session)
        print(f'  격리 폴더로 이동: {p} → {dest}')
    if permanent:
        print(f'완료 · 사용자 승인 영구 삭제 {len(targets)}개.')
        return 0
    print(f'완료 · 휴지통 {recycled}개 · 격리 {len(targets) - recycled}개.')
    for sd in sorted(session_dirs):
        arg = session if sd.parent.name == QDIR else str(sd)
        print(f'  격리분 복원 = --restore "{arg}" --yes · 목록 = {sd / "manifest.tsv"}')
    if recycled:
        print('  휴지통분 복원 = Windows 휴지통에서 [복원]')
    return 0


def sessions(root):
    base = (root or Path.cwd()) / QDIR
    return sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []


def restore(root, session, yes):
    """세션 이름 또는 격리 세션 폴더 절대경로(드라이브 격리 _psp_quarantine 포함)를 받아 원위치로 되돌린다."""
    base = Path(session) if Path(session).is_absolute() else (root or Path.cwd()) / QDIR / session
    man = base / 'manifest.tsv'
    if not man.is_file():
        print(f'격리 세션 없음: {base}')
        return 1
    origin_file = base / 'origin_root.txt'
    origin = Path(origin_file.read_text(encoding='utf-8').strip()) if origin_file.is_file() else (root or Path.cwd())
    tops = [d for d in base.iterdir() if d.name not in ('manifest.tsv', 'origin_root.txt')]
    moves = []
    for top in tops:
        for dp, dn, fn in os.walk(top):
            for f in fn:
                src = Path(dp) / f
                moves.append((src, origin / src.relative_to(base)))
    clash = [d for _, d in moves if d.exists()]
    print(f'복원 대상 {len(moves)}개 · 이미 있는 자리 {len(clash)}개(덮지 않음)')
    for d in clash[:20]:
        print(f'  이미 있음: {d}')
    if not yes:
        print('미리보기만 했습니다. --yes 로 실행합니다(이미 있는 자리는 건너뜀).')
        return 0
    for src, dst in moves:
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    print('복원 완료.')
    return 0


def purge(root, days, yes):
    if days < MIN_PURGE_DAYS:
        print(f'보존 기간은 최소 {MIN_PURGE_DAYS}일입니다.')
        return 1
    cutoff = time.time() - days * 86400
    old = [d for d in sessions(root) if d.stat().st_mtime < cutoff]
    for d in old:
        print(f'  비울 세션: {d} ({tree_size(d)[0] / 1e6:.1f}MB)')
    if not old:
        print('보존 기간이 지난 격리 세션이 없습니다.')
        return 0
    if not yes:
        print('미리보기만 했습니다. 사용자 확인 후 --yes 로 실행합니다.')
        return 0
    for d in old:
        shutil.rmtree(d)
    print(f'{len(old)}개 세션을 비웠습니다.')
    return 0


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description='되돌릴 수 있는 삭제(휴지통·격리 폴더)')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--yes', action='store_true', help='미리보기 후 실제 실행')
    ap.add_argument('--quarantine', action='store_true', help='휴지통 대신 격리 폴더로만')
    ap.add_argument('--permanent', action='store_true', help='정확한 대상을 영구 삭제(기본은 미리보기)')
    ap.add_argument('--confirmed-by-user', action='store_true', help='현재 사용자가 미리보기의 정확한 대상을 영구 삭제하도록 승인했음')
    ap.add_argument('--root', type=Path, help='격리 폴더 기준 프로젝트 루트')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--restore')
    ap.add_argument('--purge-older-than', type=int)
    a = ap.parse_args()
    root = a.root.resolve() if a.root else project_root(Path.cwd())
    if a.list:
        for d in sessions(root):
            print(f'{d.name}  {tree_size(d)[0] / 1e6:.1f}MB  {d}')
        return 0
    if a.restore:
        return restore(root, a.restore, a.yes)
    if a.purge_older_than is not None:
        return purge(root, a.purge_older_than, a.yes)
    if not a.paths:
        ap.error('경로를 주세요.')
    if a.confirmed_by_user and not a.permanent:
        ap.error('--confirmed-by-user 는 --permanent 와 함께 사용합니다.')
    return remove(a.paths, a.yes, a.quarantine, a.permanent, a.confirmed_by_user)


if __name__ == '__main__':
    sys.exit(main())
