#!/usr/bin/env python3
"""Source-only regression tests. HTTP responses are mocked; no JVM executes."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


restore = load('source_test_restore_inputs', STAGE / 'portable-bootstrap/restore_inputs.py')
runtime = load('source_test_runtime_restore', HERE / 'runtime_restore.py')


class Response(io.BytesIO):
    def __init__(self, content, url):
        super().__init__(content)
        self.url = url

    def geturl(self):
        return self.url


class DeclaredMirrorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.payload = b'exact locked contents'
        self.row = {'path': 'mirror/artifact.jar', 'bytes': len(self.payload),
                    'sha256': hashlib.sha256(self.payload).hexdigest(),
                    'sha1': hashlib.sha1(self.payload).hexdigest(),
                    'urls': ['https://one.example/artifact', 'https://two.example/artifact']}
        self.calls = []
        self.responses = {}

    def factory(self, redirect):
        owner = self

        class Opener:
            def open(self, request, timeout):
                url = request.full_url
                owner.calls.append(url)
                effect = owner.responses[url]
                if isinstance(effect, Exception):
                    raise effect
                if isinstance(effect, tuple) and effect[0] == 'redirect':
                    redirect.redirect_request(request, None, 302, 'Moved', {}, effect[1])
                    raise AssertionError('Unsafe redirect was accepted')
                return Response(effect, url)

        return Opener()

    def invoke(self):
        with patch.object(restore.urllib.request, 'build_opener', self.factory), patch.object(restore.time, 'sleep'):
            return restore.restore(self.root, self.row, {'one.example', 'two.example'})

    def test_bad_same_size_hash_falls_back_without_accepting_bad_bytes(self):
        self.responses = {self.row['urls'][0]: b'x' * len(self.payload), self.row['urls'][1]: self.payload}
        result = self.invoke()
        self.assertEqual(result['status'], 'downloaded-and-verified')
        self.assertEqual((self.root / self.row['path']).read_bytes(), self.payload)
        self.assertEqual(self.calls, self.row['urls'])
        self.assertEqual(list((self.root / 'mirror').glob('.verified-download-*')), [])

    def test_oversized_and_short_responses_use_declared_alternative(self):
        for response in (self.payload + b'!', self.payload[:-1]):
            with self.subTest(size=len(response)):
                self.responses = {self.row['urls'][0]: response, self.row['urls'][1]: self.payload}
                self.invoke()
                (self.root / self.row['path']).unlink()

    def test_non_allowlisted_redirect_is_rejected_then_declared_mirror_used(self):
        self.responses = {self.row['urls'][0]: ('redirect', 'https://unlisted.example/collect'),
                          self.row['urls'][1]: self.payload}
        self.invoke()
        self.assertEqual(self.calls, self.row['urls'])

    def test_all_bad_mirrors_leave_no_artifact_or_temporary_download(self):
        self.responses = {url: b'wrong' for url in self.row['urls']}
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.invoke()
        self.assertFalse((self.root / self.row['path']).exists())
        self.assertEqual(list((self.root / 'mirror').iterdir()), [])

    def test_existing_bad_file_is_never_replaced_by_network_fallback(self):
        path = self.root / self.row['path']
        path.parent.mkdir()
        path.write_bytes(b'wrong')
        with self.assertRaises(restore.ArtifactMismatch):
            self.invoke()
        self.assertEqual(self.calls, [])
        self.assertEqual(path.read_bytes(), b'wrong')

    def test_hashes_both_remain_mandatory(self):
        self.row['sha1'] = '0' * 40
        self.responses = {url: self.payload for url in self.row['urls']}
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertFalse((self.root / self.row['path']).exists())

    def test_invalid_declared_url_fails_before_any_request(self):
        self.row['urls'][0] = 'https://unlisted.example/artifact'
        with self.assertRaises(restore.UnsafeURL):
            self.invoke()
        self.assertEqual(self.calls, [])

    def test_timeout_attempts_are_bounded_before_declared_fallback(self):
        self.responses = {self.row['urls'][0]: TimeoutError('test timeout'), self.row['urls'][1]: self.payload}
        self.invoke()
        self.assertEqual(self.calls, [self.row['urls'][0]] * 3 + [self.row['urls'][1]])

    def test_invalid_final_response_url_is_not_committed(self):
        class Opener:
            def open(inner, request, timeout):
                return Response(self.payload, 'https://unlisted.example/artifact')
        with patch.object(restore.urllib.request, 'build_opener', return_value=Opener()):
            with self.assertRaises(RuntimeError):
                restore.restore(self.root, self.row, {'one.example', 'two.example'})
        self.assertFalse((self.root / self.row['path']).exists())


class ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = runtime.load_sources(STAGE)
        cls.lock = runtime.compose_lock(STAGE, cls.meta)

    def test_original_compile_pins_and_sizes_unchanged(self):
        original = json.loads((STAGE / runtime.NONCE / 'dependency-lock.json').read_text())
        restored = []
        for row in self.lock['artifacts']:
            if 'originalCompilePin' in row:
                restored.append(row['originalCompilePin'])
            restored.extend(row.get('originalCompilePins', []))
        self.assertEqual(sorted(restored, key=lambda r: r['path']), sorted(original['artifacts'], key=lambda r: r['path']))
        self.assertEqual(self.lock['originalCompileBytes'], 637208559)
        self.assertEqual(self.lock['originalCompileRecords'], 360)
        self.assertEqual(self.lock['missingOfficialInputs'], [])

    def test_mojang_module_correct_route_preserves_identity(self):
        row = next(r for r in self.lock['artifacts'] if r['path'].endswith('minecraft-dependencies-1.21.1.module'))
        self.assertEqual(row['urls'], ['https://maven.neoforged.net/mojang-meta/net/neoforged/minecraft-dependencies/1.21.1/minecraft-dependencies-1.21.1.module'])
        self.assertEqual(row['sha256'], row['originalCompilePin']['sha256'])
        self.assertEqual(row['bytes'], row['originalCompilePin']['bytes'])
        self.assertIn('/releases/', row['originalCompilePin']['urls'][0])

    def test_explicit_config_and_existing_j2objc_are_present(self):
        config = next(r for r in self.lock['artifacts'] if r['path'].endswith('-moddev-config.json'))
        self.assertEqual(config['sha256'], runtime.MODDEV_CONFIG_SHA)
        self.assertEqual(config['bytes'], 10209)
        j2objc = [r for r in self.lock['artifacts'] if r['path'].endswith('j2objc-annotations-2.8.jar')]
        self.assertEqual(len(j2objc), 1)
        self.assertEqual(j2objc[0]['sha256'], 'f02a95fa1a5e95edb3ed859fd0fb7df709d121a35290eff8b74dce2ab7f4d6ed')

    def test_strict_metadata_adds_only_config_checksum(self):
        source = STAGE / runtime.NONCE / 'probe/gradle/verification-metadata.xml'
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'verification.xml'
            runtime.verification_metadata(STAGE, output, self.meta)
            ns = {'v': 'https://schema.gradle.org/dependency-verification'}
            original = ET.fromstring(before)
            generated = ET.fromstring(output.read_bytes())
            old = [ET.tostring(node) for node in original.findall('v:components/v:component/v:artifact', ns)]
            new = [ET.tostring(node) for node in generated.findall('v:components/v:component/v:artifact', ns)]
            self.assertEqual(len(new), len(old) + 1)
            self.assertTrue(all(row in new for row in old))
            self.assertEqual(ET.tostring(original.find('v:configuration', ns)), ET.tostring(generated.find('v:configuration', ns)))
            self.assertEqual(source.read_bytes(), before)
            component = next(c for c in generated.findall('v:components/v:component', ns)
                             if c.get('group') == 'net.neoforged' and c.get('name') == 'neoforge')
            config = next(a for a in component if a.get('name') == 'neoforge-21.1.219-moddev-config.json')
            self.assertEqual(config.find('v:sha256', ns).get('value'), runtime.MODDEV_CONFIG_SHA)

    def test_exact_95_entry_client_check_is_retained(self):
        rows = [{'path': '/isolated/' + r['name'], 'sha256': r['sha256']} for r in self.meta['clientClasspathIdentities']]
        self.assertEqual(len(rows), 95)
        runtime.verify_client_classpath(self.meta, {'inputs': rows})
        for changed in (rows[:-1], rows + [rows[0]], [{**rows[0], 'sha256': '0' * 64}, *rows[1:]]):
            with self.subTest(entries=len(changed)):
                with self.assertRaisesRegex(ValueError, 'classpath identity'):
                    runtime.verify_client_classpath(self.meta, {'inputs': changed})

    def test_exact_clumps_fixture_is_present(self):
        product = json.loads((HERE / 'product-input-lock.json').read_text())
        clumps = next(r for r in product['artifacts'] if 'Clumps' in r['path'])
        original = next(r for r in json.loads((STAGE / runtime.PUBLIC).read_text())['artifacts'] if r['path'] == clumps['path'])
        for key in ('bytes', 'sha256', 'urls'):
            self.assertEqual(clumps[key], original[key])
        self.assertEqual(clumps['bytes'], 18226)

    def test_active_quilt_script_has_all_exact_direct_cache_inputs(self):
        source = STAGE / 'work/emi-render-integration/candidate-complete-core-sources.zip'
        with zipfile.ZipFile(source) as archive:
            script = archive.read('four-loader/api-tests/run.sh').decode()
            abi = archive.read('four-loader/api-tests/verify_api_abi.py').decode()
        requested = re.findall(r'find "\$cache/([^"]+)" -name', script)
        self.assertEqual(set(requested), {'org.sinytra/forgified-fabric-loader',
                                        'org.jetbrains/annotations/24.1.0',
                                        'com.google.code.gson/gson', 'org.slf4j/slf4j-api'})
        paths = {name: row for row in self.lock['artifacts']
                 for name in [row['path'], *row.get('also_seed', [])]}
        core = json.loads((HERE / 'core-dependency-lock.json').read_text())
        cache = 'source-workspace/gradle-cache/caches/modules-2/files-2.1/'
        for requested_path in requested:
            matches = [(name, row) for name, row in paths.items()
                       if name.startswith(cache + requested_path + '/') and name.endswith('.jar')]
            self.assertEqual(len(matches), 1, requested_path)
            name, row = matches[0]
            original = next(r for r in core['artifacts']
                            if r['observed_source_path'].removeprefix('work/api1/') == name)
            for key in ('bytes', 'sha256'):
                self.assertEqual(row[key], original[key])
        reference = next(r for r in json.loads((HERE / 'product-input-lock.json').read_text())['artifacts']
                         if r['path'] == 'docs/four-loader/quilt/upstream/loader-0.30.1.jar')
        self.assertIn(reference['sha256'], abi)
        self.assertEqual(reference['bytes'], 3149891)

    def test_exact_original_forge_fixture_official_inputs_are_restorable(self):
        names = {'forge-1.21.1-52.1.0-universal.jar', 'eventbus-6.2.27.jar',
                 'javafmllanguage-1.21.1-52.1.0.jar', 'fmlcore-1.21.1-52.1.0.jar'}
        product = json.loads((HERE / 'product-input-lock.json').read_text())
        fixtures = [r for r in product['artifacts'] if r['phase'] == 'forge-fixture']
        self.assertEqual({Path(r['path']).name for r in fixtures}, names)
        public = {r['path']: r for r in json.loads((STAGE / runtime.PUBLIC).read_text())['artifacts']}
        for row in fixtures:
            self.assertTrue(row['path'].startswith('docs/four-loader/forge/upstream/'))
            for key in ('bytes', 'sha256', 'urls'):
                self.assertEqual(row[key], public[row['path']][key])
        self.assertFalse(any('forge-api-probe' in r['path'] for r in product['artifacts']))

    def test_quilt_aliases_do_not_create_duplicate_download_records(self):
        aliases = [r for r in self.meta['supplementalArtifacts'] if r['phase'] == 'core-regression-cache']
        self.assertEqual(len(aliases), 3)
        for alias in aliases:
            records = [r for r in self.lock['artifacts'] if r.get('sha256') == alias['sha256']]
            self.assertEqual(len(records), 1)
            destinations = [records[0]['path'], *records[0].get('also_seed', [])]
            self.assertIn(alias['path'], destinations)
            self.assertIn(alias['also_seed'][0], destinations)

    def test_fresh_preparation_is_text_only_and_seals_portable_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = Path(directory) / 'consumer'
            with (patch.object(runtime, 'restore', side_effect=AssertionError('No restoration allowed')),
                  patch.object(restore.urllib.request, 'build_opener', side_effect=AssertionError('No HTTP allowed'))):
                result = runtime.prepare(STAGE, consumer)
            api = consumer / 'work/api1'
            sealed = runtime.verify_preparation(api)
            self.assertFalse(result['jvmStarted'])
            self.assertFalse(result['downloadsStarted'])
            self.assertFalse(result['gameLaunched'])
            self.assertEqual(sealed['missingOfficialInputs'], [])
            installers = [s for s in result['steps'] if s['name'].startswith('installer-')]
            self.assertEqual(len(installers), 2)
            for installer in installers:
                command = installer['command']
                self.assertEqual(command[1:4], ['-Xmx512m', '-XX:ActiveProcessorCount=1', '-cp'])
                self.assertEqual(command[5:7], ['net.minecraftforge.installer.SimpleInstaller', '--offline'])
                self.assertEqual(command[4], str(api / 'docs/research/upstream/neoforge-21.1.219-installer.jar') + ':' + str(api / runtime.OFFLINE_CACHE))
                self.assertEqual(installer['timeoutSeconds'], 1800)
                self.assertTrue(installer['requiresExternalExecutionPolicy'])
            self.assertFalse((api / runtime.OFFLINE_CACHE).exists())
            step = next(s for s in result['steps'] if s['name'] == 'export-official-client')
            self.assertIn('--offline', step['command'])
            self.assertIn('--dependency-verification=strict', step['command'])
            script = (api / 'ci/runtime-restore/client.init.gradle').read_text()
            self.assertIn('metadataSources { gradleMetadata(); mavenPom() }', script)
            self.assertNotIn('/workspace/', script)
            build = (api / runtime.CLIENT.removeprefix('work/api1/') / 'build.gradle').read_text()
            self.assertIn("classpath(project.configurations.getByName('additionalRuntimeClasspath'))", build)


class OfflineInstallerTests(unittest.TestCase):
    def test_mocked_pack_uses_only_verified_text_and_original_zip_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Path(directory)
            payloads = [b'client mappings\n', b'server mappings\n', b'{"version":"test"}\n']
            inputs = tuple((entry, source, len(data), hashlib.sha256(data).hexdigest())
                           for (entry, source, _, _), data in zip(runtime.OFFLINE_TEXT_INPUTS, payloads))
            identities = {}
            lock_rows = []
            for (_, name, size, digest), data in zip(inputs, payloads):
                path = api / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                identities[path] = {'bytes': size, 'sha256': digest}
                lock_rows.append({'path': name, 'bytes': size, 'sha256': digest,
                                  'sha1': hashlib.sha1(data).hexdigest()})
            lock = api / 'ci/runtime-restore/input-lock.json'
            lock.parent.mkdir(parents=True)
            lock.write_text(json.dumps({'artifacts': lock_rows}))
            installer = api / 'docs/research/upstream/neoforge-21.1.219-installer.jar'
            identities[installer] = {'bytes': 6961236, 'sha256': '140df0fa17fd438848051ecfa3d091081515ad12bfe34fa126405037ba01de44'}
            identities[api / runtime.OFFLINE_CACHE] = runtime.OFFLINE_CACHE_IDENTITY
            fake_code = b'mocked pinned installer code'
            code_pins = {name: hashlib.sha256(fake_code).hexdigest() for name in runtime.INSTALLER_CLASSES}
            packed = {}
            metadata = {}

            class Archive:
                def __init__(self, path, mode='r', **kwargs):
                    self.installer = path == installer

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def namelist(self):
                    return list(code_pins) if self.installer else list(packed)

                def read(self, name):
                    return fake_code if self.installer else packed[name]

                def writestr(self, info, data):
                    metadata[info.filename] = (info.date_time, info.compress_type, info.external_attr, info.create_system)
                    packed[info.filename] = data

            with (patch.object(runtime, 'OFFLINE_TEXT_INPUTS', inputs),
                  patch.object(runtime, 'INSTALLER_CLASSES', code_pins),
                  patch.object(runtime, 'identity', side_effect=lambda path: identities[Path(path)]),
                  patch.object(runtime.zipfile, 'ZipFile', Archive)):
                result = runtime.prepare_offline_installer_cache(api)
                self.assertEqual(result['sha256'], runtime.OFFLINE_CACHE_IDENTITY['sha256'])
                self.assertEqual(list(packed), sorted(r[0] for r in inputs))
                self.assertEqual(packed, {r[0]: data for r, data in zip(inputs, payloads)})
                self.assertTrue(all(value == ((1980, 1, 1, 0, 0, 0), 0, 0o644 << 16, 3) for value in metadata.values()))
                identities[api / inputs[0][1]] = {'bytes': 1, 'sha256': '0' * 64}
                packed.clear()
                with self.assertRaisesRegex(ValueError, 'offline text input changed'):
                    runtime.prepare_offline_installer_cache(api)
                self.assertEqual(packed, {})
                identities[api / runtime.OFFLINE_CACHE] = {'bytes': 1, 'sha256': '0' * 64}
                with self.assertRaisesRegex(ValueError, 'text cache identity changed'):
                    runtime.verify_offline_installer_cache(api)
            self.assertFalse((api / runtime.OFFLINE_CACHE).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
