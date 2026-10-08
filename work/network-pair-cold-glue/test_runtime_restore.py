"""Source-only behavioral checks: no downloads, Java, Gradle or installers."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('runtime_restore', HERE / 'runtime_restore.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeSourceChecks(unittest.TestCase):
    def test_known_input_closures(self):
        meta = runtime.load_sources(REPO)
        lock = runtime.compose_lock(REPO, meta)
        self.assertEqual(lock['missingOfficialInputs'], [])
        self.assertEqual(len(meta['serverClosure']), 95)
        self.assertEqual(len(meta['clientClasspathIdentities']), 95)
        self.assertEqual(len(meta['generatedFmlInputs']), 4)
        self.assertEqual(len(meta['generatedDevelopmentOutputs']), 2)
        preserved = [r['originalCompilePin'] for r in lock['artifacts'] if 'originalCompilePin' in r]
        preserved += [r for row in lock['artifacts'] for r in row.get('originalCompilePins', [])]
        original = json.loads((REPO / runtime.NONCE / 'dependency-lock.json').read_text())['artifacts']
        self.assertEqual(sorted(preserved, key=lambda r: r['path']), sorted(original, key=lambda r: r['path']))
        paths = [p for row in lock['artifacts'] for p in [row['path'], *row.get('also_seed', [])]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(sum(r['phase'] == 'client-assets' for r in lock['artifacts']), 3888)

    def test_prepare_is_only_text_and_exact_original_exporter(self):
        with tempfile.TemporaryDirectory(prefix='runtime-source-check-') as folder, \
             mock.patch('subprocess.run', side_effect=AssertionError('No processes permitted')), \
             mock.patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network permitted')):
            consumer = Path(folder) / 'consumer'
            plan = runtime.prepare(REPO, consumer)
            api = Path(plan['apiRoot'])
            runtime.verify_preparation(api)
            self.assertFalse(plan['jvmStarted'])
            self.assertFalse(plan['downloadsStarted'])
            self.assertEqual((api / 'four-loader/api-contract-controls/client-development/gradle/verification-metadata.xml').read_bytes(),
                             (REPO / runtime.NONCE / 'probe/gradle/verification-metadata.xml').read_bytes())
            self.assertEqual(len(plan['steps']), 5)
            project = api / 'four-loader/api-contract-controls/client-development'
            for name in ('build.gradle', 'settings.gradle'):
                self.assertEqual((project / name).read_bytes(), (REPO / runtime.CLIENT / name).read_bytes())
            for path in consumer.rglob('*'):
                if path.suffix == '.py': ast.parse(path.read_text(), filename=str(path))
                self.assertNotIn(path.suffix, {'.jar', '.class', '.zip', '.gz'})
            init = (api / 'ci/runtime-restore/client.init.gradle').read_text()
            self.assertIn("actual.contains(':prepareClientLaunch')", init)
            self.assertNotIn("':runClient'", init)
            command = plan['steps'][3]['command']
            self.assertEqual(command[-3:], ['prepareClientLaunch', '-x', 'downloadAssets'])
            self.assertIn('--offline', command)
            self.assertIn('--dependency-verification=strict', command)
            for step in plan['steps']:
                self.assertEqual(step['environment']['_JAVA_OPTIONS'],
                                 '-Xmx512m -XX:ActiveProcessorCount=1 -Djava.awt.headless=true')
            self.assertIn('-Xmx1280M', (project / 'build.gradle').read_text())
            (project / 'build.gradle').write_text('// mutated\n')
            with self.assertRaisesRegex(ValueError, 'preparation source changed'):
                runtime.verify_preparation(api)
            with self.assertRaisesRegex(ValueError, 'preparation already exists'):
                runtime.prepare(REPO, consumer)

    def test_rejects_source_or_traversal_destinations(self):
        for consumer in (REPO, REPO / 'work/api1', REPO / 'work/api1/nested'):
            with self.assertRaises(ValueError): runtime.prepare(REPO, consumer)
        with self.assertRaises(ValueError): runtime.relative('../escape')
        with self.assertRaises(ValueError): runtime.relative('/absolute')


if __name__ == '__main__':
    unittest.main()
