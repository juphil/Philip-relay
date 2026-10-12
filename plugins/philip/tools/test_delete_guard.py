"""삭제 가드 훅·safe_delete 회귀 시험 (docs/08_destructive_ops.md)."""
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import version_state

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'hooks' / 'agent_hook.py'
TOOL = ROOT / 'tools' / 'safe_delete.py'
TMP = tempfile.gettempdir().replace('\\', '/')

CASES = [
    ('git clean -fdxq -e .claude', True), ('git clean -n -fdx', False), ('git clean -fdn', False),
    ('rm -rf SIA_deploy/SIA/result', True), (f'rm -rf {TMP}/x', False), ('rm -f C:/x/scratchpad/a.txt', False),
    ('Remove-Item -Recurse -Force foo', True), ('Remove-Item foo -WhatIf', False),
    ('git reset --hard origin/main', True), ('git reset --soft HEAD~1', False),
    ('git checkout -- .', True), ('git checkout .', True), ('git checkout HEAD important.txt', True),
    ('git checkout main', False), ('git restore --staged a.py', False), ('git restore a.py', True),
    ('git push --force origin main', True), ('git push --force-with-lease origin main', False),
    ('git push origin main', False), ('git branch -D old', True), ('git stash drop', True),
    ("git commit -m 'rm old; cleanup'", False),
    ('python -c "import shutil; shutil.rmtree(\'data\')"', True),
    (f'python -c "import shutil; shutil.rmtree(r\'{TMP}/q\')"', False),
    ('powershell -NoProfile -Command "Remove-Item C:/proj/x -Recurse"', True), ("grep -rn 'Remove-Item' docs", False),
    ('ls -la; echo rm is a word', False), ('cd x && del /s /q build', True), ('python tools/safe_delete.py a b --yes', False),
    ('echo safe_delete.py && rm -rf important', True),
    ('Stop-Process -Id 12 -Force', False), ('rm -rf $S', True), ('cmd //c "rd /s /q build"', True), ("bash -c 'git clean -fdx'", True),
    ('cmd /c del important.txt', True),
    ('git clone -q https://x/y.git /tmp/y && cd /tmp/y && git checkout --orphan tool && git rm -rfq --cached .', False),
    (f'cd {TMP}/scratchpad && rm -rf chrome_bd2 2>/dev/null', False),
    (f'cd {TMP}/psp-check && git restore --source=HEAD :/', False),
    (f'git -C {TMP}/psp-check restore --source=HEAD :/', False),
    ('git -C C:/important/project restore --source=HEAD :/', True),
    ('git -C C:/important/project clean -fdx', True),
    ('git -C C:/important/project reset --hard HEAD', True),
    ('git -C C:/important/project checkout --orphan rewrite', True),
    (f'git -C {TMP}/repo --work-tree C:/important/work restore --source=HEAD :/', True),
    (f'git -C {TMP}/repo --git-dir C:/important/repo.git reset --hard HEAD', True),
    # 2026-10-11 추가: rm 계열이 아닌 영구 삭제(find·rsync·truncate)
    ('find todo -delete', True), ('find . -name "*.log" -delete', True), ('find todo -exec rm -rf {} +', True),
    ('find todo -type f -execdir /bin/rm {} ;', True), (f'find {TMP}/scratch -delete', False),
    ('find todo -name "*.md"', False), ('find . -exec grep -n rm {} +', False),
    ('rsync -a --delete empty/ todo/', True), ('rsync -a --delete-after src/ C:/important/dst/', True),
    ('rsync -a --delay-updates src/ backup/', False),
    (f'rsync -a --delete src/ {TMP}/mirror/', False), ('rsync -a src/ backup/', False),
    ('rsync -a --remove-source-files data/ backup/', True),
    ('truncate -s 0 MEMORY.md', True), (f'truncate -s 0 {TMP}/x.log', False),
    ('git push origin +main', True), ('git push origin +HEAD:main', True),
    ('git push -u origin +feature', True),
    ('git push --force-with-lease origin +main', False),
    ('git push origin main:main', False), ('git push origin HEAD', False),
    ('git push origin v1.0.0', False),
]


def hook(command):
    ordinary = 'C:/philip-test-project' if os.name == 'nt' else '/opt/philip-test-project'
    payload = json.dumps({'cwd': ordinary, 'tool_input': {'command': command}}).encode('utf-8')
    r = subprocess.run([sys.executable, str(HOOK), 'deleteguard'], input=payload, capture_output=True, timeout=20)
    out = r.stdout.decode('utf-8', 'replace').strip()
    return bool(out) and json.loads(out)['hookSpecificOutput'].get('permissionDecision') == 'deny'


class SingleVersion(unittest.TestCase):
    def test_four_places_same_version(self):
        repo = version_state.find_source_repo(ROOT)
        self.assertIsNotNone(repo, '원본 또는 marketplace 저장소를 찾지 못해 버전 4곳을 검증할 수 없습니다.')
        claude = json.loads((ROOT / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))['version']
        codex = json.loads((ROOT / '.codex-plugin' / 'plugin.json').read_text(encoding='utf-8'))['version']
        market = next(p['version'] for p in json.loads((repo / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))['plugins'] if p['name'] == 'philip')
        top = (repo / 'VERSION').read_text(encoding='utf-8').split()[0].lstrip('v')
        self.assertRegex(claude, r'^\d+\.\d+\.\d+$')
        self.assertEqual({claude, codex, market, top}, {claude}, '클로드·코덱스 매니페스트·marketplace·VERSION 버전은 같아야 한다')


class DeleteGuard(unittest.TestCase):
    def test_cases(self):
        for command, blocked in CASES:
            with self.subTest(command=command):
                self.assertEqual(hook(command), blocked)

    def test_quarantine_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / 'proj'
            (proj / 'sub').mkdir(parents=True)
            (proj / 'sub' / 'a.txt').write_text('a', encoding='utf-8')
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj), PYTHONIOENCODING='utf-8')
            run = lambda *a: subprocess.run([sys.executable, str(TOOL), *a], cwd=proj, env=env, capture_output=True, timeout=60)
            run('sub')                                               # 미리보기 = 그대로 있어야
            self.assertTrue((proj / 'sub' / 'a.txt').exists())
            run('sub', '--quarantine', '--yes')
            self.assertFalse((proj / 'sub').exists())
            sessions = list((proj / '_quarantine').iterdir())
            self.assertEqual(len(sessions), 1)
            self.assertIn('a.txt', (sessions[0] / 'manifest.tsv').read_text(encoding='utf-8'))
            run('--restore', sessions[0].name, '--yes')
            self.assertEqual((proj / 'sub' / 'a.txt').read_text(encoding='utf-8'), 'a')
            r = run('--purge-older-than', '5', '--yes')                # 최소 보존 30일
            self.assertTrue(sessions[0].exists())

    def test_permanent_delete_requires_explicit_user_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / 'proj'
            proj.mkdir()
            target = proj / 'approved.txt'
            target.write_text('remove me', encoding='utf-8')
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj), PYTHONIOENCODING='utf-8')
            run = lambda *a: subprocess.run([sys.executable, str(TOOL), *a], cwd=proj, env=env,
                                             capture_output=True, timeout=60)
            preview = run(str(target), '--permanent')
            self.assertEqual(preview.returncode, 0)
            self.assertTrue(target.exists())
            refused = run(str(target), '--permanent', '--yes')
            self.assertNotEqual(refused.returncode, 0)
            self.assertTrue(target.exists())
            approved = run(str(target), '--permanent', '--confirmed-by-user', '--yes')
            self.assertEqual(approved.returncode, 0)
            self.assertFalse(target.exists())

    def test_permanent_delete_refuses_project_root(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / 'proj'
            proj.mkdir()
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj), PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, str(TOOL), str(proj), '--permanent',
                                     '--confirmed-by-user', '--yes'], cwd=proj, env=env,
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(proj.exists())

    def test_permanent_delete_refuses_ancestors_of_protected_roots(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d) / 'workspace'
            proj = parent / 'proj'
            proj.mkdir(parents=True)
            sentinel = parent / 'sentinel.txt'
            sentinel.write_text('keep', encoding='utf-8')
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj), PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, str(TOOL), str(parent), '--permanent',
                                     '--confirmed-by-user', '--yes'], cwd=proj, env=env,
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(sentinel.exists())
        spec = importlib.util.spec_from_file_location('safe_delete_for_test', TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        home = Path.home().resolve()
        self.assertTrue(module._protected_permanent_root(home.parent, None))
        self.assertFalse(module._protected_permanent_root(home / 'philip-not-a-root-check', None))

    def test_permanent_ancestor_refused_without_claude_project_dir(self):
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        env['PYTHONIOENCODING'] = 'utf-8'
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d) / 'workspace'
            proj = parent / 'proj'
            proj.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(proj)], check=True)
            sentinel = parent / 'sentinel.txt'
            sentinel.write_text('keep', encoding='utf-8')
            result = subprocess.run([sys.executable, str(TOOL), str(parent), '--permanent',
                                     '--confirmed-by-user', '--yes'], cwd=proj, env=env,
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(sentinel.exists())

            plain = Path(d) / 'plain'
            (plain / 'proj').mkdir(parents=True)
            keep = plain / 'keep.txt'
            keep.write_text('keep', encoding='utf-8')
            result = subprocess.run([sys.executable, str(TOOL), str(plain), '--permanent',
                                     '--confirmed-by-user', '--yes', '--root', str(plain / 'proj')],
                                    cwd=Path(d), env=env, capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(keep.exists())

            target = proj / 'approved.txt'
            target.write_text('remove me', encoding='utf-8')
            result = subprocess.run([sys.executable, str(TOOL), str(target), '--permanent',
                                     '--confirmed-by-user', '--yes'], cwd=proj, env=env,
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(target.exists())


class RuleSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('agent_hook_for_test', HOOK)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_session_conflict_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            claude = root / 'CLAUDE.md'
            agents = root / 'AGENTS.md'
            claude.write_text('Claude change', encoding='utf-8')
            agents.write_text('Codex change', encoding='utf-8')
            message = self.module.rulesync(root)
            self.assertIn('자동 덮어쓰지 않았습니다', message)
            self.assertEqual(claude.read_text(encoding='utf-8'), 'Claude change')
            self.assertEqual(agents.read_text(encoding='utf-8'), 'Codex change')

    def test_identical_files_with_both_names_do_not_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            text = 'AGENTS.md와 CLAUDE.md는 같은 내용을 유지합니다.'
            (root / 'CLAUDE.md').write_text(text, encoding='utf-8')
            (root / 'AGENTS.md').write_text(text, encoding='utf-8')
            self.assertEqual(self.module.rulesync(root), '')

    def test_explicit_source_backs_up_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'CLAUDE.md').write_text('CLAUDE.md Claude/Co-Authored new', encoding='utf-8')
            (root / 'AGENTS.md').write_text('independent old', encoding='utf-8')
            old_local = os.environ.get('LOCALAPPDATA')
            os.environ['LOCALAPPDATA'] = str(root / 'local')
            try:
                self.module.rulesync(root, 'CLAUDE.md')
            finally:
                if old_local is None:
                    os.environ.pop('LOCALAPPDATA', None)
                else:
                    os.environ['LOCALAPPDATA'] = old_local
            backups = list((root / 'local/philip-relay/rulesync-backups').rglob('*-AGENTS.md'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding='utf-8'), 'independent old')
            self.assertEqual((root / 'AGENTS.md').read_text(encoding='utf-8'), 'AGENTS.md Codex/Co-Authored new')


if __name__ == '__main__':
    unittest.main()
