"""Shared Claude/Codex hooks. No shell-specific environment expansion."""
import fnmatch
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path

KOREAN = '응답·질문·선택지·진행 설명·직접 작성하는 승인 사유는 항상 한국어 존댓말로 작성합니다.'


def load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else (default or {})


def config(root):
    for rel in ('.claude/psp.config.json', '.codex/psp.config.json'):
        if (root / rel).is_file():
            return load(root / rel)
    return {}


def matches(path, pattern):
    path, pattern = path.replace('\\', '/'), pattern.replace('\\', '/')
    if os.name == 'nt':
        path, pattern = path.casefold(), pattern.casefold()
    parts = path.split('/')
    return any(fnmatch.fnmatchcase('/'.join(parts[i:]), pattern) for i in range(len(parts)))


def guard(data, root):
    inp = data.get('tool_input') or {}
    if not isinstance(inp, dict):
        raise ValueError('편집 입력을 해석할 수 없습니다.')
    paths = [inp['file_path']] if inp.get('file_path') else []
    command = inp.get('command', inp.get('patch', ''))
    if command:
        paths.extend(re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\r?$', command, re.M))
    if not paths:
        raise ValueError('편집 대상 경로를 찾을 수 없어 보호 검사를 중단했습니다.')
    cfg = config(root).get('guard', {})
    protected = ['.env*', '*.dev.vars', '.dev.vars', 'migrations/*', '*_KEEP/*', '*_backup_*/*',
                 '_quarantine/*', '_psp_quarantine/*'] + cfg.get('protect', [])
    for raw in paths:
        p = Path(raw.strip())
        lexical = Path(os.path.abspath(p if p.is_absolute() else root / p))
        for candidate in {lexical, lexical.resolve()}:
            if any(matches(str(candidate), pat) for pat in cfg.get('allow', [])):
                continue
            if any(matches(str(candidate), pat) for pat in protected):
                print(f'[가드] 보호 파일 직접 편집 차단: {candidate}\n프로젝트 보호 규칙에 해당합니다.', file=sys.stderr)
                return 2
    return 0


DELETE_RULE = ('[psp 삭제·덮어쓰기 규칙 — 실수 방지] 기본은 ①대상 미리보기 ②목록 재검토 ③휴지통·격리 이동이다. '
               '사용자가 정확한 대상을 영구 삭제하도록 명시 승인하면 safe_delete.py --permanent --confirmed-by-user --yes 로 실행할 수 있다. '
               '드라이브 루트·사용자 홈·프로젝트 루트 같은 광범위 대상과 승인 범위 밖 경로는 허용하지 않는다. '
               'git 작업 트리 정리는 백업 또는 임시 클론에서 한다.')

# 완전 삭제·되돌릴 수 없는 덮어쓰기 명령(셸 문장 첫 단어 기준). PowerShell 별칭 rm/del/rd/ri/erase 포함.
_DELETE_VERBS = {'rm', 'rmdir', 'rd', 'del', 'erase', 'ri', 'unlink', 'shred', 'remove-item', 'clear-content'}
_DELETE_CALLS = re.compile(r'shutil\.rmtree|os\.(?:remove|unlink|rmdir|removedirs)\s*\(|\.unlink\s*\(|\.rmdir\s*\(|'
                           r'Remove-Item|\[System\.IO\.(?:File|Directory)\]::Delete|DeleteFile|rimraf|fs\.(?:rm|unlink)Sync?\s*\(',
                           re.I)
_INTERPRETERS = {'python', 'python3', 'py', 'node', 'powershell', 'pwsh', 'cmd', 'bash', 'sh'}
_TEMP_MARK = re.compile(r'(?i)(?:[\\/]|^|[\s"\'])(?:tmp|temp)[\\/]|appdata[\\/]local[\\/]temp|scratchpad|\$env:temp|%temp%|\$tmpdir|\$\{?tmp')
_REDIRECT = re.compile(r'^\d*(?:>>?|<<?|<>|>&|<&)')


def _statements(command):
    """셸 문장 단위로 자른다(;, &&, ||, |, 줄바꿈 — 따옴표 밖에서만). heredoc 본문까지 정밀 파싱은 하지 않는다."""
    out, cur, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in '"\'':
            quote = ch
            cur.append(ch)
        elif ch in ';|\n' or command.startswith('&&', i):
            out.append(''.join(cur))
            cur = []
            i += 2 if command.startswith(('&&', '||'), i) else 1
            continue
        else:
            cur.append(ch)
        i += 1
    out.append(''.join(cur))
    return [s.strip() for s in out if s.strip()]


def _quoted(stmt):
    return [m.group(2) for m in re.finditer(r'(["\'])(.*?)\1', stmt, re.S)]


def _verb_and_args(stmt):
    try:
        lex = shlex.shlex(stmt.replace('(', ' '), posix=False)
        lex.whitespace_split = True
        lex.commenters = ''
        tokens = [token.strip('"\'') for token in lex]
    except ValueError:
        tokens = stmt.replace('(', ' ').split()
    while tokens and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[0]) or tokens[0] in ('sudo', 'command', 'exec', 'time', '&', '.')):
        tokens = tokens[1:]
    if not tokens:
        return '', []
    verb = tokens[0].strip('"\'').replace('\\', '/').rsplit('/', 1)[-1].lower()
    verb = verb[:-4] if verb.endswith('.exe') else verb
    return verb, tokens[1:]


def _without_redirections(args):
    out, skip = [], False
    for token in args:
        if skip:
            skip = False
            continue
        if _REDIRECT.match(token):
            skip = bool(re.fullmatch(r'\d*(?:>>?|<<?|<>|>&|<&)', token))
            continue
        out.append(token)
    return out


def _known_temp_expansion(value):
    temp = tempfile.gettempdir()
    value = re.sub(r'(?i)%temp%|\$env:temp|\$\{?tmpdir\}?|\$\{?tmp\}?',
                   lambda _: temp, value.strip('"\''))
    if os.name == 'nt':
        match = re.match(r'^/(?:tmp|temp)(?:/(.*))?$', value, re.I)
        if match:
            return str(Path(temp) / (match.group(1) or ''))
        match = re.match(r'^/([A-Za-z])/(.*)$', value)
        if match:
            return f'{match.group(1).upper()}:/{match.group(2)}'
    return value


def _resolved_path(value, cwd):
    value = _known_temp_expansion(value)
    if '$' in value or '%' in value:
        return None
    path = Path(value)
    try:
        return (path if path.is_absolute() else Path(cwd) / path).resolve()
    except OSError:
        return None


def _is_temp_path(path):
    if not path:
        return False
    try:
        if path.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            return True
    except (OSError, ValueError):
        pass
    return any(part.casefold() == 'scratchpad' for part in path.parts)


def _only_temp(args, cwd):
    """리다이렉션·옵션을 뺀 모든 실제 대상이 검증된 임시 경로 아래일 때만 허용한다."""
    args = _without_redirections(args)
    paths = [a for a in args if not re.match(r'^-{1,2}[A-Za-z]', a) and not re.match(r'^/[A-Za-z]$', a)]
    resolved = [_resolved_path(path, cwd) for path in paths]
    return bool(resolved) and all(_is_temp_path(path) for path in resolved)


def _git_parts(args, cwd):
    """git 전역 옵션을 걷어 하위 명령·인자·-C가 반영된 작업 경로를 반환한다."""
    args, effective, index, extra_roots = _without_redirections(args), Path(cwd), 0, []
    takes_value = {'-c', '--namespace', '--exec-path'}
    while index < len(args):
        token = args[index]
        if token == '-C' and index + 1 < len(args):
            effective = _resolved_path(args[index + 1], effective) or effective
            index += 2
        elif token in ('--git-dir', '--work-tree') and index + 1 < len(args):
            extra_roots.append(_resolved_path(args[index + 1], effective))
            index += 2
        elif token in takes_value and index + 1 < len(args):
            index += 2
        elif token.startswith(('--git-dir=', '--work-tree=')):
            extra_roots.append(_resolved_path(token.split('=', 1)[1], effective))
            index += 1
        elif token.startswith(('--namespace=', '--exec-path=')):
            index += 1
        elif token.startswith('-'):
            index += 1
        else:
            return token.lower(), args[index + 1:], [effective] + extra_roots
    return '', [], [effective] + extra_roots


def _cd_target(args, cwd):
    values = [a for a in _without_redirections(args)
              if a.lower() not in ('/d', '-literalpath', '-path')]
    return _resolved_path(values[0], cwd) if values else Path(cwd)


def _scan(command, reasons, depth=0, cwd=None):
    cwd = Path(cwd or os.getcwd()).resolve()
    for stmt in _statements(command):
        verb, args = _verb_and_args(stmt)
        if verb in ('cd', 'chdir', 'set-location', 'pushd'):
            cwd = _cd_target(args, cwd)
            continue
        if verb in _INTERPRETERS and depth < 3:
            # cmd /c "…", powershell -Command "…", bash -c "…" — 따옴표 안 명령도 같은 기준으로 검사
            for inner in _quoted(stmt):
                _scan(inner, reasons, depth + 1, cwd)
            switches = {'cmd': ('/c', '/k', '//c', '//k'),
                        'powershell': ('-command', '-c'), 'pwsh': ('-command', '-c'),
                        'bash': ('-c',), 'sh': ('-c',),
                        'python': ('-c',), 'python3': ('-c',), 'py': ('-c',), 'node': ('-e',)}
            lowered = [arg.lower() for arg in args]
            for switch in switches.get(verb, ()):
                if switch in lowered:
                    index = lowered.index(switch)
                    inner = ' '.join(args[index + 1:]).strip().strip('"\'')
                    if inner:
                        _scan(inner, reasons, depth + 1, cwd)
                    break
        low = ' '.join(args).lower()
        if verb == 'git':
            sub, git_args, git_roots = _git_parts(args, cwd)
            low = ' '.join(git_args).lower()
            temp_repo = bool(git_roots) and all(_is_temp_path(path) for path in git_roots)
            checkout_values = [arg for arg in git_args if not arg.startswith('-')]
            checkout_path = (sub == 'checkout' and
                             (len(checkout_values) >= 2 or any(value in ('.', ':/') or '/' in value or '\\' in value
                                                               or Path(value).suffix for value in checkout_values)))
            if sub == 'clean' and not re.search(r'(^|\s)(-n|--dry-run|-[a-z]*n[a-z]*)(\s|$)', ' ' + low):
                if not temp_repo:
                    reasons.append(f'git clean(작업 트리의 추적 밖 파일 영구 삭제{" + 깃 제외 파일까지" if re.search(r"-[a-z]*x", low) else ""}): {stmt[:120]}')
            elif sub == 'reset' and '--hard' in low:
                if not temp_repo:
                    reasons.append(f'git reset --hard(커밋 안 된 변경 영구 소실): {stmt[:120]}')
            elif sub in ('checkout', 'restore') and (re.search(r'(^|\s)--\s', ' ' + low + ' ') or re.search(r'(^|\s)(-f|--force)(\s|$)', low)
                                                    or checkout_path
                                                    or sub == 'restore' and ('--staged' not in low or re.search(r'(^|\s)(--worktree|-w)(\s|$)', low))):
                if not temp_repo:
                    reasons.append(f'git {sub}(작업 중 변경 덮어쓰기): {stmt[:120]}')
            elif sub in ('checkout', 'switch') and '--orphan' in low:
                if not temp_repo:
                    reasons.append(f'git {sub} --orphan(작업 트리 이력 전환): {stmt[:120]}')
            elif sub == 'push' and re.search(r'(^|\s)(-f|--force)(?:=\S+)?(\s|$)', low):
                reasons.append(f'git push --force(원격 이력 덮어쓰기): {stmt[:120]}')
            elif (sub == 'push' and '--force-with-lease' not in low
                  and any(len(arg) > 1 and arg.startswith('+') for arg in _without_redirections(git_args))):
                # A positional +refspec has the same force-push effect. Keep the existing lease exception.
                reasons.append(f'git push +refspec(원격 이력 덮어쓰기): {stmt[:120]}')
            elif sub == 'branch' and re.search(r'(^|\s)-D(\s|$)', ' '.join(git_args)):
                if not temp_repo:
                    reasons.append(f'git branch -D(병합 안 된 브랜치 강제 삭제): {stmt[:120]}')
            elif sub == 'stash' and git_args and git_args[0].lower() in ('drop', 'clear'):
                if not temp_repo:
                    reasons.append(f'git stash {git_args[0]}(보관 변경 영구 삭제): {stmt[:120]}')
        elif verb == 'find' and ('-delete' in [a.lower() for a in args] or re.search(
                r'(^|\s)-(exec|execdir|ok|okdir)\s+(\S*[\\/])?(rm|rmdir|del|unlink|shred)(\.exe)?(\s|$)', ' ' + low)):
            # find -delete / find -exec rm — 시작 경로(첫 옵션 앞 인자, 없으면 현재 폴더)가 모두 임시면 허용
            starts = []
            for arg in _without_redirections(args):
                if arg.startswith(('-', '(', '!')):
                    break
                starts.append(arg)
            if not _only_temp(starts or ['.'], cwd):
                reasons.append(f'find 삭제(-delete/-exec rm, 영구 삭제): {stmt[:120]}')
        elif verb == 'rsync' and re.search(
                r'(^|\s)--(?:del|delete(?:-(?:before|during|delay|after|excluded|missing-args))?|remove-source-files)(?:=\S+)?(\s|$)', low):
            # rsync --delete: 대상(마지막 경로)에서 원본에 없는 파일을 지움 / --remove-source-files: 원본 삭제
            values = [arg for arg in _without_redirections(args) if not arg.startswith('-')]
            if not values or not _only_temp(values[-1:] if '--remove-source-files' not in low else values, cwd):
                reasons.append(f'rsync --delete(대상 파일 영구 삭제): {stmt[:120]}')
        elif verb == 'truncate':
            values = [arg for arg in _without_redirections(args) if not arg.startswith('-') and not re.fullmatch(r'[+<>/%-]?\d+[KMGTP]?i?B?', arg, re.I)]
            if not values or not _only_temp(values, cwd):
                reasons.append(f'truncate(파일 내용 소실): {stmt[:120]}')
        elif verb in _DELETE_VERBS:
            if '-whatif' in low or _only_temp(args, cwd):
                continue
            reasons.append(f'{verb}(영구 삭제): {stmt[:120]}')
        elif verb in _INTERPRETERS and _DELETE_CALLS.search(stmt) and '-whatif' not in low and not _TEMP_MARK.search(stmt):
            # 인터프리터 한 줄 실행(python -c, node -e, powershell -Command) 안의 삭제 호출 — 대상이 임시 폴더가 아니면 차단
            reasons.append(f'스크립트 안 삭제 호출(rmtree·remove·unlink·Remove-Item 등): {stmt[:120]}')


def deleteguard(data, root):
    """PreToolUse(셸): 완전 삭제·되돌릴 수 없는 덮어쓰기 명령을 차단하고 되돌릴 수 있는 절차로 돌려보낸다.
    허용 = 미리보기(git clean -n, -WhatIf), 임시 폴더(Temp·scratchpad) 대상, psp safe_delete.py."""
    inp = data.get('tool_input') or {}
    command = inp.get('command', '') if isinstance(inp, dict) else ''
    if isinstance(command, list):
        command = ' '.join(map(str, command))
    if not command:
        return 0
    reasons = []
    _scan(command, reasons, cwd=root)
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        return 0
    tool = Path(__file__).resolve().parents[1] / 'tools' / 'safe_delete.py'
    print('[삭제 가드] 되돌릴 수 없는 삭제·덮어쓰기 명령을 막았습니다.\n- ' + '\n- '.join(reasons) +
          f'\n\n절차(psp 공통 규칙 7): ①대상 목록 미리보기 → ②재검토 → ③되돌릴 수 있는 방식으로 실행.\n'
          f'  미리보기: python "{tool}" <경로...>\n'
           f'  기본 실행: python "{tool}" <경로...> --yes   (휴지통, 안 되면 _quarantine/날짜/ 격리 + 목록)\n'
           f'  승인 영구삭제: python "{tool}" <경로...> --permanent --confirmed-by-user --yes\n'
          f'  git 정리·고아 브랜치 = 임시 클론(git clone / git worktree add)에서. 미리보기는 git clean -n.\n'
           f'  영구 삭제는 사용자가 미리보기의 정확한 대상을 명시 승인한 경우에만 실행한다.', file=sys.stderr)
    return 2


HANDOFF_MAX_BYTES = 12000
MEMORY_INDEX_MAX_BYTES = 4200
SESSION_MAX_BYTES = 18000


def _utf8_prefix(text, limit):
    data = text.encode('utf-8')[:max(0, limit)]
    while data:
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError as error:
            data = data[:error.start]
    return ''


def _bounded_handoff(text, limit=HANDOFF_MAX_BYTES):
    """현재·다음·재개 근거를 우선하면서 최종 UTF-8 바이트 상한을 지킨다."""
    if len(text.encode('utf-8')) <= limit:
        return text
    lines = text.splitlines()
    important = [line for line in lines if re.search(r'(?i)현재|다음|재개|미완료|next|resume|blocked', line)]
    links = [m.group(0) for m in re.finditer(r'^\s*-\s+\[[^\n]+?\]\([^\n]+?\)', text, re.M)]
    candidates = important + lines[:40] + links
    note = '\n인계 원본이 길어 현재·다음 항목, 상단, 연결 문서 일부만 바이트 상한 안에서 주입했습니다. 필요한 본문만 여세요.'
    budget = limit - len(note.encode('utf-8'))
    out, seen, used = [], set(), 0
    for line in candidates:
        if line in seen:
            continue
        seen.add(line)
        clipped = _utf8_prefix(line, 1600)
        if clipped != line:
            clipped = _utf8_prefix(clipped, 1596) + ' …'
        addition = clipped if not out else '\n' + clipped
        size = len(addition.encode('utf-8'))
        if used + size > budget:
            continue
        out.append(clipped)
        used += size
    return _utf8_prefix('\n'.join(out) + note, limit)


def _memory_index_summary(indexes, limit=MEMORY_INDEX_MAX_BYTES):
    """Inject index pointers and topic links, not whole long-term-memory bodies."""
    headers, reviews, overviews, topics, seen = [], [], [], [], set()
    for path in indexes:
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        headers.append(f'[메모리 인덱스: {path}]')
        text = path.read_text(encoding='utf-8-sig')
        reviews.extend(line for line in text.splitlines()
                       if re.search(r'마지막\s*검토|last\s+review', line, re.I))
        # 한 줄에 링크가 여럿이어도 전부 남긴다(첫 링크만 잡으면 2026-10-11 실측 71개 중 27개 누락).
        # 예산 안에 다 들어가게 링크 경로만 쓴다(인덱스 폴더 기준 상대 경로 그대로). 제목·회수 트리거는 인덱스 원본에서 연다.
        found = []
        for line in text.splitlines():
            if re.match(r'^\s*[-*]\s+', line):
                names = [m.group(1) for m in re.finditer(r'\[[^\]\n]+\]\(([^)\s]+?\.md)(?:#[^)]*)?\)', line)]
                if names:
                    found.append('- ' + ' · '.join(dict.fromkeys(names)))
        if found:
            topics.extend(found)
        else:
            overviews.append(_utf8_prefix(text, 1200))
    if not headers:
        return ''
    note = ('\n메모리 본문은 자동 주입하지 않습니다. 위 목록은 인덱스가 가리키는 메모리 파일 경로이며 제목·회수 트리거는 인덱스 원본에 있습니다. '
            '현재 작업에 필요한 인덱스와 본문만 여세요.')
    budget = limit - len(note.encode('utf-8')) - 120   # 120 = 생략 안내 한 줄 자리
    out, used, line_seen, omitted = [], 0, set(), 0
    for line in headers + reviews + overviews + topics:
        if line in line_seen:
            continue
        line_seen.add(line)
        clipped = _utf8_prefix(line, 1000)
        addition = clipped if not out else '\n' + clipped
        size = len(addition.encode('utf-8'))
        if used + size > budget:
            omitted += line.count(' · ') + 1   # 조용히 버리지 않고 생략 수를 알린다
            continue
        out.append(clipped)
        used += size
    if omitted:
        note = f'\n[메모리 요약 상한으로 {omitted}개 항목 생략 — 인덱스 원본을 여세요]' + note
    return _utf8_prefix('\n'.join(out) + note, limit)


def _bounded_session_context(text, limit=SESSION_MAX_BYTES):
    """Final fail-safe so one unusually long project cannot flood SessionStart."""
    if len(text.encode('utf-8')) <= limit:
        return text
    note = '\n세션 시작 문맥이 전체 상한을 넘어 잘랐습니다. 연결된 원본에서 현재 작업에 필요한 부분만 여세요.'
    return _utf8_prefix(text, limit - len(note.encode('utf-8'))) + note


def _roadmap_state(root):
    roadmap = root / config(root).get('roadmap', 'todo/roadmap.md')
    if not roadmap.is_file():
        return roadmap, '', None
    current = next((line for line in roadmap.read_text(encoding='utf-8-sig').splitlines()
                    if line.strip().startswith('현재')), '')
    match = re.search(r'현재\s*=\s*([A-Za-z0-9_-]+)', current)
    candidates = sorted((root / 'todo').glob(f'{match.group(1)}*/index.md')) if match else []
    return roadmap, current, candidates[0].resolve() if candidates else None


def session(data, root):
    print('[psp 상시 소통 규칙] ' + KOREAN)
    print(DELETE_RULE)
    try:
        tools = Path(__file__).resolve().parents[1] / 'tools'
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from update_notice import notice
        print(notice(root))
    except Exception:
        print('[Philip Relay 버전] 설치 버전 확인 실패 · 작업은 계속하되 philip:updatecheck에서 재확인하세요.')
    rule = next((p for p in (root / 'AGENTS.md', root / 'CLAUDE.md') if p.is_file()), None)
    if not rule:
        return
    synced = rulesync(root)
    if synced:
        print(synced)
    print(f'프로젝트 규칙: {rule} 및 연결된 원본을 읽으세요.')
    runtime = load(root / '.psp/runtime.json')
    roadmap, current, current_handoff = _roadmap_state(root)
    handoff = runtime.get('handoff_index')
    target = current_handoff or ((root / handoff).resolve() if handoff else None)
    if target:
        if target.is_relative_to(root.resolve()) and target.is_file():
            handoff_text = target.read_text(encoding='utf-8-sig')
            handoff_text = _bounded_handoff(handoff_text)
            print(f'[작업 인계 원본: {target}]\n' + handoff_text)
            print('위 인계 기록의 시각과 실제 변경 파일을 대조하고 재개하세요. 과거 실행 상태를 현재 상태로 단정하지 마세요.')
        else:
            print('[작업 인계 확인 필요] 연결된 프로젝트 내부 파일을 찾을 수 없습니다.')
    dirs = runtime.get('memory_dirs', ['memory'])
    indexes = [root / 'MEMORY.md'] + [(Path(d) if Path(d).is_absolute() else root / d) / 'MEMORY.md' for d in dirs]
    memory_summary = _memory_index_summary(indexes)
    if memory_summary:
        print('\n' + memory_summary)
    print('인덱스 상대 링크는 해당 인덱스 폴더 기준입니다. 필요한 본문을 열고 판단하세요.')
    if not roadmap.is_file():
        return
    print(current)
    m = re.search(r'현재\s*=\s*([A-Za-z0-9_-]+)', current)
    candidates = sorted((root / 'todo').glob(f'{m.group(1)}*/index.md')) if m else []
    for p in candidates[:1] or [root / 'todo/index.md']:
        if p.is_file() and (not target or p.resolve() != target):
            print(f'[{p}]\n' + '\n'.join(p.read_text(encoding='utf-8-sig').splitlines()[:40]))


RULE_FILES = ('CLAUDE.md', 'AGENTS.md')
RULE_AGENT = {'CLAUDE.md': 'Claude', 'AGENTS.md': 'Codex'}


def _rule_canon(text, name):
    """파일 고유 표기(자기 이름·에이전트 이름)를 자리표로 바꿔 두 규칙 파일을 같은 형태로 비교한다."""
    return text.replace(name, '{RULE}').replace(RULE_AGENT[name] + '/Co-Authored', '{AGENT}/Co-Authored')


def rulesync(root, source=None):
    """두 규칙 파일의 독립 변경을 보존한다.

    SessionStart(source 없음)는 차이만 알리고 쓰지 않는다. 편집 훅처럼 source가 명확할 때만
    반대편의 기존 내용을 로컬 백업한 뒤 동기화한다.
    """
    paths = {n: root / n for n in RULE_FILES}
    if not all(p.is_file() for p in paths.values()):
        return ''
    texts = {n: p.read_text(encoding='utf-8-sig') for n, p in paths.items()}
    if texts['CLAUDE.md'] == texts['AGENTS.md']:
        return ''
    if _rule_canon(texts['CLAUDE.md'], 'CLAUDE.md') == _rule_canon(texts['AGENTS.md'], 'AGENTS.md'):
        return ''
    if source not in RULE_FILES:
        return '[규칙 충돌] CLAUDE.md와 AGENTS.md가 다릅니다. 어느 쪽도 자동 덮어쓰지 않았습니다. 두 변경을 검토해 병합하세요.'
    target = 'AGENTS.md' if source == 'CLAUDE.md' else 'CLAUDE.md'
    local = Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())
    project_key = hashlib.sha256(str(root.resolve()).encode('utf-8')).hexdigest()[:16]
    backup_dir = local / 'philip-relay' / 'rulesync-backups' / project_key
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'{time.time_ns()}-{target}'
    backup.write_text(texts[target], encoding='utf-8')
    new = (_rule_canon(texts[source], source).replace('{RULE}', target)
           .replace('{AGENT}/Co-Authored', RULE_AGENT[target] + '/Co-Authored'))
    paths[target].write_text(new, encoding='utf-8')
    return f'[규칙 동기] {source} → {target} 동기화. 기존 {target}은 로컬 Philip Relay 백업에 보존했습니다.'


def rulesync_hook(data, root):
    inp = data.get('tool_input') or {}
    raw = inp.get('file_path') if isinstance(inp, dict) else None
    source = Path(raw).name if raw else None
    if source not in RULE_FILES:
        return
    msg = rulesync(root, source)
    if msg:
        print(msg)


def reminder(data, root):
    # 시간 간격이 아니라 실제 사건(규칙 변경·작업 전환)에 맞춰 필요한 포인터만 주입한다.
    print(KOREAN)
    rules = [root / x for x in ('AGENTS.md', 'CLAUDE.md') if (root / x).is_file()]
    if not rules:
        return
    digest = hashlib.sha256(b'\0'.join(p.read_bytes() for p in rules)).hexdigest()
    state_path = root / '.psp/.behavior_state.json'
    try:
        state = load(state_path)
    except (OSError, ValueError):
        state = {}
    messages = []
    changed = state.get('rules_hash') != digest
    if changed:
        messages.append('[행동매뉴얼 변경 감지] 프로젝트 규칙과 연결된 원본 중 이번 작업에 관련된 부분을 다시 읽으세요.')
    prompt = str(data.get('prompt') or (data.get('tool_input') or {}).get('prompt') or '')
    if re.search(r'검토|리뷰|감사|review|audit', prompt, re.I):
        messages.append('[검토 권한] 발견·보고 요청인지 수정까지 승인된 요청인지 구분하세요.')
    if re.search(r'고쳐|수정|구현|진행|반영|업데이트|update|implement|fix', prompt, re.I):
        messages.append('[변경 시작] 대상 실물·기존 분석·프로젝트 규칙·영향 범위·현재 승인을 확인하세요.')
    if re.search(r'완료|끝났|배포|출시|done|complete|deploy', prompt, re.I):
        messages.append('[완료 주장] 실행·실측·전파 근거와 미검증 범위를 분리하세요.')
    if changed:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({'rules_hash': digest, 'updated_at': time.time()}), encoding='utf-8')
        except OSError:
            pass
    if messages:
        print('\n'.join(dict.fromkeys(messages)))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    event = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        data = json.loads(sys.stdin.buffer.read().decode('utf-8-sig').strip() or '{}')
        if not isinstance(data, dict):
            raise ValueError('훅 입력은 JSON 객체여야 합니다.')
        root = Path(data.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()).resolve()
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            if event == 'guard':
                try:
                    denied = guard(data, root) == 2
                except (ValueError, OSError, TypeError) as exc:
                    denied = True
                    errors.write(f'보호 검사 실패: {exc}')
            elif event == 'deleteguard':
                denied = deleteguard(data, root) == 2
            elif event == 'session':
                session(data, root)
            elif event == 'reminder':
                reminder(data, root)
            elif event == 'rulesync':
                rulesync_hook(data, root)
            else:
                raise ValueError('지원하지 않는 훅입니다.')
        if event in ('guard', 'deleteguard'):
            if denied:
                print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                      'permissionDecision': 'deny', 'permissionDecisionReason': errors.getvalue()}}))
        else:
            name = {'session': 'SessionStart', 'rulesync': 'PostToolUse'}.get(event, 'UserPromptSubmit')
            context = output.getvalue()
            if event == 'session':
                context = _bounded_session_context(context)
            print(json.dumps({'hookSpecificOutput': {'hookEventName': name, 'additionalContext': context}}))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        if event == 'guard':
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                  'permissionDecision': 'deny', 'permissionDecisionReason': f'보호 검사 실패: {exc}'}}))
            return 0
        print(f'[psp] 훅 처리 실패: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
