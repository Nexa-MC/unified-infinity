import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("verify_bundle", Path(__file__).parents[1] / "tools/verify_bundle.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ArchiveVerifierTest(unittest.TestCase):
    def test_valid_nested_path(self):
        self.assertTrue(verifier.safe_archive_path("META-INF/jars/fabric-api.jar"))

    def test_reject_unsafe_paths(self):
        for path in ("", "/absolute.jar", "../escape.jar", "META-INF/../escape.jar", "a\\b", "a//b"):
            with self.subTest(path=path):
                self.assertFalse(verifier.safe_archive_path(path))

    def test_reads_mod_identity_without_loading_code(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as jar:
            jar.writestr(verifier.MOD_METADATA, '[[mods]]\nmodId="example"\n')
        result = verifier.inventory(out.getvalue(), "test.jar")
        self.assertEqual(result[0]["mod_ids"], ["example"])

    def test_reject_missing_declared_nested_archive(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as jar:
            jar.writestr(verifier.JARJAR_METADATA,
                         '{"jars":[{"identifier":{"group":"a","artifact":"b"},"path":"missing.jar"}]}')
        with self.assertRaises(KeyError):
            verifier.inventory(out.getvalue(), "test.jar")

    def test_reject_duplicate_entries(self):
        import warnings
        out = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(out, "w") as jar:
                jar.writestr("duplicate", "a")
                jar.writestr("duplicate", "b")
        with self.assertRaisesRegex(ValueError, "Duplicate ZIP"):
            verifier.inventory(out.getvalue(), "test.jar")


if __name__ == "__main__":
    unittest.main()
