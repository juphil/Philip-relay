import json
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import knowledge_check
import update_notice
import version_state
import update_preflight
import version_check


class KnowledgeRegistry(unittest.TestCase):
    def source(self, ref='v1.2.3'):
        return {'id':'game-core','domain':'game','repo':'https://example.com/repo.git','ref':ref,
                'entry':'game/INDEX.md','authority':'user-approved','mode':'advisory',
                'reviewed_at':'2026-10-11','license':'private'}

    def test_pinned_source_passes(self):
        self.assertEqual(knowledge_check.validate({'schema_version':1,'sources':[self.source()]}), [])

    def test_moving_ref_and_escape_fail(self):
        source = self.source('main')
        source['entry'] = '../secret.md'
        self.assertGreaterEqual(len(knowledge_check.validate({'schema_version':1,'sources':[source]})), 2)


class UpdateNotice(unittest.TestCase):
    def test_semver(self):
        self.assertEqual(update_notice.semver('v2.10.0 (date)'), '2.10.0')
        self.assertEqual(update_notice.semver('bad'), '')
        self.assertGreater(update_notice.version_tuple('2.10.0'), update_notice.version_tuple('2.9.1'))

    def test_project_reviewed_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.psp').mkdir()
            (root / '.psp/runtime.json').write_text(json.dumps({'psp_reviewed_version':'2.9.1'}), encoding='utf-8')
            self.assertEqual(update_notice.reviewed_version(root), '2.9.1')

    def test_remote_uses_authenticated_git_and_not_raw_url(self):
        source = (ROOT / 'tools/update_notice.py').read_text(encoding='utf-8')
        self.assertNotIn('raw.githubusercontent.com', source)
        self.assertIn('remote_release', source)

    def test_installed_layout_finds_marketplace_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo = home / '.codex/.tmp/marketplaces/philip-relay'
            (repo / 'plugins/philip').mkdir(parents=True)
            subprocess.run(['git', 'init', str(repo)], check=True, capture_output=True)
            plugin = home / '.codex/plugins/cache/philip-relay/philip/0.1.1'
            plugin.mkdir(parents=True)
            self.assertEqual(version_state.find_source_repo(plugin, home=home), repo)

    def test_remote_release_does_not_trust_first_stale_host_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            remote, seed = base / 'remote.git', base / 'seed'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', 'clone', str(remote), str(seed)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(seed), 'config', 'user.name', 'Test'], check=True)
            subprocess.run(['git', '-C', str(seed), 'config', 'user.email', 'test@example.invalid'], check=True)
            (seed / 'plugins/philip').mkdir(parents=True)
            (seed / 'VERSION').write_text('v1.0.0\n')
            (seed / 'plugins/philip/marker').write_text('old')
            subprocess.run(['git', '-C', str(seed), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(seed), 'commit', '-m', 'old'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(seed), 'push', 'origin', 'HEAD:main'], check=True, capture_output=True)
            stale = base / 'home/.codex/.tmp/marketplaces/philip-relay'
            fresh = base / 'home/.claude/plugins/marketplaces/philip-relay'
            stale.parent.mkdir(parents=True)
            subprocess.run(['git', 'clone', '-b', 'main', str(remote), str(stale)], check=True, capture_output=True)
            (seed / 'VERSION').write_text('v1.1.0\n')
            subprocess.run(['git', '-C', str(seed), 'commit', '-am', 'new'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(seed), 'push', 'origin', 'HEAD:main'], check=True, capture_output=True)
            fresh.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', '-b', 'main', str(remote), str(fresh)], check=True, capture_output=True)
            plugin = base / 'home/.codex/plugins/cache/philip-relay/philip/1.0.0'
            plugin.mkdir(parents=True)
            version, commit, source = version_state.remote_release(plugin, home=base / 'home')
            self.assertEqual(version, '1.1.0')
            self.assertTrue(commit)
            self.assertEqual(source, fresh)


class UpdatePreflight(unittest.TestCase):
    def test_dirty_marketplace_fails_closed_when_git_status_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                update_preflight.dirty_marketplace(Path(tmp) / 'missing')

    def test_dirty_marketplace_and_cache_are_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, source = Path(tmp), Path(tmp) / 'source'
            subprocess.run(['git', 'init', str(source)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(source), 'config', 'user.name', 'Test'], check=True)
            subprocess.run(['git', '-C', str(source), 'config', 'user.email', 'test@example.invalid'], check=True)
            (source / 'plugins/philip').mkdir(parents=True)
            (source / 'plugins/philip/a.txt').write_text('original')
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), 'commit', '-m', 'release'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(source), 'tag', 'v1.0.0'], check=True)
            market = base / 'home/.claude/plugins/marketplaces/philip-relay'
            market.parent.mkdir(parents=True)
            subprocess.run(['git', 'clone', str(source), str(market)], check=True, capture_output=True)
            (market / 'plugins/philip/a.txt').write_text('market edit')
            cache = base / 'home/.codex/plugins/cache/philip-relay/philip/1.0.0'
            cache.mkdir(parents=True)
            (cache / 'a.txt').write_text('cache edit')
            findings, backup = update_preflight.audit(base / 'home', source, base / 'backups')
            self.assertEqual({row['kind'] for row in findings}, {'marketplace', 'cache'})
            self.assertTrue((backup / 'manifest.json').is_file())


class VersionCheck(unittest.TestCase):
    def test_codex_cache_selects_highest_semver(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for version in ('0.9.9', '0.11.4', '0.10.12'):
                (home / '.codex/plugins/cache/philip-relay/philip' / version).mkdir(parents=True)
            self.assertEqual(version_check.installed(home)['코덱스 설치본(기본)'], '0.11.4')


if __name__ == '__main__':
    unittest.main(verbosity=2)
