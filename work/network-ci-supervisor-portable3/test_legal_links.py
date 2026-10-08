"""Manifest-bound JDK notice aliases; pure local files only."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervisor as s
import test_input_modes


class LegalAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jdk = self.root / 'jdk'
        self.target = self.jdk / 'legal/java.base/LICENSE'
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'Synthetic legal text; not a runtime artifact\n')
        self.alias = self.jdk / 'legal/java.other/LICENSE'
        self.alias.parent.mkdir()
        self.alias.symlink_to('../java.base/LICENSE')
        self.row = {'path': str(self.alias), 'link_text': '../java.base/LICENSE',
                    'resolved_path': str(self.target), 'jdk_root': str(self.jdk)}
        self.spec = {'server': {'command': [str(self.jdk / 'bin/java')]},
                     'client': {'command': [str(self.jdk / 'bin/java')]},
                     'immutable_trees': [str(self.jdk)], 'jdk_legal_links': [self.row]}
        self.pins = {str(self.target): {'path': str(self.target), 'bytes': self.target.stat().st_size,
                                      'sha256': s.digest(self.target)}}

    def verify(self):
        return s.verify_jdk_legal_links(self.spec, self.pins, [self.root])

    def test_exact_legal_alias_and_target_preserved(self):
        self.assertEqual(self.verify(), {str(self.alias)})
        self.assertEqual(os.readlink(self.alias), '../java.base/LICENSE')

    def test_changed_link_text_rejected(self):
        self.alias.unlink()
        self.alias.symlink_to('../java.base/./LICENSE')
        with self.assertRaisesRegex(ValueError, 'link text changed'):
            self.verify()

    def test_false_declared_resolved_target_rejected(self):
        other = self.target.with_name('OTHER')
        other.write_bytes(b'other')
        self.pins[str(other)] = {'path': str(other), 'bytes': 5, 'sha256': s.digest(other)}
        self.row['resolved_path'] = str(other)
        with self.assertRaisesRegex(ValueError, 'resolved target changed'):
            self.verify()

    def test_outside_jdk_link_cannot_leave_and_return(self):
        outside = self.root / 'outside'
        outside.symlink_to(self.target)
        self.alias.unlink()
        self.alias.symlink_to('../../../outside')
        self.row['link_text'] = '../../../outside'
        with self.assertRaisesRegex(ValueError, 'escapes exact JDK'):
            self.verify()

    def test_resolved_target_outside_jdk_or_unpinned_rejected(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'outside')
        self.pins[str(outside)] = {'path': str(outside), 'bytes': 7, 'sha256': s.digest(outside)}
        self.row['resolved_path'] = str(outside)
        with self.assertRaisesRegex(ValueError, 'inside the exact JDK'):
            self.verify()
        self.row['resolved_path'] = str(self.target)
        self.pins.clear()
        with self.assertRaisesRegex(ValueError, 'canonical pinned file'):
            self.verify()

    def test_nonlegal_alias_wrong_jdk_or_directory_target_rejected(self):
        other = self.jdk / 'bin/java'
        other.parent.mkdir()
        other.symlink_to('../legal/java.base/LICENSE')
        self.row.update(path=str(other), link_text='../legal/java.base/LICENSE')
        with self.assertRaisesRegex(ValueError, 'Only legal-file'):
            self.verify()
        self.row.update(path=str(self.alias), link_text='../java.base/LICENSE', resolved_path=str(self.target.parent))
        self.pins[str(self.target.parent)] = {}
        with self.assertRaisesRegex(ValueError, 'canonical pinned file'):
            self.verify()
        self.row['jdk_root'] = str(self.root)
        with self.assertRaisesRegex(ValueError, 'exact command JDK'):
            self.verify()

    def test_legal_alias_cannot_target_executable_subtree(self):
        executable = self.jdk / 'bin/java'
        executable.parent.mkdir()
        executable.write_bytes(b'synthetic executable bytes')
        self.pins[str(executable)] = {'path': str(executable), 'bytes': executable.stat().st_size,
                                      'sha256': s.digest(executable)}
        self.alias.unlink()
        self.alias.symlink_to('../../bin/java')
        self.row.update(link_text='../../bin/java', resolved_path=str(executable))
        with self.assertRaisesRegex(ValueError, 'canonical pinned file'):
            self.verify()

    def test_cycle_rejected_without_unbounded_resolve(self):
        second = self.alias.with_name('SECOND')
        self.alias.unlink()
        self.alias.symlink_to('SECOND')
        second.symlink_to('LICENSE')
        self.row['link_text'] = 'SECOND'
        self.spec['jdk_legal_links'].append(dict(self.row, path=str(second), link_text='LICENSE'))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.verify()

    def test_unsealed_intermediate_alias_rejected(self):
        second = self.alias.with_name('SECOND')
        self.alias.unlink()
        self.alias.symlink_to('SECOND')
        second.symlink_to('../java.base/LICENSE')
        self.row['link_text'] = 'SECOND'
        with self.assertRaisesRegex(ValueError, 'Unsealed intermediate'):
            self.verify()

    def test_eight_hops_allowed_ninth_rejected(self):
        self.alias.unlink()
        rows = []
        for index in range(9):
            alias = self.alias.with_name(str(index))
            target = str(index + 1) if index < 8 else '../java.base/LICENSE'
            alias.symlink_to(target)
            rows.append(dict(self.row, path=str(alias), link_text=target))
        self.spec['jdk_legal_links'] = rows[1:]
        self.assertEqual(len(self.verify()), 8)
        self.spec['jdk_legal_links'] = rows
        with self.assertRaisesRegex(ValueError, 'depth exceeds eight'):
            self.verify()

    def test_duplicate_manifest_input_collision_and_bounds_rejected(self):
        self.spec['jdk_legal_links'] = [self.row, self.row]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.verify()
        self.spec['jdk_legal_links'] = [self.row]
        self.pins[str(self.alias)] = {}
        with self.assertRaisesRegex(ValueError, 'file-pinned'):
            self.verify()
        self.spec['jdk_legal_links'] = [self.row] * 1025
        with self.assertRaisesRegex(ValueError, 'bound exceeded'):
            self.verify()


class V2IntegratedInputs(unittest.TestCase):
    def setUp(self):
        test_input_modes.WholeSpecWritableConfigs.setUp(self)

    def test_full_tree_legal_alias_inventory_and_target_bytes(self):
        target = self.root / 'jdk/legal/java.base/LICENSE'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'test legal bytes')
        alias = self.root / 'jdk/legal/java.other/LICENSE'
        alias.parent.mkdir()
        alias.symlink_to('../java.base/LICENSE')
        self.spec['inputs'].append({'path': str(target), 'bytes': target.stat().st_size, 'sha256': s.digest(target)})
        self.spec['jdk_legal_links'] = [{'path': str(alias), 'link_text': '../java.base/LICENSE',
                                       'resolved_path': str(target), 'jdk_root': str(self.root / 'jdk')}]
        before = s.capture_server_properties(self.spec)
        s.verify_spec(self.spec, before, self.root / 'legal-poststart.json')
        target.write_bytes(b'changed legal bytes')
        with self.assertRaises(ValueError):
            s.verify_spec(self.spec, before)

    def test_unmanifested_alias_outside_root_and_overlapping_roots_rejected(self):
        alias = self.root / 'jdk/alias'
        alias.symlink_to('bin/java')
        with self.assertRaisesRegex(ValueError, 'Redirected immutable'):
            s.verify_spec(self.spec)
        alias.unlink()
        self.spec['preparation_roots'].append(str(self.root / 'jdk'))
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            s.verify_spec(self.spec)
        self.spec['preparation_roots'] = [str(self.root / 'server'), str(self.root / 'client')]
        with self.assertRaisesRegex(ValueError, 'outside explicit preparation roots'):
            s.verify_spec(self.spec)

    def test_actual_access_and_owner_write_claims_fail_closed(self):
        target = self.root / 'server/server.properties'
        original = os.access
        for denied in (os.R_OK, os.W_OK):
            def denied_access(path, mode, **kwargs):
                if Path(path) == target and mode == denied:
                    return False
                return original(path, mode, **kwargs)
            with self.subTest(denied=denied), patch('supervisor.os.access', side_effect=denied_access):
                with self.assertRaisesRegex(ValueError, 'actual read/execute|owner-write claim'):
                    s.verify_spec(self.spec)


if __name__ == '__main__':
    unittest.main()
