"""Bind the transition pin to the unchanged production full-JDK producer."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

import supervisor as s


class ProductionSourceBinding(unittest.TestCase):
    def test_original_jdk_closure_producer_is_unchanged_and_consumed_completely(self):
        work = Path(__file__).resolve().parent.parent
        producer = work / 'network-pair-finalizer/prepare_inputs.py'
        self.assertEqual(hashlib.sha256(producer.read_bytes()).hexdigest(),
                         '3fe5393ffc0dfe6a7bfe4a23ac9fe55dc133913a66e1908d7ff03e34ce44249e')
        source = (work / 'network-pair-cold-glue/seal_pair.py').read_text()
        normalized = ast.unparse(ast.parse(source))
        self.assertIn('jdk_files, links, jdk_result = helper.jdk_closure()', normalized)
        self.assertIn('trees.add(str(helper.JDK))', normalized)
        self.assertIn("for row in jdk_files:\n        inputs[row['path']] = row", normalized)
        self.assertIn("'immutable_trees': sorted(trees)", normalized)
        self.assertIn("'inputs': list(inputs.values())", normalized)

    def test_new_transition_only_adds_original_official_member_identity(self):
        self.assertEqual(s.JDK_SPAWN_BYTES, 17888)
        self.assertEqual(s.JDK_SPAWN_SHA256,
                         'e3101d3a580c9ae6e973acbf2e861855e93ebceb0bbd8e5fa3ddf6abbf6fd63d')
        self.assertEqual(s.JDK_SPAWN_VERSION, b'21.0.12.1+1-LTS')


if __name__ == '__main__':
    unittest.main()
