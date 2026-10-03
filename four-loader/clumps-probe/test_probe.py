#!/usr/bin/env python3
"""Pure Java arithmetic and packaging tests only. Does not launch Minecraft."""
import hashlib
import json
import pathlib
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JAVA = ROOT / '.toolchains/jdk-21.0.12.1+1/bin'


class ProbeTests(unittest.TestCase):
    def test_pure_java_arithmetic_controls(self):
        with tempfile.TemporaryDirectory(prefix='clumps-arithmetic-') as directory:
            subprocess.run([str(JAVA / 'javac'), '-proc:none', '--release', '21', '-d', directory,
                            str(HERE / 'src/dev/infinity/clumpsprobe/OrbTotals.java'),
                            str(HERE / 'test/OrbTotalsTest.java')], check=True)
            result = subprocess.run([str(JAVA / 'java'), '-cp', directory,
                                     'dev.infinity.clumpsprobe/OrbTotalsTest'],
                                    check=True, text=True, capture_output=True)
            self.assertIn('PASS assertions=20 minecraft_loaded=false', result.stdout)

    def test_forge_metadata_and_compile_only_dependency(self):
        jar = HERE / 'build/unified-clumps-probe-0.1.0.jar'
        with zipfile.ZipFile(jar) as archive:
            metadata = tomllib.loads(archive.read('META-INF/mods.toml').decode())
            self.assertEqual(metadata['modLoader'], 'javafml')
            self.assertEqual(metadata['mods'][0]['modId'], 'unified_clumps_probe')
            deps = {entry['modId']: entry for entry in metadata['dependencies']['unified_clumps_probe']}
            self.assertEqual(set(deps), {'forge', 'minecraft', 'clumps'})
            self.assertEqual(deps['clumps']['versionRange'], '[19.0.0.1]')
            self.assertTrue(all(entry['mandatory'] for entry in deps.values()))
            self.assertEqual(archive.read('META-INF/LICENSE'), (HERE / 'LICENSE').read_bytes())
            self.assertFalse(any(name.startswith(('com/blamejared/', 'net/')) for name in archive.namelist()))
            self.assertFalse(any('OrbTotalsTest' in name for name in archive.namelist()))

    def test_build_report_matches_artifact(self):
        report = json.loads((HERE / 'build/build-report.json').read_text())
        jar = ROOT / report['probe']
        self.assertEqual(hashlib.sha256(jar.read_bytes()).hexdigest(), report['sha256'])
        self.assertTrue(report['runtime_validation'].startswith('NOT RUN:'))
        self.assertEqual(report['clumps_sha256'], 'e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19')
        self.assertEqual(report['no_clumped_map_setter_check'], 'PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
