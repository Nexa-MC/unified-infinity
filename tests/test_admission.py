import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from compat_admission import Limits, Target, plan
from compat_admission.versions import UnsupportedVersion, fabric_matches, maven_matches


def jar_bytes(entries, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'w', compression=compression) as jar:
            for name, data in entries:
                jar.writestr(name, data)
    return buffer.getvalue()


def fabric(mid='sample_mod', version='1.0.0', **extra):
    return json.dumps({'schemaVersion': 1, 'id': mid, 'version': version, **extra})


def neo(mid='neo_sample', version='1.0.0', dependencies='', loader='[4,)'):
    return f'modLoader="javafml"\nloaderVersion="{loader}"\nlicense="MIT"\n[[mods]]\nmodId="{mid}"\nversion="{version}"\n{dependencies}'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def jar(self, filename='sample.jar', metadata=None, entries=(), compression=zipfile.ZIP_STORED):
        path = self.root / filename
        content = [] if metadata is None else [('fabric.mod.json', metadata)]
        path.write_bytes(jar_bytes(content + list(entries), compression))
        return path

    def codes(self, report):
        return {issue['code'] for issue in report['issues']}

    def inventory(self, entries):
        path = self.root / 'inventory.json'
        path.write_text(json.dumps({'schema_version': 1, 'bundled_apis': entries}))
        return path

    def test_valid_fabric_keeps_hash_and_original_bytes(self):
        jar = self.jar(metadata=fabric(depends={'minecraft': '~1.21.1', 'java': '>=21', 'fabricloader': '>=0.16.0'}))
        before = jar.read_bytes()
        report = plan([jar], target=Target(fabric_loader_version='0.16.10'))
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(report['runtime_compatibility'], 'unverified')
        self.assertEqual(report['artifacts'][0]['sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(jar.read_bytes(), before)

    def test_valid_neoforge(self):
        deps = '[[dependencies.neo_sample]]\nmodId="minecraft"\ntype="required"\nversionRange="[1.21.1]"\nside="BOTH"\nordering="NONE"'
        jar = self.jar(entries=[('META-INF/neoforge.mods.toml', neo(dependencies=deps))])
        self.assertEqual(plan([jar], target=Target(fml_version='4.0.1'))['admission'], 'metadata_pass')

    def test_missing_dependency(self):
        report = plan([self.jar(metadata=fabric(depends={'absent': '*'}))])
        self.assertIn('DEPENDENCY_MISSING', self.codes(report))
        self.assertEqual(report['admission'], 'rejected')

    def test_wrong_game(self):
        report = plan([self.jar(metadata=fabric(depends={'minecraft': '1.20.1'}))])
        self.assertIn('GAME_VERSION_MISMATCH', self.codes(report))

    def test_unsupported_target(self):
        report = plan([self.jar(metadata=fabric())], target=Target(minecraft='1.20.1'))
        self.assertIn('GAME_VERSION_UNSUPPORTED', self.codes(report))

    def test_loader_not_assumed(self):
        report = plan([self.jar(metadata=fabric(depends={'fabricloader': '>=0.16.0'}))])
        self.assertIn('LOADER_VERSION_UNKNOWN', self.codes(report))

    def test_neoforge_fml_distinct_from_neoforge_version(self):
        jar = self.jar(entries=[('META-INF/neoforge.mods.toml', neo())])
        report = plan([jar], target=Target(neoforge_version='21.1.1'))
        self.assertIn('LOADER_VERSION_UNKNOWN', self.codes(report))

    def test_duplicate_logical_ids(self):
        report = plan([self.jar('one.jar', fabric()), self.jar('two.jar', fabric())])
        self.assertIn('DEPENDENCY_DUPLICATE_ID', self.codes(report))

    def test_provides_alias_satisfies_dependency(self):
        report = plan([self.jar('one.jar', fabric(provides=['old_name'])), self.jar('two.jar', fabric('consumer', depends={'old_name': '1.0.0'}))])
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(report['dependency_groups'], [['sample_mod'], ['consumer']])

    def test_duplicate_alias(self):
        report = plan([self.jar('one.jar', fabric(provides=['other_mod'])), self.jar('two.jar', fabric('other_mod'))])
        self.assertIn('DEPENDENCY_DUPLICATE_ID', self.codes(report))

    def test_bundled_inventory_satisfies_original_api_id(self):
        inv = self.inventory([{'id': 'fabric-api', 'version': '0.100.0+1.21.1', 'ecosystem': 'fabric'}])
        report = plan([self.jar(metadata=fabric(depends={'fabric-api': '>=0.100.0'}))], bundled_inventory=inv)
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(report['bundled_apis'][0]['version'], '0.100.0+1.21.1')
        self.assertEqual(report['bundled_apis'][0]['verification'], 'provided_inventory_only')

    def test_bundled_api_conflict(self):
        inv = self.inventory([{'id': 'fabric-api', 'version': '1.0.0', 'ecosystem': 'fabric'}])
        report = plan([self.jar(metadata=fabric('fabric-api'))], bundled_inventory=inv)
        self.assertIn('API_BUNDLED_CONFLICT', self.codes(report))

    def test_bundled_api_version_mismatch(self):
        inv = self.inventory([{'id': 'fabric-api', 'version': '1.0.0', 'ecosystem': 'fabric'}])
        report = plan([self.jar(metadata=fabric(depends={'fabric-api': '>=2.0.0'}))], bundled_inventory=inv)
        self.assertIn('API_VERSION_MISMATCH', self.codes(report))

    def test_invalid_inventory_is_not_assumed(self):
        inv = self.inventory([{'id': 'fabric-api', 'ecosystem': 'fabric'}])
        report = plan([self.jar(metadata=fabric())], bundled_inventory=inv)
        self.assertEqual(report['admission'], 'rejected')
        self.assertEqual(report['bundled_apis'], [])

    def test_environment_exclusion(self):
        report = plan([self.jar(metadata=fabric(environment='client'))], target=Target(environment='server'))
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(report['summary']['excluded_mods'], 1)
        self.assertIn('ENVIRONMENT_EXCLUDED', self.codes(report))

    def test_side_excluded_dependency_fails_clearly(self):
        report = plan([self.jar('one.jar', fabric('client_mod', environment='client')), self.jar('two.jar', fabric('common_mod', depends={'client_mod': '*'}))], target=Target(environment='server'))
        self.assertIn('ENVIRONMENT_DEPENDENCY', self.codes(report))

    def test_neoforge_side_dependency_ignored_on_other_side(self):
        deps = '[[dependencies.neo_sample]]\nmodId="absent_mod"\ntype="required"\nversionRange="[1,)"\nside="CLIENT"'
        jar = self.jar(entries=[('META-INF/neoforge.mods.toml', neo(dependencies=deps))])
        self.assertEqual(plan([jar], target=Target(environment='server', fml_version='4'))['admission'], 'metadata_pass')

    def test_mutual_dependencies_are_grouped_not_recursed(self):
        report = plan([self.jar('one.jar', fabric('first_mod', depends={'second_mod': '*'})), self.jar('two.jar', fabric('second_mod', depends={'first_mod': '*'}))])
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertIn('DEPENDENCY_CYCLE_GROUP', self.codes(report))
        self.assertEqual(report['dependency_groups'], [['first_mod', 'second_mod']])

    def test_explicit_ordering_cycle_rejected(self):
        def dep(owner, other):
            return f'[[dependencies.{owner}]]\nmodId="{other}"\ntype="required"\nversionRange="[1,)"\nordering="AFTER"'
        one = self.jar('one.jar', entries=[('META-INF/neoforge.mods.toml', neo('first_mod', dependencies=dep('first_mod', 'second_mod')))])
        two = self.jar('two.jar', entries=[('META-INF/neoforge.mods.toml', neo('second_mod', dependencies=dep('second_mod', 'first_mod')))])
        self.assertIn('DEPENDENCY_ORDER_CYCLE', self.codes(plan([one, two], target=Target(fml_version='4'))))

    def test_breaks_dependency(self):
        report = plan([self.jar('one.jar', fabric('first_mod', breaks={'second_mod': '*'})), self.jar('two.jar', fabric('second_mod'))])
        self.assertIn('DEPENDENCY_INCOMPATIBLE', self.codes(report))

    def test_optional_absent_dependency_allowed(self):
        report = plan([self.jar(metadata=fabric(suggests={'absent_mod': '*'}))])
        self.assertEqual(report['admission'], 'metadata_pass')

    def test_unsupported_missing_dependency_range_rejected(self):
        report = plan([self.jar(metadata=fabric(depends={'absent_mod': '1.0 || 2.0'}))])
        self.assertIn('DEPENDENCY_UNSUPPORTED_RANGE', self.codes(report))

    def test_nested_fabric_archive(self):
        nested = jar_bytes([('fabric.mod.json', fabric('nested_mod'))])
        jar = self.jar(metadata=fabric(jars=[{'file': 'META-INF/jars/nested.jar'}]), entries=[('META-INF/jars/nested.jar', nested)])
        report = plan([jar])
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(len(report['artifacts']), 2)
        self.assertTrue(report['artifacts'][1]['origin'].endswith('!/META-INF/jars/nested.jar'))
        self.assertEqual(report['artifacts'][1]['sha256'], hashlib.sha256(nested).hexdigest())

    def test_nested_jar_missing(self):
        report = plan([self.jar(metadata=fabric(jars=[{'file': 'missing.jar'}]))])
        self.assertIn('METADATA_NESTED_MISSING', self.codes(report))

    def test_nested_depth_bounded(self):
        leaf = jar_bytes([('fabric.mod.json', fabric('leaf_mod'))])
        middle = jar_bytes([('fabric.mod.json', fabric('middle_mod', jars=[{'file': 'leaf.jar'}])), ('leaf.jar', leaf)])
        root = self.jar(metadata=fabric(jars=[{'file': 'middle.jar'}]), entries=[('middle.jar', middle)])
        self.assertIn('SECURITY_NESTING_DEPTH', self.codes(plan([root], limits=Limits(max_nested_depth=1))))

    def test_archive_size_bounded(self):
        jar = self.jar(metadata=fabric())
        self.assertIn('SECURITY_ARCHIVE_SIZE', self.codes(plan([jar], limits=Limits(max_archive_bytes=10))))

    def test_entry_count_bounded(self):
        jar = self.jar(metadata=fabric(), entries=[('asset', b'a')])
        self.assertIn('SECURITY_ENTRY_COUNT', self.codes(plan([jar], limits=Limits(max_entries=1))))

    def test_metadata_size_bounded(self):
        jar = self.jar(metadata=fabric())
        self.assertIn('SECURITY_METADATA_SIZE', self.codes(plan([jar], limits=Limits(max_metadata_bytes=10))))

    def test_zip_bomb_ratio_bounded(self):
        jar = self.jar(metadata=fabric(), entries=[('bomb', b'A'*1000000)], compression=zipfile.ZIP_DEFLATED)
        self.assertIn('SECURITY_COMPRESSION_RATIO', self.codes(plan([jar])))

    def test_aggregate_expanded_size_bounded(self):
        jar = self.jar(metadata=fabric(), entries=[('asset', b'A'*1000)])
        self.assertIn('SECURITY_UNCOMPRESSED_BUDGET', self.codes(plan([jar], limits=Limits(max_uncompressed_bytes=500))))

    def test_traversal_absolute_windows_paths_rejected(self):
        for name in ('../evil', '/evil', 'safe/../evil', 'C:/evil', 'safe\\evil', './evil', 'safe//evil'):
            with self.subTest(name=name):
                report = plan([self.jar(metadata=fabric(), entries=[(name, 'x')])])
                self.assertIn('SECURITY_UNSAFE_PATH', self.codes(report))
                self.assertFalse((self.root.parent / 'evil').exists())

    def test_duplicate_entries_rejected(self):
        jar = self.jar(metadata=fabric(), entries=[('fabric.mod.json', fabric('other_mod'))])
        self.assertIn('SECURITY_DUPLICATE_ENTRY', self.codes(plan([jar])))

    def test_case_collisions_rejected(self):
        jar = self.jar(metadata=fabric(), entries=[('FABRIC.MOD.JSON', '{}')])
        self.assertIn('SECURITY_DUPLICATE_ENTRY', self.codes(plan([jar])))

    def test_symlink_entry_rejected(self):
        link = zipfile.ZipInfo('link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        jar = self.jar(metadata=fabric(), entries=[(link, '../outside')])
        self.assertIn('SECURITY_SPECIAL_ENTRY', self.codes(plan([jar])))

    def test_input_symlink_rejected(self):
        jar = self.jar(metadata=fabric())
        symlink = self.root / 'link.jar'; symlink.symlink_to(jar)
        self.assertIn('SECURITY_INPUT_UNREADABLE', self.codes(plan([symlink])))

    def test_no_metadata_rejected(self):
        self.assertIn('LOADER_UNKNOWN_METADATA', self.codes(plan([self.jar(entries=[('foo.class', b'CAFEBABE')])])))

    def test_ambiguous_multiloader_metadata_rejected(self):
        jar = self.jar(metadata=fabric(), entries=[('META-INF/neoforge.mods.toml', neo())])
        self.assertIn('LOADER_AMBIGUOUS_METADATA', self.codes(plan([jar])))

    def test_invalid_json_and_toml_fail_without_crash(self):
        for descriptor, raw in [('fabric.mod.json', '{'), ('META-INF/neoforge.mods.toml', '[[bad')]:
            with self.subTest(descriptor=descriptor):
                report = plan([self.jar(entries=[(descriptor, raw)])])
                self.assertEqual(report['admission'], 'rejected')
                self.assertIn('metadata', report['summary']['categories'])

    def test_duplicate_json_keys_rejected(self):
        jar = self.jar(metadata='{"schemaVersion":1,"id":"first_mod","id":"second_mod","version":"1.0"}')
        self.assertIn('METADATA_DUPLICATE_KEY', self.codes(plan([jar])))

    def test_reserved_id_rejected(self):
        self.assertIn('LOADER_RESERVED_ID', self.codes(plan([self.jar(metadata=fabric('minecraft'))])))

    def test_unresolved_version_rejected(self):
        self.assertIn('METADATA_UNRESOLVED_VERSION', self.codes(plan([self.jar(metadata=fabric(version='${version}'))])))

    def test_manifest_version_substitution(self):
        jar = self.jar(entries=[('META-INF/neoforge.mods.toml', neo(version='${file.jarVersion}')), ('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\r\nImplementation-Version: 2.0.\r\n 1\r\n\r\n')])
        report = plan([jar], target=Target(fml_version='4'))
        self.assertEqual(report['mods'][0]['version'], '2.0.1')
        self.assertEqual(report['admission'], 'metadata_pass')

    def test_jarjar_is_not_silently_ignored(self):
        jar = self.jar(entries=[('META-INF/neoforge.mods.toml', neo()), ('META-INF/jarjar/metadata.json', '{}')])
        self.assertIn('LOADER_JARJAR_UNSUPPORTED', self.codes(plan([jar], target=Target(fml_version='4'))))

    def test_reading_does_not_execute_python_or_classes(self):
        marker = self.root / 'executed'
        jar = self.jar(metadata=fabric(), entries=[('__main__.py', f'open({str(marker)!r},"w").write("bad")'), ('malicious.class', b'not really a class')])
        self.assertEqual(plan([jar])['admission'], 'metadata_pass')
        self.assertFalse(marker.exists())

    def test_empty_input_rejected(self):
        self.assertIn('METADATA_NO_INPUTS', self.codes(plan([])))

    def test_cli_json_and_exit_code(self):
        jar = self.jar(metadata=fabric())
        proc = subprocess.run([sys.executable, '-m', 'compat_admission', 'plan', str(jar)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['runtime_compatibility'], 'unverified')

    def test_cli_refuses_output_over_input(self):
        jar = self.jar(metadata=fabric())
        before = jar.read_bytes()
        proc = subprocess.run([sys.executable, '-m', 'compat_admission', 'plan', str(jar), '--output', str(jar)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(jar.read_bytes(), before)

    def test_forged_directory_count_does_not_bypass_budget(self):
        jar = self.jar(metadata=fabric(), entries=[('asset', b'x')])
        data = bytearray(jar.read_bytes())
        end = data.rfind(b'PK\x05\x06')
        struct.pack_into('<HH', data, end+8, 1, 1)
        jar.write_bytes(data)
        self.assertIn('SECURITY_ENTRY_COUNT', self.codes(plan([jar], limits=Limits(max_entries=1))))

    def test_zip64_end_marker_rejected(self):
        jar = self.jar(metadata=fabric())
        data = bytearray(jar.read_bytes()); end = data.rfind(b'PK\x05\x06')
        struct.pack_into('<HH', data, end+8, 65535, 65535)
        jar.write_bytes(data)
        self.assertIn('SECURITY_ZIP64_UNSUPPORTED', self.codes(plan([jar])))

    def test_local_header_name_mismatch_rejected(self):
        jar = self.jar(metadata=fabric())
        data = bytearray(jar.read_bytes()); data[30] = ord('z'); jar.write_bytes(data)
        self.assertIn('SECURITY_ARCHIVE_LAYOUT', self.codes(plan([jar])))

    def test_archive_trailing_garbage_rejected(self):
        jar = self.jar(metadata=fabric()); jar.write_bytes(jar.read_bytes()+b'garbage')
        self.assertIn('SECURITY_ARCHIVE_LAYOUT', self.codes(plan([jar])))

    def test_encrypted_bit_rejected(self):
        jar = self.jar(metadata=fabric()); data = bytearray(jar.read_bytes())
        central = data.find(b'PK\x01\x02')
        struct.pack_into('<H', data, 6, 1); struct.pack_into('<H', data, central+8, 1)
        jar.write_bytes(data)
        self.assertIn('SECURITY_ENCRYPTED_ENTRY', self.codes(plan([jar])))

    def test_non_deflate_compression_rejected(self):
        jar = self.jar(metadata=fabric(), compression=zipfile.ZIP_BZIP2)
        self.assertIn('SECURITY_COMPRESSION_METHOD', self.codes(plan([jar])))

    def test_corrupted_deflate_metadata_rejected_without_crash(self):
        jar = self.jar(metadata=fabric(), compression=zipfile.ZIP_DEFLATED)
        data = bytearray(jar.read_bytes()); name_length, extra_length = struct.unpack_from('<HH', data, 26)
        start = 30+name_length+extra_length
        data[start:start+4] = b'\xff\xff\xff\xff'; jar.write_bytes(data)
        self.assertEqual(plan([jar])['admission'], 'rejected')

    def test_corrupted_crc_rejected(self):
        jar = self.jar(metadata=fabric()); data = bytearray(jar.read_bytes())
        name_length, extra_length = struct.unpack_from('<HH', data, 26)
        data[30+name_length+extra_length] ^= 1; jar.write_bytes(data)
        self.assertEqual(plan([jar])['admission'], 'rejected')

    def test_top_level_archive_count_bounded(self):
        jars = [self.jar('one.jar', fabric()), self.jar('two.jar', fabric('second_mod'))]
        self.assertIn('SECURITY_ARCHIVE_COUNT', self.codes(plan(jars, limits=Limits(max_archives=1))))

    def test_missing_file_is_diagnostic(self):
        self.assertIn('SECURITY_INPUT_UNREADABLE', self.codes(plan([self.root / 'missing.jar'])))

    def test_dependency_limit(self):
        jar = self.jar(metadata=fabric(depends={'first_mod': '*', 'second_mod': '*'}))
        self.assertIn('SECURITY_DEPENDENCY_LIMIT', self.codes(plan([jar], limits=Limits(max_dependencies=1))))

    def test_bundled_alias_retained(self):
        inv = self.inventory([{'id': 'fabric-api', 'version': '1.0.0', 'ecosystem': 'fabric', 'provides': ['fabric']}])
        report = plan([self.jar(metadata=fabric(depends={'fabric': '*'}))], bundled_inventory=inv)
        self.assertEqual(report['admission'], 'metadata_pass')
        self.assertEqual(report['bundled_apis'][0]['provides'], ['fabric'])

    def test_bundled_duplicate_id_rejected(self):
        record = {'id': 'fabric-api', 'version': '1.0.0', 'ecosystem': 'fabric'}
        report = plan([self.jar(metadata=fabric())], bundled_inventory=self.inventory([record, record]))
        self.assertIn('API_BUNDLED_CONFLICT', self.codes(report))

    def test_boolean_inventory_schema_rejected(self):
        path = self.root / 'inventory.json'
        path.write_text('{"schema_version":true,"bundled_apis":[]}')
        self.assertIn('API_INVALID_INVENTORY', self.codes(plan([self.jar(metadata=fabric())], bundled_inventory=path)))

    def test_neoforge_optional_installed_wrong_version_rejected(self):
        deps = '[[dependencies.neo_sample]]\nmodId="other_mod"\ntype="optional"\nversionRange="[2,)"'
        one = self.jar('one.jar', entries=[('META-INF/neoforge.mods.toml', neo(dependencies=deps))])
        two = self.jar('two.jar', fabric('other_mod', '1.0.0'))
        report = plan([one, two], target=Target(fml_version='4'))
        self.assertEqual(report['admission'], 'rejected')

    def test_deep_json_metadata_rejected_without_crash(self):
        raw = '{"schemaVersion":1,"id":"sample_mod","version":"1","custom":'+'['*2000+'0'+']'*2000+'}'
        self.assertEqual(plan([self.jar(metadata=raw)])['admission'], 'rejected')

    def test_invalid_field_types_rejected_without_crash(self):
        for field in ('id', 'version', 'environment', 'provides', 'depends', 'jars'):
            with self.subTest(field=field):
                values = {'schemaVersion': 1, 'id': 'sample_mod', 'version': '1.0.0', field: 42}
                self.assertEqual(plan([self.jar(metadata=json.dumps(values))])['admission'], 'rejected')


class RuntimeAuthoritativeTests(unittest.TestCase):
    setUp = AdmissionTests.setUp
    tearDown = AdmissionTests.tearDown
    jar = AdmissionTests.jar
    codes = AdmissionTests.codes
    inventory = AdmissionTests.inventory

    def runtime(self, jars, **kwargs):
        return plan(jars, runtime_authoritative=True, **kwargs)

    def jarjar(self, children, metadata=None):
        declarations = [{'identifier': {'group': 'fixture', 'artifact': f'child{i}'},
                         'version': {'range': '[1,)', 'artifactVersion': '1.0.0'}, 'path': name}
                        for i, (name, _) in enumerate(children)]
        return self.jar(entries=[('META-INF/neoforge.mods.toml', neo()),
                                 ('META-INF/jarjar/metadata.json', json.dumps({'jars': declarations}) if metadata is None else metadata),
                                 *children])

    def test_never_claims_metadata_pass_or_selected_graph(self):
        report = self.runtime([self.jar(metadata=fabric())])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertEqual(report['candidate_selection'], 'deferred')
        self.assertEqual(report['runtime_authority']['components'], ['NeoForge FML', 'Sinytra Connector'])
        self.assertIsNone(report['dependency_groups'])
        self.assertIsNone(report['ordering_constraints'])
        self.assertFalse(report['candidate_graph_authoritative'])
        self.assertNotIn('active', report['mods'][0])
        self.assertEqual(report['mods'][0]['selection'], 'deferred')

    def test_duplicate_candidates_and_dependencies_are_deferred(self):
        one = self.jar('one.jar', fabric(depends={'absent_mod': '*'}))
        two = self.jar('two.jar', fabric(version='2.0.0'))
        report = self.runtime([one, two])
        self.assertEqual(report['admission'], 'runtime_deferred')
        for code in ('DEPENDENCY_DUPLICATE_ID', 'DEPENDENCY_MISSING'):
            issue = next(i for i in report['issues'] if i['code'] == code)
            self.assertEqual(issue['severity'], 'deferred')
            self.assertIn('decision_owner', issue)

    def test_mod_game_range_mismatch_is_deferred(self):
        report = self.runtime([self.jar(metadata=fabric(depends={'minecraft': '1.20.1'}))])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertIn('GAME_VERSION_MISMATCH', self.codes(report))

    def test_invalid_game_target_still_blocks(self):
        report = self.runtime([self.jar(metadata=fabric())], target=Target(minecraft='1.20.1'))
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('GAME_VERSION_UNSUPPORTED', self.codes(report))

    def test_invalid_environment_target_still_blocks(self):
        report = self.runtime([self.jar(metadata=fabric())], target=Target(environment='invalid'))
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('ENVIRONMENT_INVALID', self.codes(report))

    def test_invalid_java_target_still_blocks(self):
        for version in ('8', 'not_a_version', None):
            with self.subTest(version=version):
                report = self.runtime([self.jar(metadata=fabric())], target=Target(java_version=version))
                self.assertEqual(report['admission'], 'rejected')
                self.assertIn('TARGET_INVALID_VERSION', self.codes(report))

    def test_malformed_json_toml_not_downgraded(self):
        for descriptor, raw in [('fabric.mod.json', '{'), ('META-INF/neoforge.mods.toml', '[[invalid')]:
            with self.subTest(descriptor=descriptor):
                report = self.runtime([self.jar(entries=[(descriptor, raw)])])
                self.assertEqual(report['admission'], 'rejected')
                self.assertTrue(any(i['category'] == 'metadata' and i['severity'] == 'error' for i in report['issues']))

    def test_malformed_predicate_type_not_downgraded(self):
        report = self.runtime([self.jar(metadata=fabric(depends={'other_mod': 42}))])
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('METADATA_INVALID_FIELD', self.codes(report))

    def test_unsupported_range_is_deferred(self):
        report = self.runtime([self.jar(metadata=fabric(depends={'other_mod': '1.0 || 2.0'}))])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertIn('DEPENDENCY_UNSUPPORTED_RANGE', self.codes(report))

    def test_side_decisions_are_deferred(self):
        report = self.runtime([self.jar(metadata=fabric(environment='client'))], target=Target(environment='server'))
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertEqual(report['mods'][0]['selection'], 'deferred')
        self.assertIsNone(report['summary']['excluded_mods'])

    def test_unsafe_zip_still_blocks(self):
        report = self.runtime([self.jar(metadata=fabric(), entries=[('../unsafe', 'bad')])])
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('SECURITY_UNSAFE_PATH', self.codes(report))

    def test_jarjar_nested_candidates_are_inspected_and_deferred(self):
        child = jar_bytes([('fabric.mod.json', fabric())])
        parent = self.jarjar([('META-INF/jarjar/child.jar', child)])
        report = self.runtime([parent])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertEqual(len(report['artifacts']), 2)
        issue = next(i for i in report['issues'] if i['code'] == 'LOADER_JARJAR_UNSUPPORTED')
        self.assertEqual(issue['severity'], 'deferred')
        self.assertTrue(report['artifacts'][1]['origin'].endswith('!/META-INF/jarjar/child.jar'))

    def test_jarjar_unsafe_nested_entry_blocks(self):
        child = jar_bytes([('fabric.mod.json', fabric()), ('../escape', 'bad')])
        report = self.runtime([self.jarjar([('child.jar', child)])])
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('SECURITY_UNSAFE_PATH', self.codes(report))

    def test_jarjar_nonmod_library_still_inspected(self):
        child = jar_bytes([('sample.class', b'class bytes are not executed')])
        report = self.runtime([self.jarjar([('child.jar', child)])])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertEqual(len(report['artifacts']), 2)
        self.assertIn('LOADER_UNKNOWN_METADATA', self.codes(report))

    def test_jarjar_malformed_json_still_blocks(self):
        report = self.runtime([self.jarjar([], metadata='{broken')])
        self.assertEqual(report['admission'], 'rejected')

    def test_jarjar_malformed_structure_still_blocks(self):
        report = self.runtime([self.jarjar([], metadata='{"jars":[{"path":"child.jar"}]}')])
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('METADATA_INVALID_JARJAR', self.codes(report))

    def test_jarjar_nested_archive_budget_still_blocks(self):
        child = jar_bytes([('fabric.mod.json', fabric())])
        report = self.runtime([self.jarjar([('child.jar', child)])], limits=Limits(max_archives=1))
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('SECURITY_ARCHIVE_COUNT', self.codes(report))

    def test_nested_fabric_security_checked_after_unsupported_range(self):
        child = jar_bytes([('../unsafe', 'bad')])
        parent = self.jar(metadata=fabric(depends={'other_mod': '1 || 2'}, jars=[{'file': 'child.jar'}]), entries=[('child.jar', child)])
        report = self.runtime([parent])
        self.assertEqual(report['admission'], 'rejected')
        self.assertIn('DEPENDENCY_UNSUPPORTED_RANGE', self.codes(report))
        self.assertIn('SECURITY_UNSAFE_PATH', self.codes(report))

    def test_repeated_fabric_nested_candidate_deferred_and_inspected_once(self):
        child = jar_bytes([('fabric.mod.json', fabric('child_mod'))])
        parent = self.jar(metadata=fabric(jars=[{'file': 'child.jar'}, {'file': 'child.jar'}]), entries=[('child.jar', child)])
        report = self.runtime([parent])
        self.assertEqual(report['admission'], 'runtime_deferred')
        self.assertEqual(len(report['artifacts']), 2)
        self.assertIn('DEPENDENCY_DUPLICATE_NESTED', self.codes(report))

    def test_dual_descriptor_cannot_hide_malformed_json(self):
        parent = self.jar(metadata='{broken', entries=[('META-INF/neoforge.mods.toml', neo())])
        self.assertEqual(self.runtime([parent])['admission'], 'rejected')

    def test_optional_version_mismatch_not_repromoted_to_error(self):
        deps = '[[dependencies.neo_sample]]\nmodId="other_mod"\ntype="optional"\nversionRange="[2,)"'
        one = self.jar('one.jar', entries=[('META-INF/neoforge.mods.toml', neo(dependencies=deps))])
        two = self.jar('two.jar', fabric('other_mod', '1.0.0'))
        self.assertEqual(self.runtime([one, two], target=Target(fml_version='4'))['admission'], 'runtime_deferred')

    def test_cli_runtime_authoritative_flag(self):
        jar = self.jar(metadata=fabric(depends={'absent_mod': '*'}))
        proc = subprocess.run([sys.executable, '-m', 'compat_admission', 'plan', str(jar), '--runtime-authoritative'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['admission'], 'runtime_deferred')


class JavaTargetPolicyTests(unittest.TestCase):
    setUp = AdmissionTests.setUp
    tearDown = AdmissionTests.tearDown
    jar = AdmissionTests.jar

    def test_java_21_maintenance_and_25_allowed_in_both_modes(self):
        jar = self.jar(metadata=fabric())
        for version in ('21', '21.0.12', '25'):
            for runtime in (False, True):
                with self.subTest(version=version, runtime=runtime):
                    report = plan([jar], target=Target(java_version=version), runtime_authoritative=runtime)
                    self.assertEqual(report['admission'], 'runtime_deferred' if runtime else 'metadata_pass')
                    self.assertEqual(report['java_policy']['minimum_major'], 21)
                    self.assertEqual(report['java_policy']['declared_target_version'], version)
                    self.assertEqual(report['java_policy']['actual_jvm_observation'], 'not_performed_by_preflight')
                    self.assertTrue(report['java_policy']['applies_to_future_target_adapters'])
                    self.assertTrue(report['java_policy']['higher_game_requirements_may_raise_minimum'])

    def test_java_17_blocks_in_both_modes_and_is_never_deferred(self):
        jar = self.jar(metadata=fabric())
        for runtime in (False, True):
            with self.subTest(runtime=runtime):
                report = plan([jar], target=Target(java_version='17'), runtime_authoritative=runtime)
                self.assertEqual(report['admission'], 'rejected')
                issue = next(i for i in report['issues'] if i['code'] == 'TARGET_INVALID_VERSION')
                self.assertEqual(issue['severity'], 'error')
                self.assertEqual(issue['details']['minimum_java_major'], 21)

    def test_malformed_java_target_blocks_in_both_modes(self):
        jar = self.jar(metadata=fabric())
        for version in ('invalid', '', None, 21):
            for runtime in (False, True):
                with self.subTest(version=version, runtime=runtime):
                    report = plan([jar], target=Target(java_version=version), runtime_authoritative=runtime)
                    self.assertEqual(report['admission'], 'rejected')
                    self.assertTrue(any(i['code'] == 'TARGET_INVALID_VERSION' and i['severity'] == 'error' for i in report['issues']))

    def test_java_floor_does_not_expand_minecraft_target_support(self):
        jar = self.jar(metadata=fabric())
        report = plan([jar], target=Target(minecraft='1.22', java_version='25'), runtime_authoritative=True)
        self.assertEqual(report['admission'], 'rejected')
        self.assertTrue(any(i['code'] == 'GAME_VERSION_UNSUPPORTED' for i in report['issues']))


class VersionTests(unittest.TestCase):
    def test_fabric_comparison_and_conjunction(self):
        self.assertTrue(fabric_matches('1.21.1', '>=1.21 <1.22'))
        self.assertFalse(fabric_matches('1.22', '>=1.21 <1.22'))

    def test_fabric_or_array(self):
        self.assertTrue(fabric_matches('2.0.0', ['1.0.0', '2.0.0']))

    def test_fabric_no_short_circuit_unknown_alternative(self):
        with self.assertRaises(UnsupportedVersion):
            fabric_matches('1.0.0', ['*', 'totally || unknown'])

    def test_wildcard_caret_tilde(self):
        for version, predicate, expected in [('1.21.1', '1.21.x', True), ('1.22', '1.21.*', False), ('0.2.9', '^0.2.3', True), ('0.3', '^0.2.3', True), ('1.9', '^1.2.3', True), ('2.0', '^1.2.3', False), ('1.2.9', '~1.2.3', True), ('1.3', '~1.2.3', False)]:
            with self.subTest(version=version, predicate=predicate):
                self.assertEqual(fabric_matches(version, predicate), expected)

    def test_fabric_empty_prerelease_and_zero_caret_semantics(self):
        self.assertTrue(fabric_matches('1.21.1', '>=1.21- <1.21.2-'))
        self.assertFalse(fabric_matches('1.21.2-alpha', '>=1.21- <1.21.2-'))
        self.assertTrue(fabric_matches('1.21-alpha', '1.21.x'))
        self.assertFalse(fabric_matches('1.22-alpha', '1.21.x'))
        self.assertTrue(fabric_matches('0.9', '^0.2.3'))
        self.assertFalse(fabric_matches('1.0-alpha', '^0.2.3'))
        self.assertFalse(fabric_matches('1.3-alpha', '~1.2.3'))

    def test_semver_prerelease_and_build(self):
        self.assertTrue(fabric_matches('1.0.0+build', '=1.0.0'))
        self.assertTrue(fabric_matches('0.116.15+2.3.5+1.21.1', '>=0.116.0'))
        self.assertTrue(fabric_matches('1.0.0-beta.2', '<1.0.0-beta.10'))
        self.assertFalse(fabric_matches('1.0.0-beta', '>=1.0.0'))

    def test_arbitrary_fabric_exact_version(self):
        self.assertTrue(fabric_matches('snapshot', 'snapshot'))
        self.assertFalse(fabric_matches('snapshot2', 'snapshot'))

    def test_maven_ranges(self):
        for version, predicate, expected in [('21.1.1', '[21.1,22)', True), ('22', '[21.1,22)', False), ('1.21.1', '[1.21.1]', True), ('1.21.2', '[1.21.1]', False), ('1.0', '(,2)', True)]:
            with self.subTest(version=version, predicate=predicate):
                self.assertEqual(maven_matches(version, predicate), expected)

    def test_maven_unsupported_unions_and_qualifiers(self):
        for predicate in ('[1,2),[3,4)', '[1-alpha,2)', '[2,1)', '[1,1)', '*', '1.0', '[,2]'):
            with self.subTest(predicate=predicate), self.assertRaises(UnsupportedVersion):
                maven_matches('1.0', predicate)


if __name__ == '__main__':
    unittest.main()
