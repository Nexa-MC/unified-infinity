"""Portable opt-in refreshed candidate proof, separate from historical acceptance.

No function in this module launches software or grants runtime acceptance.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import zipfile

PROFILE_SHA256 = 'bc75bf67565aeefffc701a844e5fd3bbc58f22cf5a464cd6594f0aa532538722'
PROFILE_PATH = 'work/network-pair-cold-glue/profiles/ffapi-20261023.json'
OUTPUT = 'work/emi-render-integration/refreshed-build-8f53'
PROOF_PATH = OUTPUT + '/proof.json'
CORE_IDENTITY = '8f53a44cf220eaddca79cf68be6b4c76cae74f7a9f3bc5982ac7d9719b211170'
COMMIT = '2b8a56143f58bc55767cfe23fb67b86111f5c4a0'

class Invalid(ValueError): pass

def require(value, message):
    if not value: raise Invalid(message)

def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def local(consumer, relative):
    root=Path(consumer).absolute()
    require(root.is_dir() and root.resolve()==root, 'Noncanonical consumer root')
    require(isinstance(relative,str) and relative and '\\' not in relative, 'Expected portable relative path')
    path=PurePosixPath(relative)
    require(not path.is_absolute() and '..' not in path.parts and str(path)==relative and relative!='.', 'Path escape/noncanonical relative path')
    result=root.joinpath(*path.parts)
    require(result.resolve()==result and not any(p.is_symlink() for p in (result,*result.parents)), 'Redirected consumer path')
    return result

def pin(consumer,path):
    root=Path(consumer).absolute();p=Path(path)
    if not p.is_absolute():p=local(root,str(p))
    require(p.is_relative_to(root),'Pin leaves consumer')
    relative=p.relative_to(root).as_posix();p=local(root,relative)
    require(p.is_file(),'Missing pinned file: '+relative)
    return {'path':relative,'bytes':p.stat().st_size,'sha256':sha(p)}

def check_pin(consumer,row):
    require(set(row)=={'path','bytes','sha256'},'Unexpected pin fields')
    path=local(consumer,row['path'])
    require(pin(consumer,path)==row,'Changed pinned file: '+row['path'])
    return path

def read_pin(consumer,row): return json.loads(check_pin(consumer,row).read_text())

def save(consumer,relative,value):
    path=local(consumer,relative);require(not path.exists(),'Refusing existing proof/output: '+relative)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return pin(consumer,path)

def portable(consumer,value):
    """Translate verifier-produced paths, never hashes or source-relative keys."""
    root=Path(consumer).absolute()
    if isinstance(value,dict):return {k:portable(root,v) for k,v in value.items()}
    if isinstance(value,list):return [portable(root,v) for v in value]
    if isinstance(value,str) and value.startswith(str(root)+'/'):
        return value[len(str(root))+1:]
    return value

def load_profile(consumer,profile_path, require_dependencies=False):
    path=local(consumer,str(profile_path))
    require(sha(path)==PROFILE_SHA256,'Unreviewed refreshed profile bytes')
    profile=json.loads(path.read_text())
    require(profile['schema']=='portable-ffapi-refreshed-profile-v1' and profile['commit']==COMMIT and profile['coreIdentity']==CORE_IDENTITY,'Wrong refreshed profile')
    require(profile['runtimeAcceptance'] is False and profile['historicalDefaultPreserved'] is True,'Profile cannot grant acceptance')
    for row in profile['inputPins']:check_pin(consumer,row)
    identity=read_pin(consumer,profile['expectedIdentity'])
    require(identity['identity_sha256']==CORE_IDENTITY and len(identity['sources'])==670 and len(identity['dependencies'])==169,'Identity inventory changed')
    require(identity['compiler_runtime']=='21.0.12.1+1-LTS','Compiler identity changed')
    core=local(consumer,profile['coreProject'])
    for row in identity['sources']:
        name=row['path']
        if name.startswith('loader-sources/'):
            path=core.parent/name.removeprefix('loader-sources/')
        else:path=core/name
        current=pin(consumer,path)
        require(current['sha256']==row['sha256'],'Changed source record: '+name)
    delta=read_pin(consumer,profile['ffapiDelta'])
    require(delta['moduleCount']==42 and delta['changedArtifactCount']==46,'Wrong FFAPI refresh scope')
    require(delta['verificationMetadata']['oldSha256']=='301991fa4fb172adc5776daa36a48efadcb855f145cc386fdfc49e307fe9105f' and delta['verificationMetadata']['newSha256']=='8358d87151141de28d6210209d804ee6f494729d54dacfe910865e4a3ee26287','Wrong scoped metadata update')
    identity_dependency_pins(consumer,profile,verify_bytes=require_dependencies)
    return profile

def identity_dependency_pins(consumer,profile,verify_bytes=True):
    identity=read_pin(consumer,profile['expectedIdentity'])
    lock=read_pin(consumer,profile['dependencyLock'])
    result=[]
    for dep in identity['dependencies']:
        matches=[r for r in lock['artifacts'] if r['filename']==dep['filename'] and r['sha256']==dep['sha256']]
        require(matches,'Identity dependency absent from scoped lock: '+dep['filename'])
        row=sorted(matches,key=lambda r:r['path'])[0]
        item={'path':'work/api1/'+row['path'],'bytes':row['bytes'],'sha256':row['sha256']}
        if verify_bytes:check_pin(consumer,item)
        result.append(item)
    return result

def inputs_binding(consumer,profile):
    rows=[pin(consumer,local(consumer,row['path'])) for row in profile['inputPins']]
    return canonical_digest({'inputPins':rows,'identity':profile['expectedIdentity'],'ffapiDelta':profile['ffapiDelta']})

def task_states(log):
    return {task:state.strip() for task,state in re.findall(r'^> Task (:\S+)(?: (.*))?$',log,re.M)}

def normalized_commands(consumer, profile):
    import build_candidate
    constructors={row['path']:row for row in profile['inputPins']}
    expected_constructor=constructors['work/network-pair-cold-glue/build_candidate.py']
    require(sha(Path(build_candidate.__file__))==expected_constructor['sha256'],'Loaded command constructor differs from profile')
    root=Path(consumer).absolute()
    return {role:[str(arg).replace(str(root),'${CONSUMER}') for arg in args]
            for role,args in build_candidate.refreshed_commands(root,profile).items()}

def validate_command(consumer, command, role, profile, session):
    expected=normalized_commands(consumer,profile)
    require(session['commandsDigest']==canonical_digest(expected),'Changed command plan')
    require(command==expected[role],'Command differs from exact role/project/task/toolchain recipe')
    for flag in ['--offline','--no-daemon','--no-parallel','--max-workers=1','--dependency-verification=strict']:
        require(command.count(flag)==1,'Missing/duplicate bounded command flag')
    heaps=re.findall(r'-Xmx(\d+)([mMgG])', ' '.join(command))
    require(heaps and all(0<int(n)*(1024 if unit.lower()=='g' else 1)<=1024 for n,unit in heaps),'Unbounded actual heap')
    require(not any('verification=off' in arg or '--write-verification-metadata' in arg for arg in command),'Verification bypass command')

def validate_receipt(consumer,row,role,profile,session):
    receipt=read_pin(consumer,row)
    require(receipt['schema']=='portable-refreshed-build-receipt-v1' and receipt['role']==role,'Wrong receipt role/schema')
    require(receipt['profileSha256']==PROFILE_SHA256 and receipt['sessionId']==session['sessionId'],'Mixed/stale build receipt')
    require(receipt['inputsBefore']==receipt['inputsAfter']==session['inputsBinding'],'Build inputs changed')
    require(receipt['exitCode']==0 and receipt['gameTask'] is False,'Build did not succeed')
    require(receipt['startedUtc']>=session['startedUtc'] and receipt['finishedUtc']>=receipt['startedUtc'],'Receipt predates build session')
    require(receipt['workers']==1 and receipt['activeProcessors']==1 and 0<receipt['perJvmHeapMiB']<=1024 and 0<receipt['timeoutSeconds']<=1200,'Unbounded build receipt')
    command=receipt['command']
    validate_command(consumer,command,role,profile,session)
    require(receipt['commandDigest']==canonical_digest(command),'Changed receipt command digest')
    import build_candidate
    expected_env={key:value.replace(str(Path(consumer).absolute()),'${CONSUMER}') for key,value in build_candidate.refreshed_environment(consumer,role).items()}
    require(receipt['environment']==expected_env and receipt['cwd']=='${CONSUMER}/work/api1','Changed build environment/cwd')
    log=check_pin(consumer,receipt['log']).read_text()
    require('BUILD SUCCESSFUL' in log and 'BUILD FAILED' not in log,'Successful actual log required')
    observed=task_states(log)
    for task in profile['requiredTasks'][role]:
        require(task in observed and observed[task] not in ('SKIPPED','NO-SOURCE','FAILED'),'Missing/nonexecuted mandatory task: '+task)
    for output in receipt['outputs']:check_pin(consumer,output)
    return receipt

def inspect_tuple(consumer,profile,artifacts):
    require(set(artifacts)=={'service','game','fml','product'},'Wrong tuple roles')
    owners={};packages={}
    for role,row in artifacts.items():
        path=check_pin(consumer,row)
        require(row['sha256']==profile['observedOutputReference'][role],'Tuple no longer reproduces the observed build reference: '+role)
        with zipfile.ZipFile(path) as z:
            names=z.namelist();require(len(names)==len(set(names)),'Duplicate ZIP member')
            require(all(not n.startswith('/') and '..' not in PurePosixPath(n).parts for n in names),'Unsafe ZIP member')
            if role=='service':
                identity=json.loads(z.read('META-INF/unified-infinity/build-identity.json'))
                require(identity['identity_sha256']==CORE_IDENTITY,'SERVICE embeds wrong identity')
            if role in ('service','game'):
                manifest=z.read('META-INF/MANIFEST.MF').decode().replace('\r\n ','').replace('\n ','')
                require('Implementation-Version: '+profile['version'] in manifest,'Wrong candidate version')
            if role=='product':
                names2=[n for n in names if n.startswith('META-INF/jarjar/forgified-fabric-api-') and n.endswith('.jar')]
                require(len(names2)==1 and hashlib.sha256(z.read(names2[0])).hexdigest()==profile['ffapiAggregateSha256'],'Changed runtime FFAPI aggregate')
            for name in names:
                if name.endswith('.class'):
                    require(name not in owners,'Duplicate class owner: '+name);owners[name]=role
                    package=name.rsplit('/',1)[0];require(package not in packages or packages[package]==role,'Split package: '+package);packages[package]=role
    return {'duplicateClasses':0,'splitPackages':0,'classCount':len(owners)}

def proof_input_pins(consumer, profile_path, proof_path, profile, proof, receipts, source, dependencies, official, fixture):
    """Authoritative rehashed closure for assembly/seal TOCTOU protection."""
    rows={}
    def add(row):
        row=portable(consumer,row)
        exact={key:row[key] for key in ('path','bytes','sha256')}
        check_pin(consumer,exact)
        require(exact['path'] not in rows or rows[exact['path']]==exact,'Conflicting closure pin')
        rows[exact['path']]=exact
    def visit(value):
        if isinstance(value,dict):
            if {'path','bytes','sha256'}<=set(value):add(value)
            for item in value.values():visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    for path in (profile_path,proof_path):add(pin(consumer,local(consumer,str(path))))
    for value in (profile['inputPins'],proof,receipts,source,dependencies,official,identity_dependency_pins(consumer,profile)):visit(value)
    identity=read_pin(consumer,profile['expectedIdentity'])
    core=local(consumer,profile['coreProject'])
    for row in identity['sources']:
        name=row['path'];path=core.parent/name.removeprefix('loader-sources/') if name.startswith('loader-sources/') else core/name
        add(pin(consumer,path))
    import build_candidate
    root=Path(consumer).absolute();api=root/'work/api1'
    for name,digest in build_candidate.ORIGINALS.items():
        row=pin(consumer,root/'complex-mod-research'/name)
        require(row['sha256']==digest,'Original regression fixture changed');add(row)
    extra=api/'run/neoforge-native/libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar'
    extra_row=pin(consumer,extra);require(extra_row['sha256']==build_candidate.EXTRA,'Original server regression input changed');add(extra_row)
    manifest=api/'run/client-dev/development-build/moddev/client-launch-inputs.json'
    add(pin(consumer,manifest))
    for item in json.loads(manifest.read_text())['inputs']:
        row=pin(consumer,Path(item['path']))
        require(row['sha256']==item['sha256'],'Changed PRODUCT compile classpath');add(row)
    aggregate=pin(consumer,api/'docs/research/upstream/ffapi-baseline.jar')
    require(aggregate['sha256']==profile['ffapiAggregateSha256'],'Changed original runtime aggregate');add(aggregate)
    add(pin(consumer,api/'docs/four-loader/quilt/bundled-tooltip.json'))
    # The original fixture verifier checks these nested rows; seal them too.
    fixture_value=json.loads(check_pin(consumer,portable(consumer,fixture)).read_text())
    visit(fixture_value)
    fixture_receipt=json.loads(check_pin(consumer,portable(consumer,fixture_value['buildReceipt'])).read_text())
    visit(fixture_receipt)
    add(pin(consumer,Path(fixture_receipt['log'])))
    return [rows[key] for key in sorted(rows)]

def validate_full_build(consumer,profile_path,proof_path):
    profile=load_profile(consumer,profile_path,require_dependencies=True)
    proof=json.loads(local(consumer,str(proof_path)).read_text())
    require(proof['schema']=='portable-refreshed-full-build-v1' and proof['profileSha256']==PROFILE_SHA256,'Wrong proof/profile')
    require(proof['status']=='FULL_BUILD_CHECKED_GAME_UNRUN' and proof['runtimeAcceptance'] is False,'Partial proof or inappropriate acceptance')
    session=read_pin(consumer,proof['session'])
    require(session['profileSha256']==PROFILE_SHA256 and session['inputsBinding']==inputs_binding(consumer,profile),'Stale source/input session')
    require(proof['sessionId']==session['sessionId'],'Wrong proof session')
    require(set(proof['receipts'])=={'core','product','fml'},'Missing full build receipts')
    receipts={role:validate_receipt(consumer,row,role,profile,session) for role,row in proof['receipts'].items()}
    artifacts=proof['artifacts'];ownership=inspect_tuple(consumer,profile,artifacts)
    for role,row in artifacts.items():
        producer='core' if role in ('service','game') else role
        require(row in receipts[producer]['outputs'],'Output not bound to producing receipt')
    generated=read_pin(consumer,proof['generatedIdentity'])
    require(generated==read_pin(consumer,profile['expectedIdentity']),'Actual generated identity differs')
    bundle=read_pin(consumer,proof['bundleVerification'])
    require(bundle['status']=='structural-check-passed' and bundle['runtime_tested'] is False and bundle['bundle_sha256']==artifacts['product']['sha256'] and bundle['ffapi_sha256']==profile['ffapiAggregateSha256'] and bundle['archive_count']==48 and bundle['mod_id_count']==48,'Wrong PRODUCT closure proof')
    import fml_metadata, forge_fixture
    source=fml_metadata.verify_sources(Path(consumer).absolute())
    require(read_pin(consumer,proof['fmlSourcePreparation'])==portable(consumer,source),'FML source binding differs')
    dependencies,official=fml_metadata.verify_dependencies(Path(consumer).absolute())
    baseline=check_pin(consumer,proof['baselineFml'])
    require(sha(baseline)==fml_metadata.BASE_FML_SHA,'Wrong preserved FML base')
    comparison=fml_metadata.compare_archives(baseline,check_pin(consumer,artifacts['fml']),official['path'])
    require(read_pin(consumer,proof['fmlComparison'])==portable(consumer,comparison),'FML comparison changed')
    fixture=forge_fixture.verify_result(Path(consumer).absolute())
    require(proof['forgeFixture']==portable(consumer,fixture),'Wrong original Forge fixture')
    base=read_pin(consumer,proof['baseReceipt'])
    expected_sources={str(Path(row['path']).relative_to(Path(consumer).absolute()/'work/api1/source-workspace')):row['sha256'] for key in ('fixedSources','sharedSources') for row in source['sources'][key] if '/src/main/java/' in row['path'] and row['path'].endswith('.java')}
    require(len(expected_sources)==195 and base['sources']==base['compilationSources']==expected_sources,'Incomplete FML source receipt')
    require(base['artifact']==artifacts['fml']['path'] and base['sha256']==artifacts['fml']['sha256'] and base['sourceIdentitySha256']==CORE_IDENTITY and base['candidateIdentity']==PROFILE_SHA256 and base['profileSha256']==PROFILE_SHA256 and base['baseBuildReceipt']==proof['receipts']['core']['path'] and base['sourceBuildReceipt']==proof['receipts']['fml']['path'],'Wrong FML base receipt binding')
    closure=proof_input_pins(consumer,profile_path,proof_path,profile,proof,receipts,source,dependencies,official,fixture)
    return dict(proof,inputPins=closure,sourceIdentity=CORE_IDENTITY,candidateIdentity=PROFILE_SHA256,candidateIdentityKind='verified-refreshed-build-profile',ownership=ownership,runtimeAcceptance=False)
