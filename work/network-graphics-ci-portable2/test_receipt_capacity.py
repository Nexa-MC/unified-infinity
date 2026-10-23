"""Synthetic graphics capacity tests; no native process or runtime claims."""
import json
from pathlib import Path
import test_graphics_preflight as baseline
g, S = baseline.g, baseline.S

class ReceiptCapacity(baseline.LockTests):
    def test_graphics_receipt_exact_boundary_and_one_byte_over(self):
        limit = S.GRAPHICS_RECEIPT_MAX_BYTES
        self.assertEqual(limit, 32768)
        # Complete 128-entry synthetic closure, not real runtime evidence.
        pins = {'/usr/lib/x86_64-linux-gnu/libSynthetic%03d.so' % i: '%064x' % i
                for i in range(128)}
        value = {'input_sha256': pins, 'padding': ''}
        size = len(json.dumps(value, separators=(',', ':')).encode('ascii')) + 1
        self.assertGreater(size, 8192)
        value['padding'] = 'x' * (limit - size)
        path = g.write_receipt(Path(self.directory.name), 'boundary.json', value, S, limit)
        self.assertEqual(Path(path).stat().st_size, limit)
        result = S.decode_json(S.read_bounded(path, limit), limit)
        self.assertEqual(result['input_sha256'], pins)
        value['padding'] += 'x'
        with self.assertRaisesRegex(ValueError, 'frozen consumer bound'):
            g.write_receipt(Path(self.directory.name), 'over.json', value, S, limit)
        self.assertFalse((Path(self.directory.name) / 'over.json').exists())
        with self.assertRaisesRegex(ValueError, 'JSON byte bound'):
            S.decode_json(Path(path).read_bytes() + b' ', limit)
        oversized = Path(self.directory.name) / 'over-read.json'
        oversized.write_bytes(Path(path).read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'File byte bound'):
            S.read_bounded(oversized, limit)


# Pin the predecessor function AST independently of optional historical fixtures.
# Only the exact reviewed capacity expression is normalized. Every other gate,
# measurement, schema field, liveness check and cleanup statement remains pinned.
import ast
import hashlib
import unittest

_MIGRATED = 'receipt, s, s.GRAPHICS_RECEIPT_MAX_BYTES)'
_ORIGINAL = 'receipt, s, 8192)'
_EXPECTED_PREDECESSOR_AST_SHA256 = '033409131fee8ff7ea36756e74b60638e51ef7835836cc4b7f71389128a8f618'

def _normalized_function_digest(source):
    if source.count(_MIGRATED) != 1:
        raise ValueError('Expected exactly one reviewed graphics capacity expression')
    from test_cleanup_lifecycle import normalize_cleanup_reporting
    tree = ast.parse(normalize_cleanup_reporting(source).replace(_MIGRATED, _ORIGINAL))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

class PreservationMigration(unittest.TestCase):
    def source(self):
        return (Path(__file__).parent / 'graphics_preflight.py').read_text()

    def test_only_reviewed_capacity_expression_changes_predecessor_function(self):
        self.assertEqual(_normalized_function_digest(self.source()), _EXPECTED_PREDECESSOR_AST_SHA256)

    def test_missing_or_duplicate_capacity_expression_rejected(self):
        for source in (self.source().replace(_MIGRATED, _ORIGINAL),
                       self.source() + '\n# ' + _MIGRATED):
            with self.subTest(source=source[-80:]), self.assertRaisesRegex(ValueError, 'exactly one'):
                _normalized_function_digest(source)

    def test_unreviewed_gate_change_is_not_normalized(self):
        source = self.source()
        needle = 'require(observed <= set(pins),'
        replacement = 'require(True,'
        self.assertEqual(source.count(needle), 1)
        changed = source.replace(needle, replacement)
        self.assertNotEqual(_normalized_function_digest(changed), _EXPECTED_PREDECESSOR_AST_SHA256)
