"""Behavior checks using isolated projects; never touch production assets."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'tools/agent_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_new_memory_after_plan_requires_rescan(self):
        self.write('memory/first.md', 'First')
        plan = bridge.make_plan('codex', self.root, self.ch, [self.co])
        self.write('memory/second.md', 'New fact')
        with self.assertRaises(ValueError):
            plan.apply()
        self.assertFalse((self.root / 'AGENTS.md').exists())
        bridge.make_plan('codex', self.root, self.ch, [self.co]).apply()
        self.assertIn('second.md', (self.root / '.psp/memory_inventory.md').read_text(encoding='utf-8'))

    def test_unavailable_registered_memory_preserves_configuration(self):
        missing = self.base / 'offline-memory'
        config = self.write('.psp/runtime.json', json.dumps({'memory_dirs': [str(missing)]}))
        original = config.read_bytes()
        for target in ('codex', 'claude'):
            with self.assertRaises(ValueError):
                bridge.make_plan(target, self.root, self.ch, [self.co])
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse((self.root / 'MEMORY.md').exists())
        missing.mkdir()
        (missing / 'fact.md').write_text('Recovered fact')
        bridge.make_plan('codex', self.root, self.ch, [self.co]).apply()
        self.assertIn('fact.md', (self.root / '.psp/memory_inventory.md').read_text(encoding='utf-8'))

    def test_invalid_settings_and_orphan_marker_stop_before_writes(self):
        with self.assertRaises(ValueError):
            bridge.block('orphan ' + bridge.END, 'replacement')
        self.write('.psp/runtime.json', '[]')
        with self.assertRaises(ValueError):
            bridge.make_plan('claude', self.root, self.ch, [self.co])
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        self.write('.psp/runtime.json', '{"memory_dirs":"not-a-list"}')
        with self.assertRaises(ValueError):
            bridge.make_plan('codex', self.root, self.ch, [self.co])

    def test_plan_rejects_intervening_changes(self):
        path = self.write('AGENTS.md', 'Original')
        plan = bridge.make_plan('claude', self.root, self.ch, [self.co])
        path.write_text('Concurrent writer', encoding='utf-8')
        with self.assertRaises(ValueError):
            plan.apply()
        self.assertEqual(path.read_text(), 'Concurrent writer')
        self.assertFalse((self.root / 'CLAUDE.md').exists())

    def test_nested_local_memory_and_handoff_preserved(self):
        self.write('memory/topic/note.md', 'Nested fact')
        self.write('.psp/runtime.json', '{"handoff_index":"todo/index.md","memory_collections":{"project":"memory"}}')
        plan = bridge.make_plan('claude', self.root, self.ch, [self.co])
        plan.apply()
        self.assertIn('topic/note.md', (self.root / 'memory/MEMORY.md').read_text(encoding='utf-8'))
        mapping = json.loads((self.root / '.psp/runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(mapping['handoff_index'], 'todo/index.md')
        self.assertEqual(mapping['memory_collections'], {'project': 'memory'})
        self.assertFalse(bridge.make_plan('claude', self.root, self.ch, [self.co]).changes)

    def test_stale_index_still_exposes_all_original_memory(self):
        self.write('memory/MEMORY.md', 'Old index without topic links')
        topic = self.write('memory/sub/missing.md', 'Original fact')
        self.write('claude/memory/legacy.md', 'Legacy fact')
        plan = bridge.make_plan('codex', self.root, self.ch, [self.co])
        plan.apply()
        inventory = (self.root / '.psp/memory_inventory.md').read_text(encoding='utf-8')
        self.assertIn('sub/missing.md', inventory)
        self.assertIn('legacy.md', inventory)
        self.assertEqual(topic.read_text(), 'Original fact')
        reverse = bridge.make_plan('claude', self.root, self.ch, [self.co])
        topic.write_text('Changed after plan')
        with self.assertRaises(ValueError):
            reverse.apply()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='psp-')
        self.base = Path(self.tmp.name)
        self.root = self.base / '한글 프로젝트'
        self.root.mkdir()
        self.ch = self.base / 'claude'
        self.co = self.base / 'codex'
        self.plugin = ROOT

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, text):
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def hook(self, mode, inp=None, shell=None):
        payload = json.dumps({'cwd': str(self.root), 'tool_input': inp or {}}, ensure_ascii=False).encode('utf-8')
        env = dict(os.environ, PLUGIN_ROOT=str(self.plugin), CLAUDE_PLUGIN_ROOT=str(self.plugin), PYTHONIOENCODING='utf-8')
        if shell:
            h = json.loads((ROOT / 'hooks/hooks.json').read_text())['hooks']
            event = {'guard':'PreToolUse','session':'SessionStart','reminder':'UserPromptSubmit'}[mode]
            cmd = h[event][0]['hooks'][0]['command']
            args = [shell, '-NoProfile', '-Command', cmd] if 'powershell' in shell.lower() else [shell, '-c', cmd]
        else:
            args = [sys.executable, str(ROOT / 'hooks/agent_hook.py'), mode]
        result = subprocess.run(args, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, cwd=self.base, timeout=20,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        if result.stdout.strip():
            out = json.loads(result.stdout)['hookSpecificOutput']
            if out.get('permissionDecision') == 'deny':
                result.returncode = 2  # Logical denial, not a failed hook process.
            result.stdout = out.get('additionalContext', '').encode('utf-8')
        return result

    def test_claude_to_codex_preserves_source_and_is_idempotent(self):
        original = self.write('CLAUDE.md', '# Existing rule\nDo not overwrite models.\n')
        mem = self.ch / 'projects' / bridge.encoded_project(self.root) / 'memory'
        mem.mkdir(parents=True)
        (mem / 'MEMORY.md').write_text('Important memory', encoding='utf-8')
        self.co.mkdir()
        foreign = {'hooks': {'PreToolUse': [{'hooks': [
            {'type':'command','command':'C:/Users/a/.orca/agent-hooks/claude-hook.cmd || echo {}'},
            {'type':'command','command':'custom-validator'},
            {'type':'command','command':'C:/Users/a/.orca/agent-hooks/codex-hook.cmd'}]}]}}
        (self.co / 'hooks.json').write_text(json.dumps(foreign))
        plan = bridge.make_plan('codex', self.root, self.ch, [self.co])
        self.assertFalse((self.root / 'AGENTS.md').exists())
        backup = plan.apply()
        self.assertTrue((backup / 'manifest.json').is_file())
        self.assertIn('Do not overwrite models.', original.read_text(encoding='utf-8'))
        self.assertIn('CLAUDE.md', (self.root / 'AGENTS.md').read_text(encoding='utf-8'))
        self.assertEqual((mem / 'MEMORY.md').read_text(), 'Important memory')
        after = json.loads((self.co / 'hooks.json').read_text())
        self.assertEqual(len(after['hooks']['PreToolUse'][0]['hooks']), 2)
        self.assertFalse(bridge.make_plan('codex', self.root, self.ch, [self.co]).changes)

    def test_external_memory_without_index_is_linked_and_preserved(self):
        external = self.base / 'external'
        external.mkdir()
        note = external / 'fact.md'
        note.write_bytes(b'Original fact')
        bridge.make_plan('codex', self.root, self.ch, [self.co], [external]).apply()
        self.assertIn(note.as_posix(), (self.root / 'MEMORY.md').read_text(encoding='utf-8'))
        self.assertEqual(note.read_bytes(), b'Original fact')
        self.assertFalse((external / 'MEMORY.md').exists())
        self.assertFalse(bridge.make_plan('codex', self.root, self.ch, [self.co], [external]).changes)

    def test_damaged_managed_block_is_rejected(self):
        for text in [bridge.END + bridge.START, bridge.START + bridge.END + bridge.END]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                bridge.block(text, 'replacement')

    def test_codex_to_claude_and_roundtrip(self):
        self.write('AGENTS.md', '# Existing coding rules\n')
        self.write('memory/fact.md', 'Preserve this')
        self.write('.claude/settings.local.json', json.dumps({'permissions': {'allow':['Read']}}))
        bridge.make_plan('claude', self.root, self.ch, [self.co]).apply()
        settings = json.loads((self.root / '.claude/settings.local.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['permissions']['allow'], ['Read'])
        self.assertEqual(Path(settings['autoMemoryDirectory']), self.root / 'memory')
        self.assertIn('AGENTS.md', (self.root / 'CLAUDE.md').read_text(encoding='utf-8'))
        self.assertFalse(bridge.make_plan('claude', self.root, self.ch, [self.co]).changes)
        bridge.make_plan('codex', self.root, self.ch, [self.co]).apply()
        self.assertFalse(bridge.make_plan('codex', self.root, self.ch, [self.co]).changes)

    def test_guard_multi_patch_move_and_normalized_paths(self):
        self.write('.claude/psp.config.json', json.dumps({'guard': {'protect':['checkpoints/*'], 'allow':['checkpoints/allowed.pt']}}))
        cases = [({'file_path':'main.py'},0), ({'file_path':'.env'},2),
                 ({'file_path':'checkpoints/a.pt'},2), ({'file_path':'checkpoints/allowed.pt'},0),
                 ({'file_path':'checkpoints/allowed.pt.extra'},2),
                 ({'file_path':'src/../checkpoints/a.pt'},2),
                 ({'command':'*** Begin Patch\n*** Update File: main.py\n*** Delete File: checkpoints/a.pt\n*** End Patch'},2),
                 ({'command':'*** Begin Patch\n*** Update File: main.py\n*** Move to: checkpoints/a.pt\n*** End Patch'},2),
                 ({'command':'*** Begin Patch\n*** Add File: module.py\n+x\n*** End Patch'},0),
                 ({'file_path':'datasets_tools/x.py'},0), ({},2)]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                r = self.hook('guard',inp)
                self.assertEqual(r.returncode, expected, r.stderr.decode('utf-8','replace'))

    def test_context_memory_todo_and_language(self):
        self.write('AGENTS.md', 'Rules')
        self.write('MEMORY.md', 'Shared index marker')
        self.write('todo/roadmap.md', '현재 = secure')
        self.write('todo/secure/index.md', 'Current milestone marker')
        r = self.hook('session')
        self.assertEqual(r.returncode,0,r.stderr)
        for marker in ['Shared index marker','Current milestone marker','한국어']:
            self.assertIn(marker,r.stdout.decode('utf-8'))
        first, second = self.hook('reminder'), self.hook('reminder')
        self.assertIn('행동매뉴얼',first.stdout.decode('utf-8'))
        self.assertNotIn('행동매뉴얼',second.stdout.decode('utf-8'))
        self.assertIn('한국어',second.stdout.decode('utf-8'))

    def test_registered_commands_in_actual_shells(self):
        self.write('AGENTS.md','Rules')
        self.plugin = self.base / '한글 플러그인'
        shutil.copytree(ROOT / 'hooks', self.plugin / 'hooks')
        shells = [shutil.which('powershell.exe')] if os.name == 'nt' else []
        bash = Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt' else Path('/bin/bash')
        if bash.is_file(): shells.append(str(bash))
        for shell in filter(None,shells):
            for mode,inp,code in [('guard',{'file_path':'main.py'},0),('guard',{'file_path':'.env'},2),('session',{},0),('reminder',{},0)]:
                with self.subTest(shell=shell,mode=mode):
                    r=self.hook(mode,inp,shell)
                    self.assertEqual(r.returncode,code,r.stderr.decode('utf-8','replace'))

    def test_long_memory_keeps_last_topic(self):
        self.write('AGENTS.md','Rules')
        self.write('MEMORY.md','\n'.join(f'- [Topic {i}](topic_{i}.md) — '+('detail '*500) for i in range(72)))
        out=self.hook('session').stdout.decode('utf-8')
        self.assertIn('topic_0.md',out)
        self.assertIn('topic_71.md',out)

    def test_protected_symlink_name(self):
        p=self.write('ordinary.txt','data')
        try:
            (self.root / '.env').symlink_to(p)
        except OSError:
            self.skipTest('Symlink privileges unavailable')
        self.assertEqual(self.hook('guard',{'file_path':'.env'}).returncode,2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
