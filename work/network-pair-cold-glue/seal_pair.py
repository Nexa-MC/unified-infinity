"""Small consumer-path adapter to the reviewed input-base/finalizer functions."""
import importlib.util
import hashlib
import json
from pathlib import Path
from compile_probe import require, sha, record, save, SOURCE_RELATIVE, OUTPUT_RELATIVE

SUPERVISOR_SHA='56237acb33a70e7f24927a0ad3acdc1ba9fb788e933e776a3643d379103691c0'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def seal_indigo_baseline(target, roles, inputs, out):
    """Retain the exact prestart Indigo bytes outside the live config tree."""
    if target != 'unified':
        return None
    original = Path(roles['client']['cwd']) / 'config/fabric/indigo-renderer.properties'
    expected = {'path': str(original), 'bytes': 281,
                'sha256': '6ccd84c116ad3a0d4277413074cc5b71ac6e5027ea45aa298a21e0b145b25d9b'}
    require(inputs.get(str(original)) == expected, 'Exact original Indigo role pin required')
    require(original.resolve() == original and not original.is_symlink() and record(original) == expected,
            'Original Indigo configuration changed before baseline capture')
    before = original.read_bytes()
    require(len(before) == expected['bytes'] and hashlib.sha256(before).hexdigest() == expected['sha256'],
            'Original Indigo configuration changed during baseline capture')
    baseline = Path(out) / 'indigo-baseline.properties'
    require(baseline.resolve() == baseline and not baseline.is_symlink(), 'Redirected Indigo baseline')
    if baseline.exists():
        require(baseline.is_file() and baseline.read_bytes() == before, 'Existing Indigo baseline changed')
    else:
        with baseline.open('xb') as stream:
            stream.write(before)
    row = record(baseline)
    require(row == dict(expected, path=str(baseline)), 'Indigo baseline differs from original role pin')
    inputs[row['path']] = row
    return row


def create(repo,consumer,target,graphics_ready,review_reference):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).resolve(strict=True);api=consumer/'work/api1'
    require(target in ('native-neoforge','unified'),'Unknown pair target')
    assembly_path=consumer/'work/network-pair-cold-assembly/pair-assembly-result.json'
    assembly=json.loads(assembly_path.read_text());require(assembly['status']=='COLD_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN','Actual cold assembly required')
    group=assembly['groups'][target];inputs={};trees={str(api/'run/client-dev/assets')};roles={}
    def add(path):
        row=record(Path(path));inputs[row['path']]=row;return row
    producer=add(assembly_path)
    probe_base=consumer/OUTPUT_RELATIVE;build=json.loads((probe_base/'probe-build-binding.json').read_text())
    source=consumer/SOURCE_RELATIVE;manifest=json.loads((source/'source-manifest.json').read_text())
    for row in manifest['files']:
        current=add(source/row['path']);require(current['sha256']==row['sha256'] and current['bytes']==row['bytes'],'Probe source/resource changed')
    for path in [source/'source-manifest.json',probe_base/'probe-build-binding.json',probe_base/'result.json',Path(build['artifact_path'])]:add(path)
    helper_path=repo/'work/network-pair-finalizer/prepare_inputs.py'
    source_seal=json.loads((helper_path.parent/'source-manifest.json').read_text())
    expected=next(r for r in source_seal['files'] if r['path']=='prepare_inputs.py')
    require(sha(helper_path)==expected['sha256'],'Reviewed JDK comparison helper changed')
    helper=module('cold_jdk_byte_comparison',helper_path)
    helper.JDK=api/'.toolchains/jdk-21.0.12.1+1';helper.JDK_ARCHIVE=api/'.toolchains/jdk21.tar.gz'
    jdk_files,links,jdk_result=helper.jdk_closure();trees.add(str(helper.JDK))
    for row in jdk_files:inputs[row['path']]=row
    for path in (api/'run/client-dev/assets').rglob('*'):
        if path.is_file():add(path)
    producers=[producer['path'],str(probe_base/'result.json')]
    for side,pin in group['roles'].items():
        rolepath=Path(pin['path']);require(sha(rolepath)==pin['sha256'],'Cold role seal changed');add(rolepath);producers.append(str(rolepath))
        role=json.loads(rolepath.read_text());cwd=Path(role['cwd'])
        for row in role['files']:
            if row['path']==str(cwd/'options.txt'):continue
            current=add(Path(row['path']));require(current==row,'Cold role input changed')
        for name in ('mods','config','defaultconfigs','installation','libraries'):
            if (cwd/name).is_dir():trees.add(str(cwd/name))
        env={'JAVA_HOME':str(helper.JDK),'PATH':str(helper.JDK/'bin')+':/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','LIBGL_ALWAYS_SOFTWARE':'true','GALLIUM_DRIVER':'llvmpipe'}
        for key,value in [('HOME','.launch-home'),('XDG_CACHE_HOME','.launch-cache'),('XDG_CONFIG_HOME','.launch-config'),('XDG_DATA_HOME','.launch-data'),('TMPDIR','.launch-tmp')]:env[key]=str(cwd/value)
        roles[side]={'cwd':str(cwd),'command':role['command'],'environment':env,'original_mods':role['original_mods'],'managed_mods':role['managed_mods']}
    out=api/'ci/pair-seals';out.mkdir(parents=True,exist_ok=True)
    seal_indigo_baseline(target,roles,inputs,out)
    base={'schema':'prepared-network-ci-pair-v2','status':'NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE','target':target,'port':group['port'],
          'preparation_roots':[str(consumer)],'jdk_legal_links':links,'inputs':list(inputs.values()),'immutable_trees':sorted(trees),
          'probe_path':build['artifact_path'],'probe_source_manifest':str(source/'source-manifest.json'),'probe_build_receipt':str(probe_base/'probe-build-binding.json'),
          'source_receipts':producers,'pair_lock':str(out/'serial-pair.lock'),'server':roles['server'],'client':roles['client'],
          'authorization':{'offline_identity_reference':'Isolated localhost tests with virtual APILocal identity','eula_reference':'Existing Minecraft EULA acceptance for isolated local tests'}}
    import sys
    sys.path.insert(0,str(repo/'work/network-pair-finalizer'))
    finalizer=module('cold_pair_finalizer',repo/'work/network-pair-finalizer/finalize_pair.py')
    ready_path=Path(graphics_ready);ready=json.loads(ready_path.read_text())
    spec=finalizer.bind(base,ready,record(ready_path),review_reference)
    supervisor=repo/'work/network-ci-supervisor-portable3/supervisor.py';require(sha(supervisor)==SUPERVISOR_SHA,'Final supervisor changed')
    s=module('cold_pair_supervisor',supervisor);s.verify_spec(spec);s.verify_graphics(spec,s.Proc())
    path=out/(target+'.json');save(path,spec)
    return {'spec':record(path),'supervisor':record(supervisor),'jdkComparison':jdk_result,'gameLaunched':False}
