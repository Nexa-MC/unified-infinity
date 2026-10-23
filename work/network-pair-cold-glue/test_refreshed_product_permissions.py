"""Source/recipe-only regression checks; no Java, Gradle or game execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import build_candidate as b

class RefreshedProductPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recipe = b.plan(self.root)
        self.prefix = self.recipe['productCommandPrefix']
        self.historical = str(self.root / b.fml_metadata.SUPPORT / 'product-payload-permissions.init.gradle')
        self.standard = str(self.root / b.fml_metadata.SUPPORT / 'archive-permissions.init.gradle')

    def test_exact_pair_removed_rest_and_historical_unchanged(self):
        original = copy.deepcopy(self.recipe)
        expected = self.prefix.copy()
        i = expected.index(self.historical)
        del expected[i-1:i+1]
        self.assertEqual(b.refreshed_product_prefix(self.root, self.recipe), expected)
        self.assertEqual(self.recipe, original)
        self.assertEqual(b.plan(self.root), original)
        self.assertIn(self.standard, expected)
        self.assertNotIn(self.historical, expected)

    def test_missing_duplicate_or_malformed_override_fails(self):
        for variant in ('missing', 'duplicate', 'malformed'):
            with self.subTest(variant=variant):
                recipe = copy.deepcopy(self.recipe)
                p = recipe['productCommandPrefix']
                i = p.index(self.historical)
                if variant == 'missing': del p[i-1:i+1]
                elif variant == 'duplicate': p.extend(['--init-script', self.historical])
                else: p[i-1] = '--other'
                with self.assertRaises(Exception): b.refreshed_product_prefix(self.root, recipe)

    def test_missing_duplicate_or_malformed_standard_fails(self):
        for variant in ('missing', 'duplicate', 'malformed'):
            with self.subTest(variant=variant):
                recipe = copy.deepcopy(self.recipe)
                p = recipe['productCommandPrefix']
                i = p.index(self.standard)
                if variant == 'missing': del p[i-1:i+1]
                elif variant == 'duplicate': p.extend(['--init-script', self.standard])
                else: p[i-1] = '--other'
                with self.assertRaises(Exception): b.refreshed_product_prefix(self.root, recipe)

    def test_refreshed_command_uses_exact_prefix(self):
        profile = {'artifactPaths': {'service': 'service.jar'}, 'observedOutputReference': {'service': 'a'*64}}
        command = b.refreshed_commands(self.root, profile)['product']
        prefix = b.refreshed_product_prefix(self.root, self.recipe)
        self.assertEqual(command[:len(prefix)], prefix)
        self.assertNotIn(self.historical, command)
        self.assertIn(self.historical, self.prefix)

    def test_pinned_modes_and_both_execution_paths(self):
        # Dependencies/support bytes are still the original checked-in sources.
        source_dir = Path(b.fml_metadata.__file__).parent
        standard = (source_dir/'build-support/archive-permissions.init.gradle').read_text()
        historical = (source_dir/'build-support/product-payload-permissions.init.gradle').read_text()
        self.assertIn('fileMode = 0644', standard)
        self.assertIn('dirMode = 0755', standard)
        self.assertIn('details.mode = 0600', historical)
        self.assertNotIn('chmod', standard)
        self.assertNotIn('chmod', historical)
        source = Path(b.__file__).read_text()
        self.assertEqual(source.count('*refreshed_product_prefix(root, recipe)'), 2)
        self.assertIn("args = [*recipe['productCommandPrefix']", source)

if __name__ == '__main__': unittest.main()
