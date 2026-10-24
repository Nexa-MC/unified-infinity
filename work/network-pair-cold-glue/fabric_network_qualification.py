"""Bounded FFAPI-path qualification after an unchanged supervisor transport PASS.

A marker alone never authorizes acceptance. The caller supplies the retained
supervisor result/spec pins and the independently validated FFAPI build bundle.
No process launch, socket admission, permission change or supervisor edit occurs.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import stat
import types

import fabric_probe_overlay as binding

SUPERVISOR_SHA256 = '2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 512
MARKER = b'FABRIC_NETWORK_QUALIFICATION'
PREFIX = MARKER + b' '
KEYS = {'schema','role','pid','start_ticks','nonce','sequence','api','entrypoint','baseline_acceptance'}
ROLES = ('server','client')
require = binding.require


def decode(payload):
    def pairs(rows):
        result = {}
        for key,value in rows:
            require(key not in result, 'Duplicate qualification JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite qualification JSON')
    try:
        return json.loads(payload.decode('ascii'),object_pairs_hook=pairs,parse_constant=invalid)
    except (UnicodeError,ValueError,RecursionError,TypeError):
        raise ValueError('Malformed qualification JSON') from None


def _signature(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def stable_read(path, maximum):
    """Exact regular-file snapshot; no raw lines/errors returned on rejection."""
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path, 'Noncanonical qualification input')
    descriptor=None
    try:
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        before=os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and 1<=before.st_size<=maximum, 'Invalid/oversize qualification input')
        with os.fdopen(descriptor,'rb') as stream:
            descriptor=None
            payload=stream.read(maximum+1)
            after=os.fstat(stream.fileno())
        require(_signature(before)==_signature(after)==_signature(path.stat(follow_symlinks=False))
                and len(payload)==before.st_size, 'Qualification input changed while reading')
        return payload,{'path':str(path),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    except OSError:
        raise ValueError('Qualification input unavailable') from None
    finally:
        if descriptor is not None:os.close(descriptor)


def valid_marker(row):
    return (type(row) is dict and set(row)==KEYS
            and type(row['schema']) is int and row['schema']==1
            and type(row['sequence']) is int and row['sequence']==1
            and type(row['role']) is str and row['role'] in ROLES
            and type(row['pid']) is int and 1<=row['pid']<=2147483647
            and type(row['start_ticks']) is int and 1<=row['start_ticks']<=2**63-1
            and type(row['nonce']) is int and 1<=row['nonce']<=2**63-1
            and row['api']=='ffapi-play-v1' and row['entrypoint']=='fabric'
            and row['baseline_acceptance'] is False)


def extract(path, expected_sha256):
    require(type(expected_sha256) is str and binding.SHA.fullmatch(expected_sha256), 'Supervisor log hash required')
    payload,pin=stable_read(path,MAX_LOG_BYTES)
    require(pin['sha256']==expected_sha256, 'Log differs from supervisor terminal hash')
    found=[]
    for line in payload.splitlines(keepends=True):
        if MARKER not in line:continue
        require(line.startswith(PREFIX) and line.endswith(b'\n') and len(line)<=MAX_LINE_BYTES,
                'Malformed/oversize qualification marker line')
        row=decode(line[len(PREFIX):-1])
        require(valid_marker(row), 'Invalid qualification marker schema')
        found.append(row)
        require(len(found)==1, 'Duplicate qualification markers')
    require(len(found)==1, 'Missing qualification marker')
    return {'marker':found[0],'log_pin':pin}


def load_supervisor(path):
    path=Path(path).absolute()
    payload,pin=stable_read(path,1024*1024)
    require(pin['sha256']==SUPERVISOR_SHA256, 'Unchanged supervisor source required')
    # Execute the exact already hashed bytes, never an adjacent cached .pyc.
    module=types.ModuleType('ffapi_fixed_supervisor_validator');module.__file__=str(path)
    exec(compile(payload,str(path),'exec'),module.__dict__)
    require(stable_read(path,1024*1024)[1]==pin, 'Supervisor source changed during import')
    return module,pin


def validate(root, *, spec_pin, report_pin, verified_bundle, supervisor_path):
    """Only the Unified FFAPI-selected pair may qualify; baseline/QSL/Forge stay false."""
    root=binding.root_path(root)
    import fabric_probe_build_validation
    semantic=fabric_probe_build_validation.validate_bundle(root,
        {'bundle_pin':verified_bundle['bundle_pin'],'reviewed':verified_bundle['reviewed']})
    require(semantic['binding']==verified_bundle,'Qualification build binding changed')
    selected=binding.supervisor_binding(root,verified_bundle)
    evidence=[]
    def read_pin(row, maximum):
        path=binding.check(root,row)
        data,current=stable_read(path,maximum)
        require(current==dict(row,path=str(path)), 'Changed retained evidence pin')
        evidence.append((current,maximum))
        return decode(data)
    spec=read_pin(spec_pin,8*1024*1024)
    report=read_pin(report_pin,8*1024*1024)
    require(spec.get('schema')=='network-ci-pair-v2' and spec.get('target')=='unified'
            and type(spec.get('port')) is int and spec['port']==25632, 'Unified sealed pair required')
    for key in ('probe_path','probe_source_manifest','probe_build_receipt'):
        require(spec.get(key)==selected[key], 'Pair selected a different/native probe')
    require(type(spec.get('inputs')) is list, 'Missing complete pair inputs')
    pins={row['path']:row for row in spec['inputs']}
    require(len(pins)==len(spec['inputs']), 'Duplicate pair input pins')
    complete=[dict(row,path=str(binding.local(root,row['path']))) for row in semantic['inputPins']]
    require(all(pins.get(row['path'])==row for row in [*selected['inputs'],*complete]), 'FFAPI source/proof closure is not sealed')
    require(all(path in spec.get('source_receipts',[]) for path in selected['source_receipts']), 'FFAPI producer receipts not sealed')
    diagnostic=spec.get('diagnostic_profile')
    require(type(diagnostic) is dict and diagnostic.get('diagnostic_only') is True
            and diagnostic.get('baseline_acceptance') is False, 'Diagnostic-only sealed profile required')
    require(type(report.get('schema')) is int and report['schema']==1 and report.get('target')=='unified'
            and report.get('status')=='PASS' and report.get('passed') is True
            and report.get('phase')=='complete' and report.get('game_launched') is True
            and report.get('spec_sha256')==spec_pin['sha256']
            and report.get('pair_spec_unchanged') is True and report.get('immutable_inputs_unchanged') is True
            and report.get('diagnostic_only') is True and report.get('baseline_acceptance') is False
            and report.get('diagnostic_profile')==diagnostic, 'No matching completed diagnostic transport PASS')
    exits=report.get('exits')
    require(type(exits) is dict and set(exits)==set(ROLES)
            and all(type(exits[r]) is int and exits[r]==0 for r in ROLES), 'Both clean owned exits required')
    for key in ('identities','probe','log_sha256'):
        require(type(report.get(key)) is dict and set(report[key])==set(ROLES), 'Incomplete paired transport evidence')
    nonce=report.get('nonce')
    require(type(nonce) is int and 1<=nonce<=2**63-1, 'Exact transport nonce required')
    module,supervisor_pin=load_supervisor(supervisor_path)
    markers={}; identities={}
    destination=binding.local(root,report_pin['path']).parent
    for role in ROLES:
        identity=report['identities'][role]
        require(type(identity) is dict and type(identity.get('pid')) is int and 1<=identity['pid']<=2147483647
                and type(identity.get('start_ticks')) is int and 1<=identity['start_ticks']<=2**63-1
                and type(identity.get('pgrp')) is int and identity['pgrp']==identity['pid']
                and type(identity.get('session')) is int and identity['session']==identity['pid'], 'Invalid supervisor process identity')
        module.validate_probe(report['probe'][role],role,identity,nonce,25632)
        profile=binding.absolute(root,spec[role]['cwd'])
        probe_copy=str(profile/'mods'/binding.ARTIFACT_NAME)
        expected=dict(verified_bundle['bundle']['artifact'],path=probe_copy)
        require(pins.get(probe_copy)==expected
                and all(Path(p).name!=binding.LEGACY_NAME for p in
                        [*spec[role]['original_mods'],*spec[role]['managed_mods']]), 'Legacy/native emitter can satisfy this role')
        binding.check_absolute(root,expected)
        started_path=destination/(role+'-started.json')
        started_data,started_pin=stable_read(started_path,16384);evidence.append((started_pin,16384))
        started=decode(started_data)
        require(type(started) is dict and set(started)=={'role','identity'}
                and started['role']==role and started['identity']==identity, 'Spawn identity receipt changed')
        result_data,result_pin=stable_read(profile/('network-control-'+role+'-result.json'),2048)
        result=decode(result_data);module.validate_probe(result,role,identity,nonce,25632)
        require(result==report['probe'][role], 'Role result differs from supervisor PASS');evidence.append((result_pin,2048))
        capture=extract(destination/(role+'.log'),report['log_sha256'][role])
        row=capture['marker']
        require(row['role']==role and row['pid']==identity['pid'] and row['start_ticks']==identity['start_ticks']
                and row['nonce']==nonce, 'Qualification marker/process/nonce mismatch')
        markers[role]=row;identities[role]={'pid':identity['pid'],'start_ticks':identity['start_ticks']}
        evidence.append((capture['log_pin'],MAX_LOG_BYTES))
    require(identities['server']['pid']!=identities['client']['pid'], 'Distinct owned role processes required')
    # Pin the exact terminal evidence again after all cross-file checks.
    for row,maximum in evidence:
        require(stable_read(row['path'],maximum)[1]==row, 'Qualification evidence changed during validation')
    return {'schema':'fabric-ffapi-network-qualification-v1','status':'FFAPI_PATH_QUALIFIED_WITH_TRANSPORT_PASS',
            'target':'unified','diagnostic_only':True,'baseline_acceptance':False,
            'full_api_compatibility':False,'qsl_forge_facade_acceptance':False,
            'api':'ffapi-play-v1','entrypoint':'fabric','probe_bundle':verified_bundle['bundle_pin'],
            'spec':spec_pin,'supervisor_report':report_pin,'supervisor_source':supervisor_pin,
            'markers':markers,'identities':identities,'evidence':[row for row,_ in evidence]}
