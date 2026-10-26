"""Future approved CI call-in: one fresh root, serial runtime -> core -> probes.

No workflow dispatch or standalone unanchored CLI. The next fixed-round workflow
must validate its first-step anchor before calling execute with the resulting
absolute monotonic work deadline, leaving its existing cleanup reserve intact.
"""
from pathlib import Path
import importlib.util,json,os,sys,time
import same_root as sr
ORIGINAL_STAGE_MANIFEST='fcb9423fbb73b52b3d7e2826611707c4ad48f7185f7019f3d9aa2260242b2708'

def execute(repo,consumer,deadline,source_manifest_sha256):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).absolute()
    sr.require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='Nexa-MC/unified-infinity' and os.environ.get('GITHUB_REF')=='refs/heads/diagnostic/network-pair-20261006-a' and os.environ.get('GITHUB_JOB')=='serial-pair' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','Existing first-attempt authorized CI only')
    sr.require(60<deadline-time.monotonic()<=38*60,'Previously anchored bounded work deadline required')
    sr.require(sr.sha(sr.HERE/'input-manifest.json')==source_manifest_sha256,'Reviewed next-stage manifest required')
    # Reuse exact original restoration/compilation support, never a substitute lock.
    stage=sr.module('original_forge_compile_stage',repo/'work/forge-play-compile-ci/run.py')
    stage.validate_source(repo,ORIGINAL_STAGE_MANIFEST)
    sr.require(not consumer.exists() and consumer.is_absolute() and consumer.resolve()==consumer and not consumer.is_relative_to(repo),'Fresh external consumer required')
    sys.path.insert(0,str(repo/'work/network-pair-cold-glue'))
    sys.path.insert(0,str(repo/'work/forge-play-compile-ci/support'))
    import ffapi_sources,runtime_restore
    ffapi_sources.prepare(repo,consumer);plan=runtime_restore.prepare(repo,consumer)
    api=consumer/'work/api1';evidence=consumer/'official-runtime-evidence';evidence.mkdir()
    # Exact baseline verification precedes an explicit immutable derivative proof.
    sr.prepare(repo,consumer)
    strict=sr.module('consumer_strict_runtime_restore',consumer/'work/forge-same-root/strict_runtime_restore.py')
    strict.restore(api,runtime_restore,deadline)
    restored=strict.restore_forge(consumer,stage.forge_records(),deadline)
    sr.write(consumer/'evidence/original-forge-restoration.json',restored)
    for step in plan['steps']:
        stage.run_step(step['command'],step['cwd'],step['environment'],evidence,step['name'],deadline,step['timeoutSeconds'])
    verified=runtime_restore.verify(api);sr.write(consumer/'evidence/original-runtime-verification.json',verified)
    # From here every producer/consumer source and helper is inside this root.
    local=sr.module('consumer_same_root',consumer/'work/forge-same-root/same_root.py')
    restore=sr.module('consumer_core_restore',consumer/'work/forge-same-root/restore_core_inputs.py')
    sr.write(consumer/'evidence/core-inputs.json',restore.restore(repo,consumer,deadline))
    producer=local.compile_core(consumer,deadline)
    result=local.build_probes(consumer,producer,deadline)
    runtime_restore.verify_inputs(api);stage.validate_source(repo,ORIGINAL_STAGE_MANIFEST)
    sr.require(sr.sha(sr.HERE/'input-manifest.json')==source_manifest_sha256,'Stage manifest changed after execution')
    return result
