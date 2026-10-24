"""Synthetic terminal-receipt fixtures only; no games/network/JVM acceptance."""
from pathlib import Path
import copy
import json
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import fabric_probe_overlay as b
import fabric_probe_build_validation as build
import fabric_network_qualification as q
import test_fabric_probe_overlay as fixtures


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.OverlayTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.root=f.root;self.verified=f.verified()
        # Only the upstream actual compilation boundary is mocked; marker,
        # transport identity, source binding and retained file validators run.
        self.semantic={'binding':self.verified,'inputPins':self.verified['inputs']}
        boundary=patch.object(build,'validate_bundle',return_value=self.semantic)
        boundary.start();self.addCleanup(boundary.stop)
        server=f.overlay/'unified/server';shutil.copytree(f.game,server)
        server_before=json.loads(json.dumps(f.before).replace(str(f.game),str(server)))
        server_baseline=self.root/'baseline/unified/server/mods'/b.LEGACY_NAME
        server_baseline.parent.mkdir(parents=True);server_baseline.write_bytes(f.baseline.read_bytes())
        self.client,_=f.stage()
        with patch.object(b,'LEGACY_SHA256',f.legacy_sha):
            self.server,_=b.stage_unified_probe(self.root,server_before,self.verified,target='unified',
                baseline_probe=b.absolute_pin(self.root,server_baseline),overlay_root=f.overlay)
        selected=b.supervisor_binding(self.root,self.verified)
        inputs={r['path']:r for r in [*selected['inputs'],*self.client['files'],*self.server['files']]}
        self.spec={'schema':'network-ci-pair-v2','target':'unified','port':25632,
                   **{k:selected[k] for k in ('probe_path','probe_source_manifest','probe_build_receipt')},
                   'inputs':list(inputs.values()),'source_receipts':selected['source_receipts'],
                   'diagnostic_profile':{'manifest_path':str(self.root/'synthetic-fml-manifest.json'),
                                         'manifest_sha256':'1'*64,'diagnostic_only':True,'baseline_acceptance':False},
                   'server':self.server,'client':self.client,'synthetic_fixture':True}
        self.spec_path=self.root/'pair-spec.json';f.save(self.spec_path,self.spec)
        self.evidence=self.root/'evidence';self.evidence.mkdir()
        self.report_path=self.evidence/'result.json'
        self.report={'schema':1,'target':'unified','status':'PASS','passed':True,'game_launched':True,'phase':'complete',
                     'spec_sha256':b.pin(self.root,self.spec_path)['sha256'],'pair_spec_unchanged':True,
                     'immutable_inputs_unchanged':True,'diagnostic_only':True,'baseline_acceptance':False,
                     'diagnostic_profile':self.spec['diagnostic_profile'],'exits':{'server':0,'client':0},
                     'nonce':2345,'identities':{},'probe':{},'log_sha256':{},'synthetic_fixture':True}
        self.markers={}
        for index,role in enumerate(q.ROLES):
            pid=12001+index;identity={'pid':pid,'start_ticks':900+index,'pgrp':pid,'session':pid}
            self.report['identities'][role]=identity
            self.report['probe'][role]={'schema':1,'role':role,'status':'PASS','nonce':2345,'sequence':1,'counter_before':0,'counter_after':1,
                'player_uuid':'dd29b97d-cafa-3d53-94e1-f85f75bcf1f6','player_name':'APILocal','port':25632,'pid':pid,'start_ticks':900+index,
                'main_thread':True,'loopback':True,'memory_connection':False,'dedicated_server':role=='server','remote_join':role=='client',
                'phase':'PLAY','flow':'SERVERBOUND' if role=='server' else 'CLIENTBOUND','code':'ok'}
            f.save(self.evidence/(role+'-started.json'),{'role':role,'identity':identity})
            f.save(Path(self.spec[role]['cwd'])/('network-control-'+role+'-result.json'),self.report['probe'][role])
            self.markers[role]={'schema':1,'role':role,'pid':pid,'start_ticks':900+index,'nonce':2345,'sequence':1,
                                'api':'ffapi-play-v1','entrypoint':'fabric','baseline_acceptance':False}
            self.write_log(role)
        self.save_report()
        self.supervisor=fixtures.supervisor_source()
    def write_log(self,role,payload=None):
        if payload is None:payload=q.PREFIX+b.canonical(self.markers[role])+b'\n'
        path=self.evidence/(role+'.log');path.write_bytes(payload)
        self.report['log_sha256'][role]=b.digest(payload)
    def save_report(self):self.fixture.save(self.report_path,self.report)
    def validate(self):
        return q.validate(self.root,spec_pin=b.pin(self.root,self.spec_path),report_pin=b.pin(self.root,self.report_path),
                          verified_bundle=self.verified,supervisor_path=self.supervisor)
    def test_both_role_qualification_requires_transport_and_binding(self):
        result=self.validate()
        self.assertEqual(result['status'],'FFAPI_PATH_QUALIFIED_WITH_TRANSPORT_PASS')
        self.assertFalse(result['baseline_acceptance']);self.assertFalse(result['full_api_compatibility'])
        self.assertFalse(result['qsl_forge_facade_acceptance']);self.assertEqual(result['markers'],self.markers)
    def test_marker_alone_cannot_qualify_failed_transport(self):
        self.report['status']='INCONCLUSIVE';self.report['passed']=False;self.save_report()
        with self.assertRaisesRegex(ValueError,'transport PASS'):self.validate()
    def test_missing_role_transport_refused(self):
        del self.report['probe']['client'];self.save_report()
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.validate()
    def test_native_transport_refused(self):
        self.report['target']='native-neoforge';self.save_report()
        with self.assertRaisesRegex(ValueError,'transport PASS'):self.validate()
    def test_old_native_probe_cannot_qualify_even_with_markers(self):
        self.spec['probe_path']=str(self.fixture.baseline);self.fixture.save(self.spec_path,self.spec)
        self.report['spec_sha256']=b.pin(self.root,self.spec_path)['sha256'];self.save_report()
        with self.assertRaisesRegex(ValueError,'different/native'):self.validate()
    def test_unsealed_source_binding_refused(self):
        self.spec['inputs']=self.spec['inputs'][1:];self.fixture.save(self.spec_path,self.spec)
        self.report['spec_sha256']=b.pin(self.root,self.spec_path)['sha256'];self.save_report()
        with self.assertRaisesRegex(ValueError,'not sealed'):self.validate()
    def test_complete_compiler_provenance_cannot_be_omitted(self):
        tool=self.root/'synthetic-compiler-input';tool.write_bytes(b'FIXTURE COMPILER INPUT')
        self.semantic['inputPins']=[*self.semantic['inputPins'],b.pin(self.root,tool)]
        with self.assertRaisesRegex(ValueError,'not sealed'):self.validate()
    def test_failed_semantic_build_recheck_cannot_qualify(self):
        with patch.object(build,'validate_bundle',side_effect=ValueError('changed actual build proof')):
            with self.assertRaisesRegex(ValueError,'changed actual build proof'):self.validate()
    def test_missing_marker_refused(self):
        self.write_log('client',b'unrelated harmless log\n');self.save_report()
        with self.assertRaisesRegex(ValueError,'Missing qualification'):self.validate()
    def test_duplicate_marker_refused(self):
        self.write_log('client',(q.PREFIX+b.canonical(self.markers['client'])+b'\n')*2);self.save_report()
        with self.assertRaisesRegex(ValueError,'Duplicate qualification'):self.validate()
    def test_malformed_json_refused_without_raw_echo(self):
        self.write_log('client',q.PREFIX+b'{Secret\n');self.save_report()
        with self.assertRaises(ValueError) as context:self.validate()
        self.assertNotIn('Secret',str(context.exception))
    def test_duplicate_json_key_refused(self):
        data=b.canonical(self.markers['client']);data=data[:-1]+b',"nonce":2345}'
        self.write_log('client',q.PREFIX+data+b'\n');self.save_report()
        with self.assertRaisesRegex(ValueError,'Malformed qualification JSON'):self.validate()
    def test_type_coercion_refused(self):
        self.markers['client']['schema']=True;self.write_log('client');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker schema'):self.validate()
    def test_nonce_mismatch_refused(self):
        self.markers['client']['nonce']=2346;self.write_log('client');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker/process/nonce'):self.validate()
    def test_process_identity_mismatch_refused(self):
        self.markers['server']['start_ticks']+=1;self.write_log('server');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker/process/nonce'):self.validate()
    def test_wrong_role_refused(self):
        self.markers['server']['role']='client';self.write_log('server');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker/process/nonce'):self.validate()
    def test_unknown_api_refused(self):
        self.markers['client']['api']='neoforge';self.write_log('client');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker schema'):self.validate()
    def test_unexpected_marker_field_refused(self):
        self.markers['client']['registered']=True;self.write_log('client');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker schema'):self.validate()
    def test_changed_log_refused(self):
        with (self.evidence/'client.log').open('ab') as stream:stream.write(b'changed\n')
        with self.assertRaisesRegex(ValueError,'terminal hash'):self.validate()
    def test_oversize_log_refused(self):
        self.write_log('client',b'x'*(q.MAX_LOG_BYTES+1));self.save_report()
        with self.assertRaisesRegex(ValueError,'oversize'):self.validate()
    def test_oversize_marker_line_refused(self):
        self.write_log('client',q.PREFIX+b' '*600+b'{}\n');self.save_report()
        with self.assertRaisesRegex(ValueError,'oversize qualification marker'):self.validate()
    def test_wrapped_logger_marker_refused(self):
        self.write_log('client',b'[logger] '+q.PREFIX+b.canonical(self.markers['client'])+b'\n');self.save_report()
        with self.assertRaisesRegex(ValueError,'marker line'):self.validate()
    def test_unterminated_marker_refused(self):
        self.write_log('client',q.PREFIX+b.canonical(self.markers['client']));self.save_report()
        with self.assertRaisesRegex(ValueError,'marker line'):self.validate()
    def test_result_file_mismatch_refused(self):
        result=copy.deepcopy(self.report['probe']['client']);result['nonce']+=1
        self.fixture.save(Path(self.client['cwd'])/'network-control-client-result.json',result)
        with self.assertRaisesRegex(ValueError,'mismatch'):self.validate()
    def test_spawn_identity_receipt_mismatch_refused(self):
        identity=dict(self.report['identities']['client'],start_ticks=444)
        self.fixture.save(self.evidence/'client-started.json',{'role':'client','identity':identity})
        with self.assertRaisesRegex(ValueError,'Spawn identity'):self.validate()
    def test_exit_bool_is_not_zero(self):
        self.report['exits']['client']=False;self.save_report()
        with self.assertRaisesRegex(ValueError,'clean owned exits'):self.validate()
    def test_same_process_cannot_supply_both_roles(self):
        identity=copy.deepcopy(self.report['identities']['server']);self.report['identities']['client']=identity
        for key in ('pid','start_ticks'):self.report['probe']['client'][key]=identity[key];self.markers['client'][key]=identity[key]
        self.fixture.save(self.evidence/'client-started.json',{'role':'client','identity':identity})
        self.fixture.save(Path(self.client['cwd'])/'network-control-client-result.json',self.report['probe']['client'])
        self.write_log('client');self.save_report()
        with self.assertRaisesRegex(ValueError,'Distinct owned'):self.validate()
    def test_midread_mutation_refused(self):
        real=q.os.fstat;calls=0
        def changed(fd):
            nonlocal calls
            value=real(fd);calls+=1
            if calls==2:
                return SimpleNamespace(**{name:getattr(value,name)+(1 if name=='st_mtime_ns' else 0)
                    for name in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode')})
            return value
        with patch.object(q.os,'fstat',changed),self.assertRaisesRegex(ValueError,'changed while reading'):
            q.extract(self.evidence/'client.log',self.report['log_sha256']['client'])
    def test_symlink_log_refused(self):
        path=self.evidence/'client.log';data=path.read_bytes();path.unlink();other=self.evidence/'other.log';other.write_bytes(data);path.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'Noncanonical'):self.validate()
    def test_supervisor_source_must_be_original(self):
        changed=self.root/'other-supervisor.py';changed.write_bytes(b'raise AssertionError("must not execute")')
        self.supervisor=changed
        with self.assertRaisesRegex(ValueError,'Unchanged supervisor'):self.validate()


if __name__=='__main__':unittest.main()
