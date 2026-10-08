"""Owned-profile mode checks with exact hashes; no JVM or external processes."""
from contextlib import ExitStack
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervisor as s
import test_supervisor


class OwnedConfigModes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / 'server'
        self.path = self.profile / 'config/neoforge-server.toml'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'advertiseDedicatedServerToLan=false\n')
        self.path.chmod(0o644)
        self.pin = {'path': str(self.path), 'bytes': self.path.stat().st_size, 'sha256': s.digest(self.path)}

    def test_owner_write_normal_modes_accepted_without_chmod(self):
        for mode in (0o600, 0o640, 0o644, 0o444, 0o755):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(mode)
                self.assertEqual(s.file_pin(self.pin, self.profile), self.path)
                self.assertEqual(self.path.stat().st_mode & 0o777, mode)

    def test_hash_and_size_unchanged_under_owned_mode_exception(self):
        for pin in (dict(self.pin, sha256='0' * 64), dict(self.pin, bytes=self.pin['bytes'] + 1)):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                s.file_pin(pin, self.profile)

    def test_outside_root_and_lexical_prefix_do_not_qualify(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            s.file_pin(self.pin, self.root / 'server-other')
        self.assertIsNone(s.preparation_root([self.profile], str(self.root / 'server-other/config/a')))
        self.assertEqual(s.preparation_root([self.profile], str(self.path)), self.profile)

    def test_group_world_write_execute_special_modes_and_hardlinks_rejected(self):
        for mode in (0o664, 0o666, 0o775, 0o4644, 0o2644):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(mode)
                with self.assertRaisesRegex(ValueError, 'runner-owned'):
                    s.file_pin(self.pin, self.profile)
        self.path.chmod(0o644)
        os.link(self.path, self.root / 'external-hardlink')
        with self.assertRaisesRegex(ValueError, 'singly linked'):
            s.file_pin(self.pin, self.profile)

    def test_nonowned_file_or_profile_rejected(self):
        original = Path.stat
        for target in (self.path, self.profile, self.path.parent):
            def different_owner(path, *args, **kwargs):
                result = original(path, *args, **kwargs)
                if path == target:
                    fields = list(result)
                    fields[4] = os.geteuid() + 1
                    return os.stat_result(fields)
                return result
            with self.subTest(target=target), patch.object(Path, 'stat', different_owner), self.assertRaises(ValueError):
                s.file_pin(self.pin, self.profile)

    def test_untrusted_profile_directory_mode_rejected(self):
        for directory in (self.profile, self.path.parent):
            directory.chmod(0o777)
            with self.subTest(directory=directory), self.assertRaisesRegex(ValueError, 'Preparation directories'):
                s.file_pin(self.pin, self.profile)
            directory.chmod(0o755)

    def test_root_or_mismatched_uid_rejected(self):
        for effective, real in ((0, 0), (1000, 1001)):
            with patch('supervisor.os.geteuid', return_value=effective), patch('supervisor.os.getuid', return_value=real):
                with self.assertRaisesRegex(ValueError, 'nonroot'):
                    s.file_pin(self.pin, self.profile)

    def test_code_and_receipts_do_not_inherit_profile_mode_exception(self):
        with self.assertRaisesRegex(ValueError, 'read-only'):
            s.file_pin(self.pin)


class WholeSpecWritableConfigs(unittest.TestCase):
    def setUp(self):
        self.fixture = test_supervisor.SealTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.spec = self.fixture.make_synthetic_spec()
        self.spec.update(schema='network-ci-pair-v2', preparation_roots=[str(self.root)], jdk_legal_links=[])
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        sha = hashlib.sha256(b'synthetic-only').hexdigest()
        self.stack.enter_context(patch.object(s, 'ORIGINAL_MODS', {'a.jar': sha, 'b.jar': sha}))
        self.stack.enter_context(patch.object(s, 'EMI_MODS', {'native-neoforge': ('c.jar', sha)}))
        self.stack.enter_context(patch('supervisor.subprocess.Popen', side_effect=AssertionError('No JVM/process')))
        self.stack.enter_context(patch('supervisor.os.killpg', side_effect=AssertionError('No signals')))
        for row in self.spec['inputs']:
            Path(row['path']).chmod(0o644)

    def test_full_prestart_and_poststart_allow_natural_config_modes(self):
        before = s.capture_server_properties(self.spec)
        properties = self.root / 'server/server.properties'
        properties.write_bytes(b'#host serialization\n' + before)
        for name in ('before-client.json', 'after-stop.json'):
            s.verify_spec(self.spec, before, self.root / name)
            self.assertEqual(json.loads((self.root / name).read_text())['status'], 'SEMANTICS_PRESERVED')
        self.assertEqual(properties.stat().st_mode & 0o777, 0o644)

    def test_writable_config_content_change_still_rejected(self):
        before = s.capture_server_properties(self.spec)
        config = self.root / 'server/config/neoforge-server.toml'
        config.write_bytes(b'advertiseDedicatedServerToLan=true\n')
        with self.assertRaises(ValueError):
            s.verify_spec(self.spec, before)

    def test_writable_mod_still_requires_exact_content_pin(self):
        mod = self.root / 'server/mods/a.jar'
        mod.chmod(0o644)
        s.capture_server_properties(self.spec)
        mod.write_bytes(b'changed-code')
        with self.assertRaises(ValueError):
            s.capture_server_properties(self.spec)

    def test_owned_writable_pair_seal_still_requires_independent_hash(self):
        seal = self.root / 'pair-spec.json'
        seal.write_text(json.dumps(self.spec))
        sha = s.digest(seal)
        s.verify_pair_seal(seal, sha, self.spec)
        seal.write_text(json.dumps(self.spec) + '\n')
        with self.assertRaisesRegex(ValueError, 'digest changed'):
            s.verify_pair_seal(seal, sha, self.spec)
        with self.assertRaisesRegex(ValueError, 'outside explicit'):
            s.verify_pair_seal(seal, s.digest(seal), dict(self.spec, preparation_roots=[str(self.root / 'server')]))

    def test_legacy_pair_seal_still_requires_readonly_mode(self):
        seal = self.root / 'pair-spec.json'
        seal.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Read-only pair spec'):
            s.verify_pair_seal(seal, s.digest(seal), {'schema': 'network-ci-pair-v1'})


class FrozenPortable2(unittest.TestCase):
    def test_all_prior_source_bytes_preserved(self):
        prior = Path(__file__).resolve().parent.parent / 'network-ci-supervisor-portable2'
        self.assertEqual(s.digest(prior / 'source-manifest.json'),
                         '22c92c8f4e1c0ee00cc251998e34b0fff9e0c150cebca773cc8d60bc7edb9aac')
        for row in json.loads((prior / 'source-manifest.json').read_text())['files']:
            self.assertEqual((prior / row['path']).stat().st_size, row['bytes'])
            self.assertEqual(s.digest(prior / row['path']), row['sha256'])

    def test_file_pin_and_properties_only_add_owned_mode_admission(self):
        here = Path(__file__).resolve().parent
        old = ast.parse((here.parent / 'network-ci-supervisor-portable2/supervisor.py').read_text())
        new = ast.parse((here / 'supervisor.py').read_text())
        for name in ('file_pin', 'verify_server_properties'):
            expected = next(node for node in old.body if isinstance(node, ast.FunctionDef) and node.name == name)
            actual = copy.deepcopy(next(node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == name))
            actual.args = copy.deepcopy(expected.args)
            if name == 'file_pin':
                index = next(i for i, node in enumerate(actual.body) if isinstance(node, ast.If))
                branch = actual.body[index]
                self.assertEqual(ast.unparse(branch.test), 'owned_profile is not None')
                self.assertEqual(ast.unparse(branch.body[0]), 'owned_preparation_access(path, info, owned_profile)')
                actual.body[index] = branch.orelse[0]
            else:
                call = next(node for node in ast.walk(actual) if isinstance(node, ast.Call) and
                            isinstance(node.func, ast.Name) and node.func.id == 'file_pin')
                self.assertEqual(ast.unparse(call.args.pop()), 'owned_profile')
            self.assertEqual(ast.dump(actual, include_attributes=False), ast.dump(expected, include_attributes=False))

    def test_cli_only_changes_pair_seal_file_admission(self):
        here = Path(__file__).resolve().parent
        old = ast.parse((here.parent / 'network-ci-supervisor-portable2/supervisor.py').read_text())
        new = ast.parse((here / 'supervisor.py').read_text())
        expected = next(node for node in old.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        actual = copy.deepcopy(next(node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == 'main'))
        matches = 0
        for index, node in enumerate(actual.body):
            if ast.unparse(node) == "require(digest(path) == args.sha256, 'Pair spec digest mismatch')":
                actual.body[index] = ast.parse("require(path.stat().st_mode & 0o222 == 0 and digest(path) == args.sha256, 'Read-only pair spec seal mismatch')").body[0]
                matches += 1
        actual.body = [node for node in actual.body if ast.unparse(node) != 'verify_pair_seal(path, args.sha256, spec)']
        self.assertEqual(matches, 1)
        self.assertEqual(ast.dump(actual, include_attributes=False), ast.dump(expected, include_attributes=False))


if __name__ == '__main__':
    unittest.main()
