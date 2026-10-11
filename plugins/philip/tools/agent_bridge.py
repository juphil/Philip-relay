"""Plan/apply additive agent integration. Backups precede every changed file."""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LANGUAGE = '응답·질문·선택지·진행 설명·직접 작성하는 승인 사유는 항상 한국어 존댓말로 작성한다.'
START, END = '<!-- philip:agent-bridge -->', '<!-- /philip:agent-bridge -->'


def read_json(p):
    data = json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
    if not isinstance(data, dict):
        raise ValueError(f'설정은 JSON 객체여야 합니다: {p}')
    return data


def encoded_project(root):
    return re.sub(r'[^a-zA-Z0-9]', '-', str(root))


def block(text, body):
    section = START + '\n' + body.rstrip() + '\n' + END
    if START in text or END in text:
        if text.count(END) != 1 or text.count(START) != 1 or text.index(END) < text.index(START):
            raise ValueError('기존 연결 블록이 손상됐습니다. 원본을 확인하세요.')
        return re.sub(re.escape(START) + r'.*?' + re.escape(END), lambda _: section, text, flags=re.S)
    return text.rstrip() + '\n\n' + section + '\n'


def clean_codex_hooks(data):
    result = copy.deepcopy(data)
    removed = []
    if not isinstance(result.get('hooks', {}), dict):
        raise ValueError('hooks 설정은 이벤트별 JSON 객체여야 합니다.')
    for event, groups in list(result.get('hooks', {}).items()):
        if not isinstance(groups, list):
            raise ValueError(f'훅 그룹은 배열이어야 합니다: {event}')
        keep_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks', []), list):
                raise ValueError(f'훅 그룹 형식이 잘못됐습니다: {event}')
            keep = []
            for hook in group.get('hooks', []):
                if not isinstance(hook, dict) or not isinstance(hook.get('command', ''), str):
                    raise ValueError(f'훅 명령 형식이 잘못됐습니다: {event}')
                cmd = hook.get('command', '').replace('\\', '/').lower()
                reason = None
                if '/.orca/agent-hooks/claude-hook.cmd' in cmd:
                    reason = '클로드 전용 Orca 훅'
                elif '/clawd-on-desk/hooks/clawd-hook.js' in cmd or '/clawd-on-desk/hooks/auto-start.js' in cmd:
                    reason = '클로드 전용 Clawd 훅'
                elif cmd.strip() == 'any-buddy apply --silent' and not shutil.which('any-buddy'):
                    reason = '실행 파일이 없는 any-buddy 훅'
                if reason:
                    removed.append({'event': event, 'reason': reason})
                else:
                    keep.append(hook)
            if keep:
                g = dict(group)
                g['hooks'] = keep
                keep_groups.append(g)
        if keep_groups:
            result['hooks'][event] = keep_groups
        else:
            del result['hooks'][event]
    return result, removed


class Plan:
    def __init__(self, root):
        self.root = root
        self.changes = {}
        self.originals = {}
        self.memory_snapshot = {}
        self.memory_roots = {}
        self.notes = []

    def write(self, p, text):
        p = Path(p).resolve()
        content = text.encode('utf-8')
        if p.exists() and p.read_bytes() == content:
            return
        self.changes[p] = content
        self.originals[p] = p.read_bytes() if p.exists() else None

    def json(self, p, data):
        self.write(p, json.dumps(data, ensure_ascii=False, indent=2) + '\n')

    def apply(self):
        for directory, files in self.memory_roots.items():
            if set(directory.rglob('*.md')) != files:
                raise ValueError(f'계획 이후 메모리 파일 목록이 변경됐습니다. 다시 계획하세요: {directory}')
        if not self.changes:
            return None
        for p, original in self.originals.items():
            if (p.read_bytes() if p.exists() else None) != original:
                raise ValueError(f'계획 이후 파일이 변경됐습니다. 다시 계획하세요: {p}')
        for p, digest in self.memory_snapshot.items():
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                raise ValueError(f'계획 이후 메모리가 변경됐습니다. 다시 계획하세요: {p}')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = self.root / 'workbench_records_KEEP' / ('agent_bridge_' + stamp)
        backup.mkdir(parents=True)
        manifest = []
        for i, (p, content) in enumerate(self.changes.items()):
            saved = f'{i:03d}_{p.name}' if p.exists() else None
            old = p.read_bytes() if p.exists() else None
            if saved:
                (backup / saved).write_bytes(old)
            manifest.append({'path': str(p), 'backup': saved,
                             'before_sha256': hashlib.sha256(old).hexdigest() if old is not None else None,
                             'after_sha256': hashlib.sha256(content).hexdigest()})
        (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        # All backups exist before the first mutation. No delete/move operations.
        for p, content in self.changes.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        for p, digest in self.memory_snapshot.items():
            if p not in self.changes and (not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest):
                raise ValueError(f'적용 후 메모리 보존 확인에 실패했습니다: {p}')
        return backup


def make_plan(target, root, claude_home, codex_homes, explicit_memories=()):
    plan = Plan(root)
    mapping_path = root / '.psp/runtime.json'
    mapping = read_json(mapping_path)
    if not isinstance(mapping.get('memory_dirs', []), list) or any(not isinstance(p, str) for p in mapping.get('memory_dirs', [])):
        raise ValueError('runtime.json의 memory_dirs는 경로 문자열 배열이어야 합니다.')
    dirs = []
    candidates = list(explicit_memories) + mapping.get('memory_dirs', [])
    candidates += [claude_home / 'projects' / encoded_project(root) / 'memory', root / 'memory', root / 'claude/memory']
    local_settings = read_json(root / '.claude/settings.local.json')
    if 'autoMemoryDirectory' in local_settings and not isinstance(local_settings['autoMemoryDirectory'], str):
        raise ValueError('autoMemoryDirectory는 경로 문자열이어야 합니다.')
    if local_settings.get('autoMemoryDirectory'):
        candidates.insert(0, Path(local_settings['autoMemoryDirectory']).expanduser())
    for d in candidates:
        p = Path(d).expanduser()
        p = (p if p.is_absolute() else root / p).resolve()
        if root == p or root.is_relative_to(p):
            raise ValueError(f'프로젝트 전체나 상위 폴더를 메모리 원본으로 지정할 수 없습니다: {p}')
        if not p.is_dir():
            if d in mapping.get('memory_dirs', []) or (local_settings.get('autoMemoryDirectory') and p == (root / Path(local_settings['autoMemoryDirectory']).expanduser()).resolve()):
                raise ValueError(f'기존 메모리 경로에 접근할 수 없습니다: {p}. 연결은 보존하며 적용을 중단합니다. 경로를 복구한 뒤 다시 실행하세요.')
            if d in explicit_memories:
                raise ValueError(f'지정한 메모리 폴더가 없습니다: {p}')
            continue
        if p not in dirs:
            dirs.append(p)
    if not dirs:
        dirs = [root / 'memory']
    mapping['memory_dirs'] = [str(p) for p in dirs]
    mapping['language'] = 'ko'
    plan.json(mapping_path, mapping)
    for name in ('AGENTS.md', 'CLAUDE.md'):
        p = root / name
        other = 'CLAUDE.md' if name == 'AGENTS.md' else 'AGENTS.md'
        if p.is_file():
            text = p.read_text(encoding='utf-8-sig')
        elif (root / other).is_file():
            text = '# 프로젝트 규칙\n\n@AGENTS.md\n' if name == 'CLAUDE.md' else f'# 프로젝트 규칙\n\n{other}를 전체 읽고 프로젝트 규칙으로 적용한다.\n'
        else:
            text = '# 프로젝트 규칙\n'
        plan.write(p, block(text, LANGUAGE + '\n새 세션은 MEMORY.md와 연결된 기존 메모리의 필요한 본문을 읽고 시작한다.'))
    index = root / 'MEMORY.md'
    text = index.read_text(encoding='utf-8-sig') if index.exists() else '# 프로젝트 메모리\n'
    links = ['공용 메모리 원본은 아래 경로를 사용한다. 중복 복사하지 않는다.']
    links.append('- [메모리 전체 파일 목록](.psp/memory_inventory.md) — 도구 전환·메모리 누락 확인 전에 회수. 기존 인덱스에 없는 파일도 포함한다.')
    for i, d in enumerate(dirs, 1):
        p = d / 'MEMORY.md'
        if p.is_file():
            links.append(f'- [기존 메모리 {i}](<{p.as_posix()}>) — 새 세션 시작·기존 맥락을 물을 때 회수.')
        elif d == root / 'memory':
            # Preserve loose memory files even when there is no index yet.
            topics = sorted(d.rglob('*.md')) if d.exists() else []
            body = '# 메모리 인덱스\n\n' + ''.join(f'- [{p.stem}](<{p.relative_to(d).as_posix()}>) — 관련 작업 전에 회수.\n' for p in topics)
            plan.write(p, body)
            links.append(f'- [기존 메모리 {i}](<{p.as_posix()}>) — 새 세션 시작·기존 맥락을 물을 때 회수.')
        else:
            # External notes may have no index. Link them without modifying them.
            links.append(f'- [기존 메모리 폴더 {i}](<{d.as_posix()}>) — 인덱스 없는 원본 폴더.')
            for topic in sorted(d.rglob('*.md')):
                links.append(f'  - [{topic.relative_to(d).as_posix()}](<{topic.as_posix()}>) — 관련 작업 전에 회수.')
    plan.write(index, block(text, '\n'.join(links)))
    inventory = ['# 공용 메모리 파일 목록', '', '본문은 아래 원본 파일에만 저장한다. SHA-256은 연결 시점의 내용 확인용이며 현재 작업 상태가 아니다.', '']
    for d in dirs:
        topics = set(d.rglob('*.md')) if d.exists() else set()
        plan.memory_roots[d] = set(topics)
        topics.update(p for p in plan.changes if p.is_relative_to(d) and p.suffix == '.md')
        inventory.append(f'## {d.as_posix()}')
        for topic in sorted(topics):
            if topic.is_file():
                plan.memory_snapshot[topic] = hashlib.sha256(topic.read_bytes()).hexdigest()
            content = plan.changes.get(topic)
            if content is None:
                content = topic.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            inventory.append(f'- [{topic.relative_to(d).as_posix()}](<{topic.as_posix()}>) — SHA-256 `{digest}`')
        if not topics:
            inventory.append('메모리 파일 없음. 경로가 맞는지 확인한다.')
        inventory.append('')
    plan.write(root / '.psp/memory_inventory.md', '\n'.join(inventory))
    plan.notes.append(f'기존 메모리 {len(plan.memory_snapshot)}개 전체 목록 연결·적용 전후 해시 확인. 대화의 미저장 내용은 이 목록에 포함되지 않습니다.')
    if target == 'codex':
        for home in dict.fromkeys(codex_homes):
            global_rule = home / 'AGENTS.md'
            global_text = global_rule.read_text(encoding='utf-8-sig') if global_rule.exists() else '# 사용자 소통 기본값\n'
            plan.write(global_rule, block(global_text, LANGUAGE))
            path = home / 'hooks.json'
            if path.exists():
                cleaned, removed = clean_codex_hooks(read_json(path))
                if removed:
                    plan.json(path, cleaned)
                    plan.notes.extend(f'{x["event"]}: {x["reason"]} 정리' for x in removed)
    else:
        global_rule = claude_home / 'CLAUDE.md'
        global_text = global_rule.read_text(encoding='utf-8-sig') if global_rule.exists() else '# 사용자 소통 기본값\n'
        plan.write(global_rule, block(global_text, LANGUAGE))
        settings_path = root / '.claude/settings.local.json'
        if not local_settings.get('autoMemoryDirectory'):
            local_settings['autoMemoryDirectory'] = str(dirs[0])
            plan.json(settings_path, local_settings)
        # A Codex-only project may own its protection config in .codex.
        # Hooks can read that original directly; do not duplicate it.
    plan.notes.append('기존 규칙·메모리 원본·권한·인증·대화 기록은 보존합니다. 플러그인 설치·훅 신뢰는 별도 검증합니다.')
    return plan


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='프로젝트 양방향 적용: 기본은 변경 예정 목록만 출력')
    parser.add_argument('target', choices=['codex', 'claude'])
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--claude-home', type=Path, default=Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))))
    parser.add_argument('--codex-home', type=Path, action='append', default=[])
    parser.add_argument('--memory', type=Path, action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.project.resolve()
    if not root.is_dir():
        parser.error('프로젝트 폴더가 없습니다.')
    homes = [Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).resolve()]
    homes.extend(p.resolve() for p in args.codex_home)
    try:
        plan = make_plan(args.target, root, args.claude_home.resolve(), homes, args.memory)
        report = {'대상': args.target, '변경파일': [str(p) for p in plan.changes], '안내': plan.notes}
        if args.apply:
            backup = plan.apply()
            report['백업'] = str(backup) if backup else None
            report['적용'] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(f'적용 중단: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
