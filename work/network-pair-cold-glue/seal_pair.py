"""Small consumer-path adapter to the reviewed input-base/finalizer functions."""
import importlib.util
import hashlib
import json
from pathlib import Path
from compile_probe import require, sha, record, save, SOURCE_RELATIVE, OUTPUT_RELATIVE

SUPERVISOR_SHA='2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'

def refreshed_assembly(consumer,profile,build_proof):
    """Revalidate full proof and bind its closure before any final seal exists.

    Observed-tuple preparations and historical pair receipts are not accepted.
    Returned rows are absolute finalizer pins, checked against the shared
    verifier's portable proof closure, not new acceptance claims.
    """
    require(profile is not None and build_proof is not None,
            'Refreshed seals require both profile and build proof')
    import refreshed_candidate as refreshed
    import pair_assembly
    root=Path(consumer)
    verified=refreshed.validate_full_build(root,profile,build_proof)
    require(verified['runtimeAcceptance'] is False and
            verified['candidateIdentity']==verified['profileSha256'] and
            verified['candidateIdentityKind']=='verified-refreshed-build-profile',
            'Full refreshed build proof must not claim runtime acceptance')
    path=refreshed.local(root,pair_assembly.REFRESHED_SUPPORT+'/pair-assembly-result.json')
    assembly=json.loads(path.read_text())
    require(assembly['status']=='REFRESHED_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN' and
            assembly['consumerRoot']==str(root) and assembly['roleCount']==4 and
            assembly['profile']==refreshed.pin(root,profile) and
            assembly['buildProof']==refreshed.pin(root,build_proof) and
            assembly['profileSha256']==verified['profileSha256'] and
            assembly['baseSourceIdentity']==verified['sourceIdentity'] and
            assembly['candidateIdentity']==verified['candidateIdentity'] and
            assembly['candidateIdentityKind']==verified['candidateIdentityKind'] and
            assembly['historicalBaseSourceIdentityPreserved']==pair_assembly.IDENTITY and
            assembly['jvmStarted'] is False and assembly['gameLaunched'] is False and
            assembly['networkAcceptance'] is False and assembly['runtimeAcceptance'] is False,
            'Actual profile-bound refreshed assembly required')
    require(assembly['probeVersion']=='0.1.1' and
            assembly['probeSha256']==pair_assembly.compile_probe.REFERENCE_JAR_SHA,
            'Refreshed assembly must preserve the exact probe')
    inputs={}
    def add_portable(row):
        current=record(refreshed.check_pin(root,row))
        require(current['path'] not in inputs or inputs[current['path']]==current,
                'Conflicting refreshed closure pin')
        inputs[current['path']]=current
        return current
    def add_absolute(row):
        absolute=Path(row['path'])
        require(absolute.is_absolute() and absolute.is_relative_to(root),
                'Refreshed assembly input leaves consumer')
        current=add_portable(dict(row,path=absolute.relative_to(root).as_posix()))
        require(current==row,'Changed refreshed assembly pin')
        return current
    require(verified.get('inputPins'),'Complete refreshed proof closure required')
    for row in verified['inputPins']:add_portable(row)
    add_portable(refreshed.pin(root,profile));add_portable(refreshed.pin(root,build_proof))
    out=Path(assembly['assemblyRoot'])
    require(out.is_absolute() and out.is_relative_to(root) and out!=root,
            'Refreshed assembly output leaves consumer')
    require(refreshed.local(root,out.relative_to(root).as_posix())==out,
            'Noncanonical refreshed assembly root')
    for relative in (pair_assembly.SUPPORT,pair_assembly.PROFILES,pair_assembly.ASSEMBLED):
        historical=root/relative
        require(not out.is_relative_to(historical) and not historical.is_relative_to(out),
                'Refreshed assembly overlaps historical output')
    require(assembly['assemblyResult']['path']==str(out/'assembly-result.json'),
            'Refreshed assembly result belongs elsewhere')
    add_absolute(assembly['assemblyResult'])
    assembled=json.loads((out/'assembly-result.json').read_text())
    require(assembled['status']=='SOURCE_ASSEMBLED_GAME_UNRUN' and
            assembled['gameLaunched'] is False and assembled['jvmStarted'] is False and
            assembled['groups']==assembly['groups'], 'Refreshed assembly result changed')
    require(set(assembly['groups'])=={'native-neoforge','unified'} and
            set(assembly['profiles'])==set(assembly['groups']), 'Missing refreshed paired group')
    for target,group in assembly['groups'].items():
        require(group['port']==(25631 if target=='native-neoforge' else 25632) and
                set(group['roles'])=={'server','client'},'Refreshed pair roles/port changed')
        fixture=root/pair_assembly.REFRESHED_PROFILES/target/'profile-preparation.json'
        require(assembly['profiles'][target]['path']==str(fixture) and
                group['sourceFixture']==assembly['profiles'][target], 'Refreshed fixture belongs elsewhere')
        add_absolute(assembly['profiles'][target])
        for side,row in group['roles'].items():
            require(row['path']==str(out/target/(side+'-launch-seal.json')),
                    'Refreshed role seal belongs elsewhere')
            add_absolute(row)
    for key,name in (('inputLock','input-lock.json'),('derivation','derivation.json')):
        require(assembly[key]['path']==str(root/pair_assembly.REFRESHED_SUPPORT/name),
                'Refreshed '+key+' belongs elsewhere')
        add_absolute(assembly[key])
    lock=json.loads(Path(assembly['inputLock']['path']).read_text())
    for row in lock['files']:add_portable(row)
    derivation=json.loads(Path(assembly['derivation']['path']).read_text())
    require(derivation['inputLock']==assembly['inputLock'] and
            derivation['source']['sha256']==pair_assembly.SOURCE_PINS['assemble_pairs.py'],
            'Frozen refreshed assembly derivation changed')
    for key in ('source','derivative','sourcePreparation'):add_absolute(derivation[key])
    return path,assembly,list(inputs.values()),out


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


def create(repo,consumer,target,graphics_ready,review_reference,*,profile=None,build_proof=None,diagnostic_manifest=None,ffapi_probe_bundle=None):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).resolve(strict=True);api=consumer/'work/api1'
    require(target in ('native-neoforge','unified'),'Unknown pair target')
    refreshed=profile is not None or build_proof is not None
    diagnostic=diagnostic_manifest is not None
    require(not diagnostic or refreshed,'Diagnostic seals require full refreshed build ancestry')
    require(ffapi_probe_bundle is None or diagnostic,'FFAPI probe requires an explicit diagnostic profile')
    if diagnostic:
        import diagnostic_pair_assembly
        assembly_path,assembly,proof_inputs,assembly_root=diagnostic_pair_assembly.validate(
            repo,consumer,Path(diagnostic_manifest),profile=profile,build_proof=build_proof,
            **({'ffapi_probe_bundle':ffapi_probe_bundle} if ffapi_probe_bundle is not None else {}))
    elif refreshed:
        assembly_path,assembly,proof_inputs,assembly_root=refreshed_assembly(consumer,profile,build_proof)
    else:
        assembly_path=consumer/'work/network-pair-cold-assembly/pair-assembly-result.json'
        assembly=json.loads(assembly_path.read_text());require(assembly['status']=='COLD_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN','Actual cold assembly required')
    group=assembly['groups'][target];inputs={};trees={str(api/'run/client-dev/assets')};roles={}
    def add(path):
        row=record(Path(path));inputs[row['path']]=row;return row
    producer=add(assembly_path)
    if refreshed:
        for row in proof_inputs:
            require(add(Path(row['path']))==row,'Refreshed proof input changed before sealing')
    if ffapi_probe_bundle is not None and target=='unified':
        import fabric_probe_build_validation as ffapi_build
        import fabric_probe_overlay as ffapi_overlay
        validated=ffapi_build.validate_bundle(consumer,ffapi_probe_bundle)
        selected=ffapi_overlay.supervisor_binding(consumer,validated['binding'])
        for row in validated['inputPins']:
            path=consumer/row['path']
            require(add(path)==dict(row,path=str(path)),'FFAPI build/source/remap input changed before sealing')
        probe_path=selected['probe_path'];probe_source_manifest=selected['probe_source_manifest']
        probe_build_receipt=selected['probe_build_receipt'];probe_producers=selected['source_receipts']
    else:
        probe_base=consumer/OUTPUT_RELATIVE;build=json.loads((probe_base/'probe-build-binding.json').read_text())
        source=consumer/SOURCE_RELATIVE;manifest=json.loads((source/'source-manifest.json').read_text())
        for row in manifest['files']:
            current=add(source/row['path']);require(current['sha256']==row['sha256'] and current['bytes']==row['bytes'],'Probe source/resource changed')
        for path in [source/'source-manifest.json',probe_base/'probe-build-binding.json',probe_base/'result.json',Path(build['artifact_path'])]:add(path)
        probe_path=build['artifact_path'];probe_source_manifest=str(source/'source-manifest.json')
        probe_build_receipt=str(probe_base/'probe-build-binding.json');probe_producers=[str(probe_base/'result.json')]
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
    producers=[producer['path'],*probe_producers]
    for side,pin in group['roles'].items():
        rolepath=Path(pin['path']);require(sha(rolepath)==pin['sha256'],'Cold role seal changed');add(rolepath);producers.append(str(rolepath))
        role=json.loads(rolepath.read_text());cwd=Path(role['cwd'])
        if refreshed:require(cwd==assembly_root/target/side,'Refreshed role working directory belongs elsewhere')
        for row in role['files']:
            if row['path']==str(cwd/'options.txt'):continue
            current=add(Path(row['path']));require(current==row,'Cold role input changed')
        for name in ('mods','config','defaultconfigs','installation','libraries'):
            if (cwd/name).is_dir():trees.add(str(cwd/name))
        env={'JAVA_HOME':str(helper.JDK),'PATH':str(helper.JDK/'bin')+':/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','LIBGL_ALWAYS_SOFTWARE':'true','GALLIUM_DRIVER':'llvmpipe'}
        for key,value in [('HOME','.launch-home'),('XDG_CACHE_HOME','.launch-cache'),('XDG_CONFIG_HOME','.launch-config'),('XDG_DATA_HOME','.launch-data'),('TMPDIR','.launch-tmp')]:env[key]=str(cwd/value)
        roles[side]={'cwd':str(cwd),'command':role['command'],'environment':env,'original_mods':role['original_mods'],'managed_mods':role['managed_mods']}
    out=api/('ci/pair-seals-refreshed' if refreshed else 'ci/pair-seals')
    if diagnostic:out=api/'ci/pair-seals-process-diagnostic'
    if ffapi_probe_bundle is not None:out=api/'ci/pair-seals-fabric-ffapi-diagnostic'
    out.mkdir(parents=True,exist_ok=True)
    # Both opt-in and historical specs share the original serialization lock.
    # The frozen supervisor also locates the exact Indigo baseline beside it.
    serial=api/'ci/pair-seals';serial.mkdir(parents=True,exist_ok=True)
    seal_indigo_baseline(target,roles,inputs,serial)
    base={'schema':'prepared-network-ci-pair-v2','status':'NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE','target':target,'port':group['port'],
          'preparation_roots':[str(consumer)],'jdk_legal_links':links,'inputs':list(inputs.values()),'immutable_trees':sorted(trees),
          'probe_path':probe_path,'probe_source_manifest':probe_source_manifest,'probe_build_receipt':probe_build_receipt,
          'source_receipts':producers,'pair_lock':str(serial/'serial-pair.lock'),'server':roles['server'],'client':roles['client'],
          'authorization':{'offline_identity_reference':'Isolated localhost tests with virtual APILocal identity','eula_reference':'Existing Minecraft EULA acceptance for isolated local tests'}}
    if diagnostic:
        manifest_pin=record(Path(diagnostic_manifest))
        require(inputs.get(manifest_pin['path'])==manifest_pin,'Diagnostic manifest missing from complete seal inputs')
        base['diagnostic_profile']={'manifest_path':manifest_pin['path'],'manifest_sha256':manifest_pin['sha256'],
                                    'diagnostic_only':True,'baseline_acceptance':False}
    import sys
    sys.path.insert(0,str(repo/'work/network-pair-finalizer'))
    finalizer=module('cold_pair_finalizer',repo/'work/network-pair-finalizer/finalize_pair.py')
    ready_path=Path(graphics_ready);ready=json.loads(ready_path.read_text())
    spec=finalizer.bind(base,ready,record(ready_path),review_reference)
    supervisor=repo/'work/network-ci-supervisor-portable3/supervisor.py';require(sha(supervisor)==SUPERVISOR_SHA,'Final supervisor changed')
    s=module('cold_pair_supervisor',supervisor);s.verify_spec(spec);s.verify_graphics(spec,s.Proc())
    path=out/(target+'.json');save(path,spec)
    result={'spec':record(path),'supervisor':record(supervisor),'jdkComparison':jdk_result,'gameLaunched':False}
    if diagnostic:result.update(diagnostic_only=True,baseline_acceptance=False,runtimeAcceptance=False,
                                diagnostic_profile=base['diagnostic_profile'])
    elif refreshed:result.update(profile=assembly['profile'],buildProof=assembly['buildProof'],
                               profileSha256=assembly['profileSha256'],runtimeAcceptance=False)
    return result
