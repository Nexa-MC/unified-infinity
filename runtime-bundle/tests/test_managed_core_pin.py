"""Exercise actual Gradle configuration rejection without compiling/executing JAR code."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class ManagedCorePinTest(unittest.TestCase):
    def check_rejected(self, manifest, pin, expected):
        with tempfile.TemporaryDirectory(prefix='infinity-pin-') as directory:
            jar = Path(directory) / 'candidate.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.writestr('META-INF/MANIFEST.MF', manifest)
            digest = hashlib.sha256(jar.read_bytes()).hexdigest()
            args = [str(ROOT / 'tools/java-env.sh'), 'gradle', '-p', str(ROOT / 'runtime-bundle'),
                    '--offline', '--no-daemon', '--console=plain', 'help',
                    '-PmanagedCoreJar=' + str(jar)]
            if pin is not None:
                args.append('-PmanagedCoreSha256=' + (digest if pin == 'actual' else pin))
            result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=90)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected, result.stdout)

    def test_missing_pin(self):
        self.check_rejected('Manifest-Version: 1.0\nImplementation-Version: test\n\n',
                            None, 'requires an explicit SHA-256 pin')

    def test_wrong_pin(self):
        self.check_rejected('Manifest-Version: 1.0\nImplementation-Version: test\n\n',
                            '0' * 64, 'does not match its SHA-256 pin')

    def test_missing_version(self):
        self.check_rejected('Manifest-Version: 1.0\n\n', 'actual',
                            'no safe exact Implementation-Version')

    def test_unsafe_version(self):
        self.check_rejected('Manifest-Version: 1.0\nImplementation-Version: bad"version\n\n',
                            'actual', 'no safe exact Implementation-Version')


if __name__ == '__main__':
    unittest.main()
