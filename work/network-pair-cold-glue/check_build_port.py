"""Focused Python-only contract tests; never invokes a JVM or a download."""
import ast
import copy
import importlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
from unittest import mock
import zipfile

import atexit
TEMPORARY = tempfile.TemporaryDirectory(prefix='coherent-build-source-')
atexit.register(TEMPORARY.cleanup)
ROOT = Path(TEMPORARY.name)
STAGE = Path(__file__).resolve().parents[2]
GLUE = STAGE / 'work/network-pair-cold-glue'
sys.path.insert(0, str(GLUE))
import build_candidate as build
import fml_metadata as fml
import pair_assembly as pair

checks = []
def check(name, callback):
    callback()
    checks.append(name)

def reject(callback):
    try:
        callback()
    except (ValueError, FileExistsError):
        return
    raise AssertionError('Expected fail-closed rejection')

def require(value):
    assert value

CONSUMER = ROOT / 'build-port-python-consumer'
import source_materialize
import runtime_restore
source_materialize.prepare(STAGE,CONSUMER)
runtime_restore.prepare(STAGE,CONSUMER)
build.prepare(CONSUMER)
pair.prepare(STAGE,CONSUMER)
check('all changed Python sources parse without execution', lambda: [ast.parse((GLUE / p).read_text()) for p in ('build_candidate.py','fml_metadata.py','pair_assembly.py')])
check('source support closure pins and preserved historical identity reference', lambda: require(fml.verify_sources(CONSUMER)['candidateIdentity'] == fml.CANDIDATE_IDENTITY))
check('prepare refuses replacing existing isolated source/output', lambda: reject(lambda: fml.prepare(CONSUMER)))
plan = build.plan(CONSUMER)
check('all three Gradle commands are offline strict serial bounded', lambda: [require(all(v in command for v in ['--offline','--no-parallel','--max-workers=1','--no-daemon','--dependency-verification=strict','-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8'])) for command in [plan['coreCommand'],plan['productCommandPrefix'],plan['fmlCommand']]])
check('PRODUCT reruns archive packing with exact historical payload permissions', lambda: require('--rerun-tasks' in plan['productCommandPrefix'] and any(p.endswith('product-payload-permissions.init.gradle') for p in plan['productCommandPrefix'])))
check('FML uses only isolated built-in Java project and bounded exact init', lambda: require(plan['fmlCommand'][-3:] == [str(CONSUMER/fml.PROJECT),'jar','sourcesJar'] and any(p.endswith('/fml/bounded-build.init.gradle') for p in plan['fmlCommand'])))
check('base and candidate identities and tuples remain distinct', lambda: require(plan['baseSourceIdentity'] != plan['expectedCandidateIdentity'] and build.BASE_EXPECTED['fml'] != build.EXPECTED['fml'] and all(build.BASE_EXPECTED[k] == build.EXPECTED[k] for k in ('service','game','product'))))
profile = pair.prepare_profile_helper(CONSUMER)
text = profile.read_text()
check('probe0.1.1 fixture derivative remains syntactically valid', lambda: ast.parse(text))
check('probe0.1.1 uses pinned manifest and exact filename', lambda: require(pair.compile_probe.SOURCE_SHA in text and pair.compile_probe.ARTIFACT_NAME in text and 'network-control-probe-0.1.0.jar' not in text))

with tempfile.TemporaryDirectory(prefix='fml-port-test-') as temporary:
    temporary = Path(temporary)
    def utf(text):
        data = text.encode('ascii')
        return struct.pack('>H', len(data)) + data
    cache = struct.pack('>i',1) + utf('converter') + struct.pack('>i',1) + utf('highlightforge') + utf('net.neoforged.fml.loading.log4j.ForgeHighlight') + utf('highlightForge') + b'\0\0'
    check('cache decoder verifies actual101-byte registration format', lambda: require(len(cache) == 101 and fml.decode_cache(cache) == fml.EXPECTED_PLUGIN))
    check('cache decoder rejects trailing bytes', lambda: reject(lambda: fml.decode_cache(cache + b'x')))
    def jar(path, files, different_mode=None):
        with zipfile.ZipFile(path,'w') as archive:
            for name, raw in files.items():
                info = zipfile.ZipInfo(name,(1980,1,1,0,0,0))
                info.external_attr=(0o644 if name != different_mode else 0o600) << 16
                archive.writestr(info,raw)
    payload = {'example/Class%d.class'%n: ('synthetic-class-%d'%n).encode() for n in range(309)}
    payload['META-INF/unified-admission/installation.json'] = b'{"schema":1,"approved":false}\n'
    old,new,official=temporary/'old.jar',temporary/'new.jar',temporary/'official.jar'
    jar(old,payload);jar(new,dict(payload,**{fml.CACHE:cache}));jar(official,{fml.CACHE:cache})
    check('archive comparison accepts only cache addition with309 unchanged classes', lambda: require(fml.compare_archives(old,new,official)['identicalClassCount'] == 309))
    changed=dict(payload,**{fml.CACHE:cache});changed['example/Class0.class']=b'changed';jar(new,changed)
    check('archive comparison rejects changed class payload', lambda: reject(lambda: fml.compare_archives(old,new,official)))
    changed=dict(payload,**{fml.CACHE:cache});jar(new,changed,different_mode='example/Class0.class')
    check('archive comparison rejects changed ZIP modes', lambda: reject(lambda: fml.compare_archives(old,new,official)))
    changed['foreign.txt']=b'extra';jar(new,changed)
    check('archive comparison rejects extra noncache resources', lambda: reject(lambda: fml.compare_archives(old,new,official)))
    changed.pop('foreign.txt');changed.pop('example/Class0.class');jar(new,changed)
    check('archive comparison rejects removed classes', lambda: reject(lambda: fml.compare_archives(old,new,official)))

source = CONSUMER/fml.PROJECT/'build.gradle'
original = source.read_bytes()
try:
    source.write_bytes(original+b'\n// changed\n')
    check('changed isolated FML build source rejected', lambda: reject(lambda: fml.verify_sources(CONSUMER)))
finally:
    source.write_bytes(original)

with mock.patch.object(build.bounded_process, 'run') as run:
    check('expired shared deadline prevents spawning a build', lambda: reject(lambda: build.command(CONSUMER, plan['fmlCommand'], 'test-expired', 600, time.monotonic()-1)))
    require(not run.called)

captured = {}
def fake_run(argv, **kwargs):
    captured.update(kwargs)
    kwargs['stdout'].write('mock source build; no JVM\n')
    return type('Result', (), {'returncode':0})()
with mock.patch.object(build.bounded_process, 'run', side_effect=fake_run):
    receipt=build.command(CONSUMER,plan['fmlCommand'],'fml-logging-v3',600,time.monotonic()+0.75)
check('build timeout consumes remaining shared deadline without extension', lambda: require(0 < captured['timeout'] <= 0.75))
check('build environment binds portable verified mirror roots', lambda: require(captured['env']['PAIR_API_ROOT'] == str(CONSUMER/'work/api1')))
check('FML compiler heap stays192MiB while all its JVMs use oneCPU', lambda: require(captured['env']['_JAVA_OPTIONS'] == '-XX:ActiveProcessorCount=1' and captured['env']['JAVA_OPTS'] == '-Xmx64m -XX:ActiveProcessorCount=1'))
with mock.patch.dict(os.environ, {'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'Nexa-MC/unified-infinity','GITHUB_REF':'refs/heads/diagnostic/unapproved-target'}):
    check('unapproved deployment branch cannot execute successor recipe', lambda: reject(lambda: build.execute(CONSUMER)))
result={'status':'PASS_PYTHON_SOURCE_AND_MOCK_CHECKS_ONLY','checks':len(checks),'tests':checks,'jvmStarted':False,'gameLaunched':False,'downloadsStarted':False}
print(json.dumps(result,indent=2))
