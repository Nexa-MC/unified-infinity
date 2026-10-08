"""Bounded synthetic property-lifecycle tests; never execute a process or game."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervisor as s
import test_supervisor


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def setUpModule():
    global _launch, _signal
    _launch = patch('supervisor.subprocess.Popen', side_effect=AssertionError('No subprocess in source-only tests'))
    _signal = patch('supervisor.os.killpg', side_effect=AssertionError('No process signals in source-only tests'))
    _launch.start()
    _signal.start()


def tearDownModule():
    _signal.stop()
    _launch.stop()


class PropertySyntax(unittest.TestCase):
    def test_host_colon_escape_and_unicode_are_same_value(self):
        expected = {'level-type': 'minecraft:flat', 'server-ip': '127.0.0.1'}
        self.assertEqual(s.parse_properties(b'level-type=minecraft:flat\nserver-ip=127.0.0.1\n'), expected)
        self.assertEqual(s.parse_properties(b'level-type=minecraft\\:flat\nserver\\u002dip=127.0.0.1\n'), expected)
        self.assertEqual(s.parse_properties(b'level-type=minecraft\\u003aflat\nserver-ip=127.0.0.1\n'), expected)

    def test_comments_order_spacing_and_line_endings(self):
        actual = b' #Minecraft server properties\r\n\t!timestamp\r\n\n level-type : minecraft\\:flat\rserver-ip \t= 127.0.0.1\n'
        self.assertEqual(s.parse_properties(actual), {'level-type': 'minecraft:flat', 'server-ip': '127.0.0.1'})

    def test_backslash_does_not_disappear_twice(self):
        self.assertEqual(s.parse_properties(b'level-type=minecraft\\\\:flat\n')['level-type'], 'minecraft\\:flat')
        self.assertNotEqual(s.parse_properties(b'level-type=minecraft\\\\:flat\n'),
                            s.parse_properties(b'level-type=minecraft\\:flat\n'))

    def test_value_whitespace_and_standard_escapes_preserve_java_semantics(self):
        self.assertEqual(s.parse_properties(b'motd= \\ hello\\tthere\\nnext\\r\\f\\!\\=\\# \\ \n'),
                         {'motd': ' hello\tthere\nnext\r\f!=#  '})
        self.assertNotEqual(s.parse_properties(b'motd=hello \n'), s.parse_properties(b'motd=hello\n'))

    def test_duplicate_decoded_keys_rejected(self):
        for raw in (b'server-ip=127.0.0.1\nserver-ip=0.0.0.0\n',
                    b'server-ip=127.0.0.1\nserver\\u002dip=127.0.0.1\n',
                    b'white-list=true\n white-list : true\n'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'Duplicate'):
                s.parse_properties(raw)

    def test_continuations_and_trailing_escape_rejected(self):
        for raw in (b'motd=hello\\\n world\n', b'motd=hello\\\r\nworld\n', b'motd=hello\\',
                    b'server-\\\nip=127.0.0.1\n'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'continuation'):
                s.parse_properties(raw)

    def test_comment_trailing_slash_is_not_continuation(self):
        self.assertEqual(s.parse_properties(b'# comment \\\nserver-ip=127.0.0.1\n'), {'server-ip': '127.0.0.1'})

    def test_malformed_unicode_control_nonascii_key_and_bound_rejected(self):
        for raw in (b'motd=\\u123\n', b'motd=\\uQQQQ\n', b'motd=\x00\n', b'motd=\x7f\n', b'motd=\xff\n',
                    b'server\\ ip=127.0.0.1\n', b'=empty-key\n', b'no-delimiter\n', b'#' * 16385):
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                s.parse_properties(raw)


class PropertyLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'server.properties'
        self.before = b'server-ip=127.0.0.1\nlevel-type=minecraft:flat\nonline-mode=false\n'
        self.path.write_bytes(self.before)
        self.path.chmod(0o444)
        self.pin = {'path': str(self.path), 'bytes': len(self.before), 'sha256': s.digest(self.path)}
        self.receipt = self.root / 'receipt.json'

    def change(self, data):
        self.path.chmod(0o644)
        self.path.write_bytes(data)
        self.path.chmod(0o444)

    def verify(self):
        return s.verify_server_properties(self.pin, self.before, self.receipt)

    def test_serialization_receipt_exact_bytes_hash_and_diff(self):
        after = b'#Minecraft server properties\r\n#new timestamp\r\nonline-mode=false\r\nlevel-type=minecraft\\:flat\r\nserver-ip=127.0.0.1\r\n'
        self.change(after)
        self.assertEqual(self.verify(), self.path)
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['status'], 'SEMANTICS_PRESERVED')
        self.assertFalse(receipt['byte_identical'])
        self.assertEqual(bytes.fromhex(receipt['before']['hex']), self.before)
        self.assertEqual(bytes.fromhex(receipt['after']['hex']), after)
        self.assertEqual(receipt['after']['sha256'], hashlib.sha256(after).hexdigest())
        self.assertEqual(receipt['before']['sha256'], self.pin['sha256'])
        self.assertTrue(any(line.startswith('+level-type=minecraft\\:flat') for line in receipt['diff']))
        self.assertEqual(receipt['added_keys'] + receipt['removed_keys'] + receipt['changed_keys'], [])

    def test_byte_identical_pass_records_empty_diff(self):
        self.verify()
        receipt = json.loads(self.receipt.read_text())
        self.assertTrue(receipt['byte_identical'])
        self.assertEqual(receipt['diff'], [])

    def test_changed_safety_and_non_safety_values_and_removed_key_rejected(self):
        for old, new in ((b'127.0.0.1', b'0.0.0.0'), (b'online-mode=false', b'online-mode=true'),
                         (b'minecraft:flat', b'minecraft:normal'), (b'level-type=minecraft:flat\n', b'')):
            with self.subTest(old=old):
                self.change(self.before.replace(old, new))
                with self.assertRaisesRegex(ValueError, 'semantic key/value'):
                    s.verify_server_properties(self.pin, self.before, None)

    def test_unknown_and_known_default_additions_rejected_with_receipt(self):
        self.change(self.before + b'unknown-key=true\n')
        with self.assertRaisesRegex(ValueError, 'semantic key/value'):
            self.verify()
        self.assertEqual(json.loads(self.receipt.read_text())['added_keys'], ['unknown-key'])
        self.change(self.before + b'allow-flight=false\n')
        with self.assertRaisesRegex(ValueError, 'semantic key/value'):
            s.verify_server_properties(self.pin, self.before, None)

    def test_original_byte_pin_cannot_be_replaced_by_semantic_equivalence(self):
        equivalent = b'# equivalent\n' + self.before
        with self.assertRaisesRegex(ValueError, 'Original server property byte pin'):
            s.verify_server_properties(self.pin, equivalent, self.receipt)

    def test_post_start_duplicate_fails_and_receipt_preserves_evidence(self):
        self.change(self.before + b'online-mode=false\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.verify()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['status'], 'REJECTED')
        self.assertIn('Duplicate', receipt['failure'])
        self.assertEqual(bytes.fromhex(receipt['after']['hex']), self.path.read_bytes())

    def test_property_permission_rules_and_no_symlink_remain(self):
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):
            s.verify_server_properties(self.pin, self.before, None)
        self.path.chmod(0o444)
        link = self.root / 'link'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'Noncanonical|Symlink'):
            s.verify_server_properties(dict(self.pin, path=str(link)), self.before, None)


class CompleteSealLifecycle(unittest.TestCase):
    def setUp(self):
        self.fixture = test_supervisor.SealTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.spec = self.fixture.make_synthetic_spec()
        sha = hashlib.sha256(b'synthetic-only').hexdigest()
        for name, value in (('ORIGINAL_MODS', {'a.jar': sha, 'b.jar': sha}),
                            ('EMI_MODS', {'native-neoforge': ('c.jar', sha)})):
            patcher = patch.object(s, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.path = self.root / 'server/server.properties'

    def rewrite(self, path, data):
        path.chmod(0o644)
        path.write_bytes(data)
        path.chmod(0o444)

    def test_prestart_exact_pin_and_two_poststart_receipts(self):
        before = s.capture_server_properties(self.spec)
        self.rewrite(self.path, b'#host timestamp\n' + before)
        with self.assertRaisesRegex(ValueError, 'size/type changed'):
            s.verify_spec(self.spec)
        for name in ('before-client.json', 'after-stop.json'):
            s.verify_spec(self.spec, before, self.root / name)
            self.assertEqual(json.loads((self.root / name).read_text())['status'], 'SEMANTICS_PRESERVED')
        with self.assertRaisesRegex(ValueError, 'size/type changed'):
            s.capture_server_properties(self.spec)

    def test_mod_config_and_json_control_pins_not_exempt(self):
        before = s.capture_server_properties(self.spec)
        paths = ('server/mods/a.jar', 'server/config/neoforge-server.toml',
                 'server/defaultconfigs/neoforge-server.toml', 'server/whitelist.json',
                 'server/ops.json', 'server/eula.txt')
        for relative in paths:
            path = self.root / relative
            original = path.read_bytes()
            with self.subTest(relative=relative):
                self.rewrite(path, original + b'\n')
                with self.assertRaisesRegex(ValueError, 'size/type changed'):
                    s.verify_spec(self.spec, before)
                self.rewrite(path, original)

    def test_all_preexisting_safety_keys_still_enforced_before_capture(self):
        original = self.path.read_bytes()
        row = next(row for row in self.spec['inputs'] if row['path'] == str(self.path))
        for key in s.parse_properties(original):
            with self.subTest(key=key):
                values = s.parse_properties(original)
                values[key] = 'unsafe'
                data = ''.join(k + '=' + v + '\n' for k, v in values.items()).encode()
                self.rewrite(self.path, data)
                row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                with self.assertRaisesRegex(ValueError, 'Unsafe server properties'):
                    s.capture_server_properties(self.spec)


class SourcePreservation(unittest.TestCase):
    def test_portable1_inventory_unchanged(self):
        frozen = HERE.parent / 'network-ci-supervisor-portable1'
        self.assertEqual(s.digest(frozen / 'source-manifest.json'),
                         '146e28f0d0b5276dbfee7e3f1145dd73b390fe2ab8fcd9f024a7143ebd27b2dc')
        for row in json.loads((frozen / 'source-manifest.json').read_text())['files']:
            self.assertEqual((frozen / row['path']).stat().st_size, row['bytes'])
            self.assertEqual(s.digest(frozen / row['path']), row['sha256'])

    def test_entire_process_class_only_changes_five_verification_invocations(self):
        upstream = ast.parse((HERE.parent / 'network-ci-supervisor-portable1/supervisor.py').read_text())
        current = ast.parse((HERE / 'supervisor.py').read_text())
        expected = next(node for node in upstream.body if isinstance(node, ast.ClassDef) and node.name == 'Pair')
        actual = copy.deepcopy(next(node for node in current.body if isinstance(node, ast.ClassDef) and node.name == 'Pair'))
        run = next(node for node in actual.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
        body = next(node for node in run.body if isinstance(node, ast.Try)).body
        expected_run = next(node for node in expected.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
        expected_body = next(node for node in expected_run.body if isinstance(node, ast.Try)).body
        observed = []
        seals = 0
        for index, node in enumerate(body):
            call = node.value if isinstance(node, (ast.Expr, ast.Assign)) else None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'verify_pair_seal':
                self.assertEqual(ast.unparse(node), 'verify_pair_seal(seal_path, seal_sha, self.spec)')
                self.assertIn('Pair spec changed', ast.unparse(expected_body[index]))
                body[index] = copy.deepcopy(expected_body[index])
                seals += 1
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in ('capture_server_properties', 'verify_spec'):
                observed.append(ast.unparse(node))
                body[index] = ast.parse('verify_spec(self.spec)').body[0]
        self.assertEqual(observed, [
            'server_properties_before = capture_server_properties(self.spec)',
            "verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-before-client.json')",
            "verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-after-stop.json')"])
        self.assertEqual(seals, 2)
        self.assertEqual(ast.dump(actual, include_attributes=False), ast.dump(expected, include_attributes=False))
        changed = {'property_values', 'verify_spec', 'Pair', 'file_pin', 'main'}
        old = {n.name: ast.dump(n, include_attributes=False) for n in upstream.body
               if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name not in changed}
        new = {n.name: ast.dump(n, include_attributes=False) for n in current.body
               if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in old}
        self.assertEqual(new, old)

    def test_spec_core_preserved_except_v2_admission_and_property_dispatch(self):
        upstream = ast.parse((HERE.parent / 'network-ci-supervisor-portable1/supervisor.py').read_text())
        current = ast.parse((HERE / 'supervisor.py').read_text())
        expected = next(node for node in upstream.body if isinstance(node, ast.FunctionDef) and node.name == 'verify_spec')
        actual = copy.deepcopy(next(node for node in current.body if isinstance(node, ast.FunctionDef) and node.name == 'verify_spec'))
        self.assertEqual([arg.arg for arg in actual.args.args], ['spec', 'server_properties_before', 'property_receipt'])
        actual.args = copy.deepcopy(expected.args)
        self.assertIsInstance(actual.body[0], ast.Assign)
        self.assertEqual(ast.unparse(actual.body[0].targets[0]), 'keys')
        self.assertIsInstance(actual.body[1], ast.If)
        actual.body[:2] = copy.deepcopy(expected.body[:2])
        loop = next(node for node in actual.body if isinstance(node, ast.For) and ast.unparse(node.iter) == "spec['inputs']")
        self.assertEqual(ast.unparse(loop.body[0]), "config_root = preparation_root(roots, row['path'])")
        self.assertIsInstance(loop.body[1], ast.If)
        self.assertEqual(ast.unparse(loop.body[2]),
                         "if server_properties_before is not None and row.get('path') == str(Path(spec['server']['cwd']) / 'server.properties'):\n"
                         "    path = verify_server_properties(row, server_properties_before, property_receipt, config_root)\n"
                         "else:\n    path = file_pin(row, config_root)")
        loop.body[:3] = [ast.parse('path = file_pin(row)').body[0]]
        actual.body = [node for node in actual.body if not (
            isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) in ('legal_links', 'observed_links')) and not (
            isinstance(node, ast.Expr) and ast.unparse(node).startswith('require(observed_links == legal_links,'))]
        tree_loop = next(node for node in actual.body if isinstance(node, ast.For) and ast.unparse(node.iter) == "spec['immutable_trees']")
        entry_loop = next(node for node in tree_loop.body if isinstance(node, ast.For))
        self.assertEqual(ast.unparse(entry_loop.body[0].test), 'path.is_symlink()')
        entry_loop.body[0] = ast.parse("require(not path.is_symlink(), 'Redirected immutable entry')").body[0]
        self.assertEqual(ast.dump(actual, include_attributes=False), ast.dump(expected, include_attributes=False))

    def test_existing_accepted_host_escape_matches_preparation_semantics(self):
        accepted = s.property_values(ROOT / 'work/api1/run/api1-unified-server-4/server.properties')
        self.assertEqual(accepted['level-type'], 'minecraft:normal')
        self.assertEqual(accepted['initial-enabled-packs'], 'vanilla,fabric')
        for target, packs in (('native-neoforge', 'vanilla'), ('unified', 'vanilla,fabric')):
            actual = s.property_values(ROOT / 'work/network-pair-assembled-local4' / target / 'server/server.properties')
            self.assertEqual(set(actual), set(accepted))
            self.assertEqual(actual['initial-enabled-packs'], packs)
            self.assertEqual(actual['level-type'], 'minecraft:flat')


if __name__ == '__main__':
    unittest.main()
