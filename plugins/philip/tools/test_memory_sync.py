"""Isolated CLI regression tests; no remote access."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import importlib.util
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
HOOK_SPEC = importlib.util.spec_from_file_location('agent_hook_for_test', PLUGIN / 'hooks/agent_hook.py')
HOOK = importlib.util.module_from_spec(HOOK_SPEC)
HOOK_SPEC.loader.exec_module(HOOK)
MEM_SPEC = importlib.util.spec_from_file_location('mem_sync_for_test', PLUGIN / 'tools/mem_sync.py')
MEM_SYNC = importlib.util.module_from_spec(MEM_SPEC)
MEM_SPEC.loader.exec_module(MEM_SYNC)


class MemoryTests(unittest.TestCase):
    def test_git_pathspec_is_posix_relative_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'project' / 'MEMORY.md'
            self.assertEqual(MEM_SYNC.git_relative(path, root), 'project/MEMORY.md')

    def test_project_config_supplies_memory_sync_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project-root'
            (root / '.claude').mkdir(parents=True)
            (root / '.psp').mkdir()
            (root / 'memory').mkdir()
            (root / '.claude/psp.config.json').write_text(
                json.dumps({'memory': {'url': 'ssh://example.invalid/memory.git', 'slug': 'stable-project'}}),
                encoding='utf-8')
            (root / '.psp/runtime.json').write_text(json.dumps({'memory_dirs': ['memory']}), encoding='utf-8')
            args = type('Args', (), {'project': str(root), 'url': None, 'slug': None, 'memdir': None})()
            MEM_SYNC.resolve_project_defaults(args)
            self.assertEqual(args.url, 'ssh://example.invalid/memory.git')
            self.assertEqual(args.slug, 'stable-project')
            self.assertEqual(Path(args.memdir), root / 'memory')

    def test_multiple_memory_dirs_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project-root'
            (root / '.psp').mkdir(parents=True)
            (root / 'memory').mkdir()
            (root / '.psp/runtime.json').write_text(
                json.dumps({'memory_dirs': [str(Path(tmp) / 'auto-memory'), 'memory']}), encoding='utf-8')
            args = type('Args', (), {'project': str(root), 'url': 'x', 'slug': 's', 'memdir': None})()
            with self.assertRaises(ValueError):
                MEM_SYNC.resolve_project_defaults(args)

    def test_multiple_memory_dirs_cli_uses_safety_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project-root'
            (root / '.psp').mkdir(parents=True)
            (root / 'memory').mkdir()
            (root / 'other').mkdir()
            (root / '.psp/runtime.json').write_text(
                json.dumps({'memory_dirs': ['memory', 'other']}), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(PLUGIN / 'tools/mem_sync.py'), 'push', '--project', str(root),
                 '--url', 'x', '--slug', 's'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 6)
            self.assertIn('중단:', result.stdout)

    def test_index_overwrite_that_drops_retained_memories_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'small', Path(tmp) / 'slot'
            src.mkdir(); dst.mkdir()
            (src / 'MEMORY.md').write_text('- [c](c.md)\n', encoding='utf-8')
            (src / 'c.md').write_text('c', encoding='utf-8')
            (dst / 'MEMORY.md').write_text('- [a](a.md) · [b](b.md)\n', encoding='utf-8')
            (dst / 'a.md').write_text('a', encoding='utf-8')
            (dst / 'b.md').write_text('b', encoding='utf-8')
            plan = type('Args', (), {'apply': False, 'allow_index_drop': False})()
            with self.assertRaises(ValueError):
                MEM_SYNC.safe_transfer(src, dst, plan)
            plan.allow_index_drop = True
            self.assertIsNone(MEM_SYNC.safe_transfer(src, dst, plan))
            (src / 'MEMORY.md').write_text('- [a](a.md) · [b](b.md) · [c](c.md)\n', encoding='utf-8')
            plan.allow_index_drop = False
            self.assertIsNone(MEM_SYNC.safe_transfer(src, dst, plan))

    def test_pending_push_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, repo, mem = root / 'remote.git', root / 'repo', root / 'memory'
            mem.mkdir()
            def run(args, cwd=None):
                result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout.strip()
            run(['git', 'init', '--bare', str(remote)])
            run(['git', 'clone', str(remote), str(repo)])
            def git(*args):
                return run(['git', *args], repo)
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            (repo / 'README').write_text('seed')
            git('add', 'README'); git('commit', '-m', 'seed'); git('push', '-u', 'origin', 'HEAD')
            (mem / 'MEMORY.md').write_text('A')
            args = [sys.executable, str(PLUGIN / 'tools/mem_sync.py'), 'push', '--repo', str(repo),
                    '--slug', 'project', '--memdir', str(mem), '--apply']
            run(args)
            run(args + ['--gitpush'])
            self.assertEqual(git('rev-parse', 'HEAD'), run(['git', '--git-dir', str(remote), 'rev-parse', 'HEAD']))
            (repo / 'project/unrelated.txt').write_text('keep private draft')
            git('add', 'project/unrelated.txt')
            (mem / 'MEMORY.md').write_text('B')
            run(args)
            self.assertNotIn('unrelated.txt', git('show', '--format=', '--name-only', 'HEAD'))
            self.assertIn('unrelated.txt', git('diff', '--cached', '--name-only'))
            (repo / 'project/MEMORY.md').write_text('another writer')
            (mem / 'MEMORY.md').write_text('C')
            result = subprocess.run(args, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((repo / 'project/MEMORY.md').read_text(), 'another writer')
            (repo / 'project/MEMORY.md').write_text('C')
            git('add', 'project/MEMORY.md')
            result = subprocess.run(args + ['--gitpush'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('project/MEMORY.md', git('diff', '--cached', '--name-only'))

    def test_same_size_same_mtime_change_is_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, mem = root / 'repo', root / 'memory'
            mem.mkdir()

            def run(args, cwd=None):
                result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout.strip()

            run(['git', 'init', '-q', str(repo)])
            git = lambda *args: run(['git', *args], repo)
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            (repo / 'README').write_text('seed', encoding='utf-8')
            git('add', 'README')
            git('commit', '-qm', 'seed')
            (mem / 'MEMORY.md').write_text('A', encoding='utf-8')
            args = [sys.executable, str(PLUGIN / 'tools/mem_sync.py'), 'push', '--repo', str(repo),
                    '--slug', 'project', '--memdir', str(mem), '--apply']
            run(args)
            first = (mem / 'MEMORY.md').stat().st_mtime_ns
            time.sleep(1.1)
            (repo / 'project/unrelated.txt').write_text('draft', encoding='utf-8')
            git('add', 'project/unrelated.txt')
            (mem / 'MEMORY.md').write_text('B', encoding='utf-8')
            os.utime(mem / 'MEMORY.md', ns=(first, first))
            run(args)
            self.assertEqual(git('show', 'HEAD:project/MEMORY.md'), 'B')
            self.assertIn('unrelated.txt', git('diff', '--cached', '--name-only'))

    def test_two_collections_preview_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            def sync(folder, collection, apply=False):
                args = [sys.executable, str(PLUGIN / 'tools/mem_sync.py'), 'push',
                        '--repo', str(repo), '--slug', 'project', '--collection', collection,
                        '--memdir', str(folder)] + (['--apply'] if apply else [])
                result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            a, b = root / 'a', root / 'b'
            a.mkdir(); b.mkdir()
            (a / 'MEMORY.md').write_text('A')
            (a / 'fact.md').write_text('Keep A')
            (a / 'topics').mkdir()
            (a / 'topics/nested.md').write_text('Nested memory')
            (b / 'MEMORY.md').write_text('B')
            sync(a, 'legacy')
            self.assertFalse((repo / 'project').exists())
            sync(a, 'legacy', True)
            sync(b, 'local', True)
            legacy_source = root / 'old-memory'
            legacy_source.mkdir()
            (legacy_source / 'MEMORY.md').write_text('Original root memory')
            for mode, folder in [('push', legacy_source), ('pull', root / 'old-restored')]:
                result = subprocess.run([sys.executable, str(PLUGIN / 'tools/mem_sync.py'), mode,
                                         '--repo', str(repo), '--slug', 'project', '--memdir', str(folder), '--apply'],
                                        capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(p.relative_to(root / 'old-restored').as_posix()
                                    for p in (root / 'old-restored').rglob('*.md')), ['MEMORY.md'])
            self.assertEqual((repo / '.psp-collections/project/legacy/topics/nested.md').read_text(), 'Nested memory')
            restored = root / 'restored'
            result = subprocess.run([sys.executable, str(PLUGIN / 'tools/mem_sync.py'), 'pull',
                                     '--repo', str(repo), '--slug', 'project', '--collection', 'legacy',
                                     '--memdir', str(restored), '--apply'], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((restored / 'topics/nested.md').read_text(), 'Nested memory')
            self.assertEqual((repo / '.psp-collections/project/legacy/MEMORY.md').read_text(), 'A')
            self.assertEqual((repo / '.psp-collections/project/local/MEMORY.md').read_text(), 'B')
            (a / 'fact.md').unlink()
            sync(a, 'legacy', True)
            self.assertEqual((repo / '.psp-collections/project/legacy/fact.md').read_text(), 'Keep A')

    def test_handoff_after_line_40_without_roadmap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'AGENTS.md').write_text('Read handoff')
            (root / '.psp').mkdir()
            (root / 'todo').mkdir()
            (root / '.psp/runtime.json').write_text(json.dumps({'handoff_index': 'todo/index.md'}))
            (root / 'todo/index.md').write_text('Old context\n' * 60 + 'NEXT_ACTION_123\n')
            result = subprocess.run([sys.executable, str(PLUGIN / 'hooks/agent_hook.py'), 'session'],
                                    input=json.dumps({'cwd': str(root)}), capture_output=True,
                                    text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('NEXT_ACTION_123', context)

    def test_handoff_summary_has_a_real_utf8_byte_cap(self):
        long_line = '- [문서](detail.md) — ' + ('긴 설명 ' * 4000)
        text = '\n'.join([long_line] * 70 + ['다음 작업 = SAFE_NEXT_ACTION'])
        summary = HOOK._bounded_handoff(text)
        self.assertLessEqual(len(summary.encode('utf-8')), HOOK.HANDOFF_MAX_BYTES)
        self.assertIn('SAFE_NEXT_ACTION', summary)

    def test_memory_summary_keeps_every_link_on_multi_link_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / 'MEMORY.md'
            index.write_text('- [안전](feedback_a.md) · [추측](feedback_b.md) · [진술](feedback_c.md) — "…물을 때" 회수 트리거\n'
                             '- [서버](project_d.md) — 설명\n', encoding='utf-8')
            summary = HOOK._memory_index_summary([index])
            for name in ('feedback_a', 'feedback_b', 'feedback_c', 'project_d'):
                self.assertIn(name, summary)
            many = '\n'.join(f'- [t{i}](topic_{i:04d}.md) · [u{i}](other_{i:04d}.md)' for i in range(400))
            index.write_text(many, encoding='utf-8')
            summary = HOOK._memory_index_summary([index])
            self.assertLessEqual(len(summary.encode('utf-8')), HOOK.MEMORY_INDEX_MAX_BYTES)
            self.assertIn('생략', summary)   # 상한을 넘으면 조용히 버리지 않고 생략 수를 알린다

    def test_session_context_has_total_cap_and_memory_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'AGENTS.md').write_text('Read linked sources', encoding='utf-8')
            (root / '.psp').mkdir()
            (root / 'todo').mkdir()
            (root / 'memory').mkdir()
            (root / '.psp/runtime.json').write_text(
                json.dumps({'handoff_index': 'todo/index.md', 'memory_dirs': ['memory']}), encoding='utf-8')
            (root / 'todo/index.md').write_text(('오래된 상태\n' * 500) + '다음 작업 = SAFE_NEXT\n', encoding='utf-8')
            links = '\n'.join(f'- [topic {i}](topic-{i}.md) — ' + ('긴 설명 ' * 80) for i in range(100))
            (root / 'MEMORY.md').write_text(links, encoding='utf-8')
            (root / 'memory/MEMORY.md').write_text(links, encoding='utf-8')
            result = subprocess.run([sys.executable, str(PLUGIN / 'hooks/agent_hook.py'), 'session'],
                                    input=json.dumps({'cwd': str(root)}), capture_output=True,
                                    text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertLessEqual(len(context.encode('utf-8')), HOOK.SESSION_MAX_BYTES)
            self.assertIn('SAFE_NEXT', context)
            self.assertIn(str(root / 'MEMORY.md'), context)
            self.assertIn(str(root / 'memory/MEMORY.md'), context)

    def test_roadmap_current_handoff_wins_over_stale_runtime_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'AGENTS.md').write_text('Read handoff')
            (root / '.psp').mkdir()
            (root / 'todo/edge').mkdir(parents=True)
            (root / 'todo/secure').mkdir(parents=True)
            (root / '.psp/runtime.json').write_text(json.dumps({'handoff_index': 'todo/edge/index.md'}))
            (root / 'todo/roadmap.md').write_text('현재 = secure', encoding='utf-8')
            (root / 'todo/edge/index.md').write_text('STALE_EDGE')
            (root / 'todo/secure/index.md').write_text('ACTIVE_SECURE')
            result = subprocess.run([sys.executable, str(PLUGIN / 'hooks/agent_hook.py'), 'session'],
                                    input=json.dumps({'cwd': str(root)}), capture_output=True,
                                    text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('ACTIVE_SECURE', context)
            self.assertNotIn('STALE_EDGE', context)


if __name__ == '__main__':
    unittest.main()
