"""Source/mock contracts only: no package commands, downloads, GL, or JVMs."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import runner_dependencies as r


class RunnerSetupTests(unittest.TestCase):
    def setUp(self):
        self.candidates = r.load_candidates()
        self.names = {row['Package'] for row in self.candidates}

    def status(self, missing=(), extra=()):
        reference = json.loads((r.HERE/'ubuntu-graphics-reference.json').read_text())
        rows = [dict(row) for row in reference['reference_closure'] if row['Package'] not in missing]
        present = {row['Package'] for row in rows}
        for name in ('xvfb', 'libgl1-mesa-dri', 'dpkg', 'libc-bin'):
            if name not in present:
                rows.append({'Package': name, 'Architecture': 'amd64',
                             'Version': reference['observed_installed'][name]})
        rows.extend(extra)
        return ('\n\n'.join('\n'.join(k+': '+v for k, v in dict(row, Status='install ok installed').items()
            if isinstance(v, str)) for row in rows)+'\n\n').encode()

    def inspect_fixture(self, folder, data, proposed_exit=0, diagnostic='', baseline_exit=0):
        available = {'runner': {}, 'missingInputs': []}
        def paths(candidates, inventory, deadline):
            return ([{'package': row['Package'], 'path': r.PACKAGE_PATHS[row['Package']]}
                     for row in candidates if r.installed_row(inventory, row['Package'])], [])
        outputs = [{'exitCode': baseline_exit, 'stdout': '', 'stderr': ''},
                   {'exitCode': proposed_exit, 'stdout': '', 'stderr': diagnostic}]
        with mock.patch.object(r.graphics, 'availability', return_value=available), \
             mock.patch.object(r.graphics, 'trusted_installed'), \
             mock.patch.object(r, 'read_status', return_value=data), \
             mock.patch.object(r, 'verify_paths', side_effect=paths), \
             mock.patch.object(r, 'apt_check', side_effect=outputs) as apt:
            result = r.inspect({}, time.monotonic()+180, Path(folder)/'inspect')
        return result, apt

    def test_pinned_exact_seven_total_bytes_and_canonical_path(self):
        self.assertEqual(len(self.candidates), 7)
        self.assertEqual(sum(int(row['Size']) for row in self.candidates), 390800)
        self.assertEqual(r.graphics.REQUIRED['glxinfo'], r.CANONICAL)
        mesa = next(row for row in self.candidates if row['Package'] == 'libegl-mesa0')
        self.assertEqual(mesa['Version'], '25.2.8-0ubuntu0.24.04.2')
        self.assertIn('libgbm1 (= '+mesa['Version']+')', mesa['Depends'])

    def test_changed_reviewed_metadata_fails_closed(self):
        with mock.patch.object(r, 'METADATA_PINS', {'ubuntu-graphics-candidates.json': '0'*64}):
            with self.assertRaisesRegex(ValueError, 'metadata changed'):
                r.load_candidates()

    def test_positive_five_and_seven_preserve_whole_actual_status(self):
        for missing in (self.names - {'libegl-mesa0', 'libxcb-xkb1'}, self.names):
            with self.subTest(count=len(missing)), tempfile.TemporaryDirectory() as folder:
                unrelated = {'Package': 'unrelated-runner-tool', 'Architecture': 'amd64',
                             'Version': '99', 'Depends': 'runner-private-dependency (= 42)'}
                data = self.status(missing, [unrelated])
                result, apt = self.inspect_fixture(folder, data)
                self.assertFalse(result['blockers'])
                self.assertEqual({row['Package'] for row in result['missing']}, missing)
                self.assertEqual(Path(result['statusSnapshot']['path']).read_bytes(), data)
                proposed = (Path(folder)/'inspect/status.proposed').read_bytes()
                inventory = r.status_inventory(proposed)
                self.assertEqual(inventory[('unrelated-runner-tool', 'amd64')]['Depends'], unrelated['Depends'])
                self.assertGreater(result['statusSnapshot']['records'], 12)
                self.assertEqual(len(inventory), len(r.status_inventory(data))+len(missing))
                self.assertEqual(apt.call_count, 2)

    def test_installed_versions_retained_without_forcing_reference_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.status(self.names - {'libegl-mesa0', 'libxcb-xkb1'})
            data = data.replace(b'25.2.8-0ubuntu0.24.04.2', b'25.2.9-0ubuntu0.24.04.3')
            result, _ = self.inspect_fixture(folder, data)
            self.assertFalse(result['blockers'])
            retained = next(row for row in result['candidates'] if row['package'] == 'libegl-mesa0')
            self.assertEqual(retained['version'], '25.2.9-0ubuntu0.24.04.3')
            self.assertNotIn('libegl-mesa0', {row['Package'] for row in result['missing']})

    def assert_whole_graph_failure_precedes_download(self, diagnostic, extra=()):
        with tempfile.TemporaryDirectory() as folder:
            before, _ = self.inspect_fixture(folder, self.status(self.names, extra), 100, diagnostic)
            self.assertEqual(before['proposedAptCheck']['stderr'], diagnostic)
            self.assertIn(diagnostic, json.dumps(before['blockers']))
            output = Path(folder)/'consumer'; output.mkdir()
            with mock.patch.object(r, 'inspect', return_value=before), \
                 mock.patch.object(r, 'download') as download, \
                 mock.patch.object(r, 'install_debs') as install, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'Whole proposed'):
                    r.ensure({}, output, time.monotonic()+180, True)
                download.assert_not_called(); install.assert_not_called()
            receipt = json.loads((output/'runner-dependencies.json').read_text())
            self.assertFalse(receipt['packageInstallStarted'])
            self.assertFalse(receipt['graphicsStarted'])
            self.assertFalse(receipt['jvmStarted'])

    def test_missing_dependency_outside_seven_is_reported_before_download(self):
        self.assert_whole_graph_failure_precedes_download('libegl-mesa0 : Depends: libdrm2 (>= 2.4.125-1) but it is not installed')

    def test_mesa_companion_equality_conflict_before_download(self):
        self.assert_whole_graph_failure_precedes_download('libegl-mesa0 : Depends: libgbm1 (= 25.2.8-0ubuntu0.24.04.2) but 25.2.7 is installed')

    def test_unrelated_actual_reverse_dependency_failure_before_download(self):
        extra = [{'Package': 'unrelated-tool', 'Architecture': 'amd64', 'Version': '1',
                  'Depends': 'libgles2 (= 99)'}]
        self.assert_whole_graph_failure_precedes_download('unrelated-tool : Depends: libgles2 (= 99) but 1.7.0-1build1 is installed', extra)

    def test_broken_baseline_blocks_even_if_additions_incidentally_fix_it(self):
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.inspect_fixture(folder, self.status(self.names), baseline_exit=100)
            self.assertEqual(result['baselineAptCheck']['exitCode'], 100)
            self.assertEqual(result['proposedAptCheck']['exitCode'], 0)
            self.assertIn('Whole existing', result['blockers'][0]['reason'])
            consumer = Path(folder)/'consumer'; consumer.mkdir()
            with mock.patch.object(r, 'inspect', return_value=result), \
                 mock.patch.object(r, 'download') as download, \
                 mock.patch.object(r, 'install_debs') as install, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'Whole existing'):
                    r.ensure({}, consumer, time.monotonic()+180, True)
                download.assert_not_called(); install.assert_not_called()

    def test_wrong_runner_starts_no_package_commands_or_snapshot(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(r.graphics, 'availability', return_value={'missingInputs':[{'input':'runner'}]}), \
             mock.patch.object(r, 'query') as query:
            target = Path(folder)/'inspect'
            self.assertTrue(r.inspect({}, time.monotonic()+120, target)['blockers'])
            query.assert_not_called(); self.assertFalse(target.exists())

    def test_apt_command_is_isolated_read_only_and_sources_disabled(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'query', return_value=mock.Mock(returncode=100, stdout='broken', stderr='all diagnostics')) as query:
            root = Path(folder)
            result = r.apt_check(root/'status', root/'apt', time.monotonic()+120)
            args = query.call_args.args[0]
            self.assertEqual(args[:2], ['/usr/bin/apt-get', '--simulate'])
            self.assertEqual(args[-1], 'check')
            self.assertIn('Dir::State::status='+str(root/'status'), args)
            self.assertIn('Dir::Etc::sourceparts=-', args)
            self.assertEqual((root/'apt/sources.list').read_text(), '')
            self.assertEqual(list((root/'apt/lists').iterdir()), [])
            self.assertNotIn('trusted=yes', ' '.join(args))
            self.assertNotIn('install', args)
            self.assertEqual(result['stderr'], 'all diagnostics')

    def test_missing_requires_explicit_flag(self):
        before = {'canonicalPresent': False, 'blockers': [], 'missing': self.candidates}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=before), \
             mock.patch.object(r, 'download') as fetch, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'flag required'):
                r.ensure({}, folder, time.monotonic()+120)
            fetch.assert_not_called()

    def test_existing_healthy_state_skips_all_mutation(self):
        before = {'canonicalPresent': True, 'blockers': [], 'missing': []}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=before), \
             mock.patch.object(r, 'download') as fetch, mock.patch.object(r, 'install_debs') as install, \
             contextlib.redirect_stdout(io.StringIO()):
            result = r.ensure({}, folder, time.monotonic()+180, True)
            self.assertEqual(result['status'], 'ALREADY_INSTALLED_NO_MUTATION')
            fetch.assert_not_called(); install.assert_not_called()

    def test_one_bounded_install_for_five_or_seven_then_whole_state_recheck(self):
        for count in (5, 7):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as folder:
                missing = self.candidates[:count]
                before_path = Path(folder)/'before.status'; before_path.write_bytes(self.status({row['Package'] for row in missing}))
                after_path = Path(folder)/'after.status'; after_path.write_bytes(self.status())
                before = {'blockers': [], 'missing': missing, 'canonicalPresent': False,
                          'statusSnapshot': {'path': str(before_path), 'sha256': 'fixture'}}
                after = {'blockers': [], 'missing': [], 'canonicalPresent': True,
                         'statusSnapshot': {'path': str(after_path)}}
                def fetch(candidate, path, deadline):
                    return {'path': str(path), 'candidate': candidate}
                with mock.patch.object(r, 'inspect', side_effect=[before, after]) as inspect, \
                     mock.patch.object(r, 'require_status_unchanged'), \
                     mock.patch.object(r, 'download', side_effect=fetch) as download, \
                     mock.patch.object(r, 'verify_deb', return_value={}), \
                     mock.patch.object(r, 'install_debs', return_value={'processReaped': True}) as install, \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = r.ensure({}, folder, time.monotonic()+999, True)
                self.assertEqual(result['status'], 'PINNED_CLOSURE_INSTALLED')
                self.assertEqual(download.call_count, count)
                install.assert_called_once()
                self.assertEqual(len(install.call_args.args[0]), count)
                self.assertEqual(inspect.call_count, 2)
                self.assertLessEqual(inspect.call_args_list[0].args[1], time.monotonic()+180)

    def test_status_drift_aborts_before_download(self):
        before = {'blockers': [], 'missing': self.candidates, 'canonicalPresent': False,
                  'statusSnapshot': {'sha256': 'fixture'}}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=before), \
             mock.patch.object(r, 'require_status_unchanged', side_effect=ValueError('status changed')), \
             mock.patch.object(r, 'download') as fetch, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'status changed'):
                r.ensure({}, folder, time.monotonic()+180, True)
            fetch.assert_not_called()

    def test_status_drift_is_detected_by_full_bytes(self):
        with mock.patch.object(r, 'read_status', return_value=b'changed actual Depends'):
            with self.assertRaisesRegex(ValueError, 'status changed'):
                r.require_status_unchanged(hashlib.sha256(b'old').hexdigest())

    def test_transition_rejects_unapproved_version_change(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            a.write_bytes(self.status()); b.write_bytes(self.status().replace(b'Version: 1.7.0-1build1', b'Version: 99'))
            with self.assertRaisesRegex(ValueError, 'beyond reviewed'):
                r.verify_status_transition({'statusSnapshot': {'path': str(a)}}, {'statusSnapshot': {'path': str(b)}}, [])

    def test_existing_package_with_bad_owner_does_not_repair(self):
        row = self.candidates[-1]
        inventory = {(row['Package'], 'amd64'): dict(row, Status='install ok installed')}
        with mock.patch.object(r.graphics, 'trusted_installed'), \
             mock.patch.object(r, 'query', return_value=mock.Mock(returncode=0, stdout='someone-else: '+r.CANONICAL)):
            paths, blockers = r.verify_paths([row], inventory, time.monotonic()+120)
            self.assertFalse(paths)
            self.assertIn('no automatic repair/upgrade', blockers[0]['reason'])

    def test_bad_package_bytes_never_run_tools(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'query') as query:
            path = Path(folder)/'bad.deb'; path.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                r.verify_deb({'path': str(path), 'candidate': self.candidates[-1]}, time.monotonic()+120)
            query.assert_not_called()

    def test_redirect_rejected(self):
        with self.assertRaisesRegex(ValueError, 'redirected'):
            r.NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://example.org/package')

    def test_download_wrong_size_hash_never_writes(self):
        row = self.candidates[-1]
        response = io.BytesIO(b'wrong'); response.status = 200; response.url = row['url']
        opener = mock.Mock(); opener.open.return_value = response
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r.urllib.request, 'build_opener', return_value=opener):
            path = Path(folder)/'package.deb'
            with self.assertRaisesRegex(ValueError, 'size/hash mismatch'):
                r.download(row, path, time.monotonic()+120)
            self.assertFalse(path.exists())

    def test_same_size_wrong_hash_and_unexpected_final_url_rejected(self):
        row = dict(self.candidates[-1], Size='5', SHA256=hashlib.sha256(b'right').hexdigest())
        for url, expected in ((row['url'], 'size/hash mismatch'), ('https://example.org/package', 'official package response')):
            response = io.BytesIO(b'wrong'); response.status = 200; response.url = url
            opener = mock.Mock(); opener.open.return_value = response
            with self.subTest(url=url), tempfile.TemporaryDirectory() as folder, \
                 mock.patch.object(r.urllib.request, 'build_opener', return_value=opener):
                path = Path(folder)/'package.deb'
                with self.assertRaisesRegex(ValueError, expected):
                    r.download(row, path, time.monotonic()+120)
                self.assertFalse(path.exists())

    def test_wrong_dependency_control_metadata_stops_before_install(self):
        content = b'fixture only'
        row = copy.deepcopy(self.candidates[-1])
        row.update(Size=str(len(content)), SHA256=hashlib.sha256(content).hexdigest())
        control = dict(row['control'], Depends='unreviewed-dependency')
        metadata = '\n'.join(key+': '+value for key, value in control.items())+'\n'
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(r, 'query', return_value=mock.Mock(returncode=0, stdout=metadata)), \
             mock.patch.object(r.subprocess, 'Popen') as popen:
            path = Path(folder)/'fixture'; path.write_bytes(content)
            with self.assertRaisesRegex(ValueError, 'metadata mismatch.*Depends'):
                r.verify_deb({'path': str(path), 'candidate': row}, time.monotonic()+120)
            popen.assert_not_called()

    def exercise_install(self, interrupted=False):
        process = mock.Mock()
        process.wait.side_effect = [KeyboardInterrupt(), 0] if interrupted else None
        process.wait.return_value = 0
        downloads = [{'path': '/fixture/'+row['Package']+'.deb', 'candidate': row} for row in self.candidates]
        with mock.patch.object(r, 'verify_deb', return_value={}) as metadata, \
             mock.patch.object(r, 'require_status_unchanged'), \
             mock.patch.object(r.subprocess, 'Popen', return_value=process) as launch:
            if interrupted:
                with self.assertRaises(KeyboardInterrupt):
                    r.install_debs(downloads, time.monotonic()+120, 'fixture')
                self.assertEqual(process.wait.call_count, 2)
            else:
                result = r.install_debs(downloads, time.monotonic()+120, 'fixture')
                self.assertEqual(result['command'][:8], ['/usr/bin/sudo', '-n', '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s', '60s', '/usr/bin/dpkg', '--install'])
                self.assertEqual(result['command'][8:], [item['path'] for item in downloads])
                self.assertTrue(result['processReaped'])
                launch.assert_called_once()
                self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(metadata.call_count, 7)

    def test_one_install_command_owns_all_seven_and_root_timeout_group(self):
        self.exercise_install()

    def test_interruption_waits_for_owned_bounded_install(self):
        self.exercise_install(interrupted=True)

    def test_changed_or_eighth_package_rejected_before_command(self):
        changed = copy.deepcopy(self.candidates[-1]); changed['Version'] = '99'
        cases = [[{'path': '/fixture', 'candidate': changed}],
                 [{'path': '/fixture', 'candidate': row} for row in self.candidates] +
                 [{'path': '/extra', 'candidate': self.candidates[-1]}]]
        for rows in cases:
            with self.subTest(count=len(rows)), mock.patch.object(r.subprocess, 'Popen') as popen:
                with self.assertRaises(ValueError):
                    r.install_debs(rows, time.monotonic()+120, 'fixture')
                popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
