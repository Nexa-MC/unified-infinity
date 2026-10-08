"""Source/mock contracts only: no download, package commands, GL, Java or game."""
import io
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import runner_dependencies as r


class RunnerSetupTests(unittest.TestCase):
    def before(self, present=False, blockers=None):
        return {'canonicalPresent': present, 'blockers': blockers or [],
                'package': {'installed': present, 'version': r.VERSION}}

    def test_canonical_package_path_and_full_dependency_set(self):
        self.assertEqual(r.graphics.REQUIRED['glxinfo'], r.CANONICAL)
        self.assertEqual(len(r.DEPENDENCIES), 12)
        self.assertEqual(r.DEPENDENCIES['libc6'], '2.38')
        self.assertEqual(r.DEPENDENCIES['libvulkan1'], '1.2.131.2')

    def test_existing_canonical_skips_download_and_install(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=self.before(True)), \
             mock.patch.object(r, 'download') as fetch, mock.patch.object(r, 'install_deb') as install:
            result = r.ensure({}, folder, time.monotonic()+120, True)
            self.assertEqual(result['status'], 'ALREADY_INSTALLED_NO_MUTATION')
            fetch.assert_not_called(); install.assert_not_called()

    def test_missing_requires_explicit_flag_and_emits_failure(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=self.before()), \
             mock.patch.object(r, 'download') as fetch:
            with self.assertRaisesRegex(ValueError, 'flag required'):
                r.ensure({}, folder, time.monotonic()+120)
            fetch.assert_not_called()
            self.assertEqual(json.loads((Path(folder)/'runner-dependencies.json').read_text())['status'], 'FAILED')

    def test_missing_dependencies_fail_before_download(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'inspect', return_value=self.before(blockers=[{'package':'libegl1'},{'package':'libgl1'}])), \
             mock.patch.object(r, 'download') as fetch:
            with self.assertRaisesRegex(ValueError, 'libegl1.*libgl1'):
                r.ensure({}, folder, time.monotonic()+120, True)
            fetch.assert_not_called()

    def test_wrong_runner_starts_no_package_commands(self):
        with mock.patch.object(r.graphics, 'availability', return_value={'missingInputs':[{'input':'runner'}]}), \
             mock.patch.object(r, 'query') as query:
            self.assertTrue(r.inspect({}, time.monotonic()+120)['blockers'])
            query.assert_not_called()

    def test_dependency_inventory_aggregates_all_twelve(self):
        available = {'runner': {}, 'missingInputs':[{'path':r.CANONICAL}]}
        with mock.patch.object(r.graphics, 'availability', return_value=available), \
             mock.patch.object(r.graphics, 'trusted_installed'), \
             mock.patch.object(r, 'installed', side_effect=lambda name, deadline: {'package':name,'installed':False}):
            result = r.inspect({}, time.monotonic()+120)
            self.assertEqual(len(result['dependencies']), 12)
            self.assertEqual(len(result['installedPrerequisites']), 4)
            self.assertEqual(len(result['blockers']), 16)

    def test_installed_but_missing_file_does_not_reinstall(self):
        available = {'runner': {}, 'missingInputs':[{'path':r.CANONICAL}]}
        with mock.patch.object(r.graphics, 'availability', return_value=available), \
             mock.patch.object(r.graphics, 'trusted_installed'), \
             mock.patch.object(r, 'installed', side_effect=lambda name, deadline: {'package':name,'installed':True,'architecture':'amd64','version':'99'}), \
             mock.patch.object(r, 'query', return_value=mock.Mock(returncode=0)):
            result = r.inspect({}, time.monotonic()+120)
            self.assertIn('no automatic repair/upgrade', result['blockers'][0]['reason'])

    def test_bad_package_bytes_never_run_tools(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r, 'query') as query, \
             mock.patch.object(r.subprocess, 'Popen') as popen:
            path=Path(folder)/'bad.deb'; path.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                r.install_deb(path, time.monotonic()+120)
            query.assert_not_called(); popen.assert_not_called()

    def test_redirect_rejected(self):
        with self.assertRaisesRegex(ValueError, 'redirected'):
            r.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://example.org/package')

    def test_download_wrong_size_hash_never_writes(self):
        response=io.BytesIO(b'wrong'); response.status=200; response.url=r.URL
        opener=mock.Mock(); opener.open.return_value=response
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(r.urllib.request, 'build_opener', return_value=opener):
            path=Path(folder)/'package.deb'
            with self.assertRaisesRegex(ValueError, 'size/hash mismatch'):
                r.download(path,time.monotonic()+120)
            self.assertFalse(path.exists())

    def exercise_install(self, interrupted=False, metadata=''):
        content=b'fixture only, not an installable package'
        process=mock.Mock()
        process.wait.side_effect=[KeyboardInterrupt(),0] if interrupted else None
        process.wait.return_value=0
        meta=metadata or 'Package: mesa-utils-bin\nVersion: 9.0.0-2\nArchitecture: amd64\n'
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(r,'SIZE',len(content)), \
             mock.patch.object(r,'SHA256',hashlib.sha256(content).hexdigest()), \
             mock.patch.object(r,'query',return_value=mock.Mock(returncode=0,stdout=meta)), \
             mock.patch.object(r.subprocess,'Popen',return_value=process) as launch:
            path=Path(folder)/'fixture';path.write_bytes(content)
            if interrupted:
                with self.assertRaises(KeyboardInterrupt):
                    r.install_deb(path,time.monotonic()+120)
                self.assertEqual(process.wait.call_count,2)
            elif metadata:
                with self.assertRaisesRegex(ValueError,'metadata mismatch'):
                    r.install_deb(path,time.monotonic()+120)
                launch.assert_not_called()
            else:
                result=r.install_deb(path,time.monotonic()+120)
                self.assertEqual(result['command'][:7],['/usr/bin/sudo','-n','/usr/bin/timeout','--signal=TERM','--kill-after=5s','60s','/usr/bin/dpkg'])
                self.assertEqual(result['command'][7:],[ '--install',str(path)])
                self.assertTrue(result['processReaped'])

    def test_install_command_has_privileged_timeout_and_no_resolver(self):
        self.exercise_install()

    def test_interruption_waits_for_owned_bounded_install(self):
        self.exercise_install(interrupted=True)

    def test_wrong_deb_metadata_stops_before_privileged_command(self):
        self.exercise_install(metadata='Package: unexpected\n')


if __name__ == '__main__':
    unittest.main()
