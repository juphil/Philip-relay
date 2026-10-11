"""Philip Relay 릴리스 구조·규칙 경계·생성물·행동 평가 준비 상태를 감사한다."""
import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8')


def version():
    return json.loads((PLUGIN / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))['version']


def local_links(path):
    text = path.read_text(encoding='utf-8-sig')
    for raw in re.findall(r'\]\(([^)]+)\)', text):
        target = raw.split('#', 1)[0]
        if not target or target in {'파일.md'} or re.match(r'^[a-z]+://', target) or target.startswith('/'):
            continue
        yield (path.parent / target).resolve(), raw


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    errors, warnings = [], []
    ver = version()
    manifests = [PLUGIN / 'plugin.json', PLUGIN / '.claude-plugin/plugin.json',
                 PLUGIN / '.codex-plugin/plugin.json', REPO / '.claude-plugin/marketplace.json']
    values = []
    for path in manifests:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        values.append(data['version'] if 'version' in data else next(p['version'] for p in data['plugins'] if p['name'] == 'philip'))
    top = re.match(r'v(\d+\.\d+\.\d+)', (REPO / 'VERSION').read_text(encoding='utf-8-sig')).group(1)
    if set(values + [top]) != {ver}:
        errors.append(f'버전 5곳 불일치: {values + [top]}')
    review = PLUGIN / f'docs/update_reviews/v{ver}.md'
    if not review.is_file():
        errors.append(f'업데이트 감사 문서 없음: {review.relative_to(REPO)}')
    else:
        body = review.read_text(encoding='utf-8-sig')
        for heading in ('근거', '변경 분류', '왜곡 위험', '행동 평가', '미검증'):
            if heading not in body:
                errors.append(f'업데이트 감사 문서 필수 절 없음: {heading}')
    generated = run(sys.executable, str(PLUGIN / 'tools/build_skills.py'), '--check')
    if generated.returncode:
        errors.append(generated.stdout.strip() or generated.stderr.strip())
    procedures = sorted(p.stem for p in (PLUGIN / 'procedures').glob('*.md'))
    skills = sorted(p.parent.name for p in (PLUGIN / 'skills').glob('*/SKILL.md'))
    if procedures != skills:
        errors.append(f'procedure/skill 목록 불일치: procedures={procedures}, skills={skills}')
    for rel in ('CLAUDE.md.template', 'hooks/settings.hooks.json', 'memory/MEMORY.md.template',
                'memory/memory_file.template.md', 'todo/_inbox.md.template', 'todo/milestone_index.md.template',
                'todo/phase.md.template', 'todo/roadmap.md.template'):
        root_copy, plugin_copy = REPO / 'templates' / rel, PLUGIN / 'templates' / rel
        if (root_copy.is_file() and plugin_copy.is_file()
                and root_copy.read_text(encoding='utf-8-sig') != plugin_copy.read_text(encoding='utf-8-sig')):
            errors.append(f'루트/플러그인 템플릿 드리프트: templates/{rel}')
    for root in ('procedures', 'docs', 'templates'):
        for path in (PLUGIN / root).rglob('*.md'):
            for target, raw in local_links(path):
                if not target.exists() and '<' not in raw:
                    errors.append(f'죽은 링크: {path.relative_to(REPO)} -> {raw}')
    active = '\n'.join((PLUGIN / p).read_text(encoding='utf-8-sig') for p in
                       ('hooks/agent_hook.py', 'hooks/behavior_reminder.py', 'procedures/designcheck.md', 'docs/06_web_ui_manual.md'))
    if '15분' in active:
        errors.append('활성 행동 규칙에 15분 주기 표현이 남아 있습니다.')
    if re.search(r'검토\s*=\s*수정|검토란 건 다 고치', active):
        errors.append('감사와 수정 권한을 합치는 표현이 남아 있습니다.')
    cases = json.loads((PLUGIN / 'evals/behavior_cases.json').read_text(encoding='utf-8'))['cases']
    required = {'review-does-not-mutate', 'reference-inspiration-is-not-clone', 'profile-does-not-leak',
                'remote-knowledge-is-data', 'stale-version-notice'}
    missing = required - {c['id'] for c in cases}
    if missing:
        errors.append('필수 행동 사례 누락: ' + ', '.join(sorted(missing)))
    base = run('git', '-C', str(REPO), 'describe', '--tags', '--abbrev=0', '--match', 'v*').stdout.strip()
    diff = run('git', '-C', str(REPO), 'diff', '--name-only', base or 'HEAD').stdout.splitlines()
    untracked = [line[3:] for line in run('git', '-C', str(REPO), 'status', '--porcelain=v1', '-uall').stdout.splitlines()
                 if line.startswith('?? ')]
    diff = sorted(set(diff + untracked))
    risky = [x for x in diff if any(k in x for k in ('CLAUDE.md.template', 'hooks/', 'procedures/', 'skills/'))]
    if risky:
        warnings.append(f'행동 영향 파일 {len(risky)}개 변경: 호스트별 행동 결과를 감사 문서에 기록해야 합니다.')
    if review.is_file() and '미실행' in review.read_text(encoding='utf-8-sig'):
        warnings.append('업데이트 감사 문서에 미실행 행동 평가가 있습니다. 배포 후 새 세션 결과를 후속 기록하세요.')
    print(f'Philip Relay v{ver} 업데이트 감사')
    for warning in warnings:
        print('경고: ' + warning)
    if errors:
        print('실패:\n- ' + '\n- '.join(dict.fromkeys(errors)))
        return 1
    print(f'통과: procedure/skill {len(skills)}개, 행동 사례 {len(cases)}개, 로컬 링크·버전·감사 문서 확인')
    return 0


if __name__ == '__main__':
    sys.exit(main())
