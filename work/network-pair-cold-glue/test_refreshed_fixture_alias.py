"""Exercise real alias hashing/copy and refreshed call ordering on synthetic bytes.

No JVM, fixture compilation, full-build proof or runtime acceptance is produced.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import build_candidate as build
import refreshed_candidate as refresh
import forge_fixture as fixture

class ReachedInputVerification(Exception):
    pass

class RefreshedFixtureAliasTests(unittest.TestCase):
    def attempt(self, existing=None, corrupt_source=False):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root=Path(folder);api=root/'work/api1'
            clean=b'synthetic exact clean input\n';digest=hashlib.sha256(clean).hexdigest()
            source=api/fixture.CLEAN_SOURCE;source.parent.mkdir(parents=True);source.write_bytes(b'wrong source' if corrupt_source else clean)
            destination=api/fixture.CLEAN_DESTINATION
            if existing is not None:
                destination.parent.mkdir(parents=True);destination.write_bytes(existing)
            server=api/'run/neoforge-native/libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar'
            server.parent.mkdir(parents=True);server.write_bytes(b'server fixture')
            plan=root/refresh.OUTPUT/'plan.json';plan.parent.mkdir(parents=True)
            plan.write_text(json.dumps({'profileSha256':refresh.PROFILE_SHA256,'profilePath':refresh.PROFILE_PATH,'recipe':{},'inputsBinding':'synthetic-binding'}))
            stack.enter_context(mock.patch.dict(build.os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'Nexa-MC/unified-infinity','GITHUB_REF':'refs/heads/diagnostic/network-pair-20261006-a'},clear=True))
            stack.enter_context(mock.patch.object(refresh,'load_profile',return_value={}))
            stack.enter_context(mock.patch.object(refresh,'inputs_binding',return_value='synthetic-binding'))
            stack.enter_context(mock.patch.object(build,'plan',return_value={}))
            stack.enter_context(mock.patch.object(build,'ORIGINALS',{}))
            stack.enter_context(mock.patch.object(build,'EXTRA',hashlib.sha256(b'server fixture').hexdigest()))
            stack.enter_context(mock.patch.object(build.fml_metadata,'verify_sources'))
            stack.enter_context(mock.patch.object(build.fml_metadata,'verify_dependencies'))
            stack.enter_context(mock.patch.object(fixture,'CLEAN_SHA',digest))
            stack.enter_context(mock.patch.object(fixture,'CLEAN_BYTES',len(clean)))
            process=stack.enter_context(mock.patch.object(build.bounded_process,'run',side_effect=AssertionError('No process permitted')))
            def verify(actual_root):
                self.assertEqual(actual_root,root)
                self.assertEqual(destination.read_bytes(),clean)
                self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(),digest)
                raise ReachedInputVerification('stop before any build')
            verifier=stack.enter_context(mock.patch.object(fixture,'verify_inputs',side_effect=verify))
            if corrupt_source or (existing is not None and existing!=clean):
                with self.assertRaisesRegex(ValueError,'clean Minecraft.*differs'):
                    build.execute_refreshed(root,refresh.PROFILE_PATH,deadline=999999999999)
                verifier.assert_not_called()
                if existing is not None:self.assertEqual(destination.read_bytes(),existing)
                else:self.assertFalse(destination.exists())
            else:
                with self.assertRaises(ReachedInputVerification):
                    build.execute_refreshed(root,refresh.PROFILE_PATH,deadline=999999999999)
                verifier.assert_called_once_with(root)
            process.assert_not_called()
            self.assertFalse((root/refresh.OUTPUT/'session.json').exists())
            self.assertFalse((root/refresh.PROOF_PATH).exists())
            self.assertEqual(source.read_bytes(),b'wrong source' if corrupt_source else clean)

    def test_missing_alias_materialized_before_input_verification(self):self.attempt()
    def test_exact_existing_alias_is_retained(self):self.attempt(existing=b'synthetic exact clean input\n')
    def test_wrong_existing_alias_rejected_without_overwrite(self):self.attempt(existing=b'wrong existing alias')
    def test_wrong_generated_source_rejected_before_copy_or_verification(self):self.attempt(corrupt_source=True)

if __name__=='__main__':unittest.main()
