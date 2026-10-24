"""Exact predecessor byte proof, independent of the complementary AST check."""
import hashlib
from pathlib import Path
import unittest

from diagnostic_profile_preservation import (
    PREDECESSOR_SHA256, REPLACEMENTS, without_diagnostic_profile)


class DiagnosticProfilePreservation(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).with_name('supervisor.py').read_text()

    def test_exact_previous_source_hash(self):
        previous = without_diagnostic_profile(self.source)
        self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(), PREDECESSOR_SHA256)
        self.assertEqual(PREDECESSOR_SHA256,
                         '1b489c7cd6db677cb067cc6f3d564c2e813baacaada2b4d583d911953aee7183')

    def test_each_metadata_block_rejects_missing_duplicate_and_changed_bytes(self):
        self.assertEqual(len(REPLACEMENTS), 6)
        for index, (reviewed, original) in enumerate(REPLACEMENTS):
            for kind, changed in (
                    ('missing', self.source.replace(reviewed, original, 1)),
                    ('duplicate', self.source + reviewed),
                    ('changed', self.source.replace(reviewed, '!' + reviewed[1:], 1))):
                with self.subTest(block=index, mutation=kind), self.assertRaises(ValueError):
                    without_diagnostic_profile(changed)

    def test_metadata_validation_mutations_are_not_hidden(self):
        for old, new in (
                ("profile['diagnostic_only'] is True", "profile['diagnostic_only'] == True"),
                ("profile['baseline_acceptance'] is False", "profile['baseline_acceptance'] == False"),
                ('16 * 1024', '64 * 1024'),
                ('len(receipts) == 2', 'len(receipts) <= 2'),
                ('pins.get(path) == receipt', 'pins.get(path) is not None')):
            self.assertIn(old, self.source)
            with self.subTest(mutation=old), self.assertRaises(ValueError):
                without_diagnostic_profile(self.source.replace(old, new, 1))

    def test_unrelated_guards_and_extra_text_remain_visible(self):
        previous = without_diagnostic_profile(self.source)
        for old, new in (
                ('CPU_PROBE_VERIFY_SECONDS = 1', 'CPU_PROBE_VERIFY_SECONDS = 2'),
                ('CPU probe socket descriptor forbidden', 'UNREVIEWED_CHANGE'),
                ('CPU probe executable digest mismatch', 'UNREVIEWED_CHANGE')):
            self.assertIn(old, self.source)
            normalized = without_diagnostic_profile(self.source.replace(old, new, 1))
            self.assertEqual(normalized, previous.replace(old, new, 1))
            self.assertNotEqual(hashlib.sha256(normalized.encode()).hexdigest(), PREDECESSOR_SHA256)
        extra = '\n# Unreviewed extra content\n'
        self.assertEqual(without_diagnostic_profile(self.source + extra), previous + extra)
        self.assertNotEqual(hashlib.sha256((previous + extra).encode()).hexdigest(), PREDECESSOR_SHA256)

    def test_reversal_is_not_a_permissive_or_idempotent_parser(self):
        previous = without_diagnostic_profile(self.source)
        for source in ('', previous, self.source + self.source):
            with self.assertRaises(ValueError):
                without_diagnostic_profile(source)


if __name__ == '__main__':
    unittest.main()
