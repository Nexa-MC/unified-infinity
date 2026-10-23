"""Synthetic 128-pin graphics receipt and exact byte boundary checks."""
import json
from pathlib import Path
import test_supervisor as baseline
s = baseline.s

class ReceiptCapacity(baseline.SyntheticProc):
    def test_actual_fixture_xvfb_executable_and_socket_owner(self):
        executable = self.root / 'graphics/Xvfb'
        executable.parent.mkdir()
        executable.write_bytes(b'SYNTHETIC ONLY')
        identity = self.make_process(404, 4000, ['77'])
        (self.root / '404/exe').symlink_to(executable)
        (self.root / '404/cmdline').write_bytes(str(executable).encode() + b'\0:77\0-nolisten\0tcp\0')
        (self.root / 'net/unix').write_text('header\n0: 00000002 00000000 00010000 0001 01 77 /tmp/.X11-unix/X77\n')
        receipt = self.root / 'graphics/preflight.json'
        receipt.write_text(json.dumps({'schema': 1, 'display': ':77', 'xvfb_pid': 404, 'xvfb_start_ticks': 4000,
                          'renderer': 'llvmpipe (synthetic fixture)', 'direct_rendering': True, 'glx_capable': True,
                          'gl_probe_peak_rss_bytes': 1024, 'measured_headroom_bytes': 256*s.MIB,
                          'input_sha256': {str(executable): s.digest(executable)}}))
        spec = {'graphics': {'display': ':77', 'pid': 404, 'start_ticks': 4000, 'executable': str(executable),
                            'preflight': str(receipt), 'reserve_bytes': 256*s.MIB},
                'inputs': [{'path': str(path), 'sha256': s.digest(path)} for path in (executable, receipt)]}
        self.assertEqual(s.verify_graphics(spec, self.proc)['identity'], identity)
        # All 128 synthetic hashes survive a receipt larger than the old 8 KiB bound.
        value = json.loads(receipt.read_text())
        value['input_sha256'].update({
            '/usr/lib/x86_64-linux-gnu/libSynthetic%03d.so' % i: '%064x' % i
            for i in range(127)})
        spec['inputs'].extend({'path': p, 'sha256': h}
                              for p, h in value['input_sha256'].items()
                              if p != str(executable))
        raw = json.dumps(value, separators=(',', ':')).encode('ascii') + b'\n'
        self.assertGreater(len(raw), 8192)
        value['renderer'] += 'x' * (s.GRAPHICS_RECEIPT_MAX_BYTES - len(raw))
        raw = json.dumps(value, separators=(',', ':')).encode('ascii') + b'\n'
        self.assertEqual(len(raw), s.GRAPHICS_RECEIPT_MAX_BYTES)
        receipt.write_bytes(raw)
        self.assertEqual(s.verify_graphics(spec, self.proc)['identity'], identity)
        self.assertEqual(len(json.loads(receipt.read_text())['input_sha256']), 128)
        receipt.write_bytes(raw + b' ')
        with self.assertRaisesRegex(ValueError, 'File byte bound'):
            s.verify_graphics(spec, self.proc)
        receipt.write_bytes(raw)
        value['input_sha256'][str(executable)] = '0' * 64
        receipt.write_text(json.dumps(value, separators=(',', ':')) + '\n')
        with self.assertRaisesRegex(ValueError, 'Unsealed graphics'):
            s.verify_graphics(spec, self.proc)
        receipt.write_bytes(raw)
        (self.root / 'net/unix').write_text('header\n0: 00000002 00000000 00010000 0001 01 99 /tmp/.X11-unix/X77\n')
        with self.assertRaisesRegex(ValueError, 'not owned'):
            s.verify_graphics(spec, self.proc)


# Pin the predecessor function AST independently of optional historical fixtures.
# Only the exact reviewed capacity expression is normalized. Every other gate,
# measurement, schema field, liveness check and cleanup statement remains pinned.
import ast
import hashlib
import unittest

_MIGRATED = "decode_json(read_bounded(graphics['preflight'], GRAPHICS_RECEIPT_MAX_BYTES),\n                          GRAPHICS_RECEIPT_MAX_BYTES)"
_ORIGINAL = "decode_json(read_bounded(graphics['preflight'], 8192), 8192)"
_EXPECTED_PREDECESSOR_AST_SHA256 = '309f04feee1e87da9cfa9be4056a306569632c0933a7ce4583b2e00181b3fadd'

def _normalized_function_digest(source):
    if source.count(_MIGRATED) != 1:
        raise ValueError('Expected exactly one reviewed graphics capacity expression')
    tree = ast.parse(source.replace(_MIGRATED, _ORIGINAL))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_graphics')
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

class PreservationMigration(unittest.TestCase):
    def source(self):
        return (Path(__file__).parent / 'supervisor.py').read_text()

    def test_only_reviewed_capacity_expression_changes_predecessor_function(self):
        self.assertEqual(_normalized_function_digest(self.source()), _EXPECTED_PREDECESSOR_AST_SHA256)

    def test_missing_or_duplicate_capacity_expression_rejected(self):
        for source in (self.source().replace(_MIGRATED, _ORIGINAL),
                       self.source() + '\n# ' + _MIGRATED):
            with self.subTest(source=source[-80:]), self.assertRaisesRegex(ValueError, 'exactly one'):
                _normalized_function_digest(source)

    def test_unreviewed_gate_change_is_not_normalized(self):
        source = self.source()
        needle = "require(receipt['glx_capable'] is True and"
        replacement = 'require(True and'
        self.assertEqual(source.count(needle), 1)
        changed = source.replace(needle, replacement)
        self.assertNotEqual(_normalized_function_digest(changed), _EXPECTED_PREDECESSOR_AST_SHA256)
