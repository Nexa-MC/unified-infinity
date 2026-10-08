#!/usr/bin/env python3
"""Materialize four side-specific launch seals from existing verified inputs. No processes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = ROOT / 'work/api1'
LOCK_SHA = '616469fb3005028cedb6e6ec0c72e2aec6749bc17162cea9f347b7cfa2ce43dd'
CLIENT_SEAL = API / 'run/api1-unified-client-build/official-client-launch-seal.json'
SERVER_BASE = API / 'run/neoforge-native'
TUPLE = ROOT / 'work/emi-render-integration/built-tuple-artifacts.json'
BASE_RECEIPT = ROOT / 'work/emi-render-integration/fml-base-build-receipt.json'
ASSETS = API / 'run/client-dev/assets'
JAVA = API / '.toolchains/jdk-21.0.12.1+1/bin/java'
JAVA_SHA = '2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d'
NAME = 'APILocal'
UUID = 'dd29b97d-cafa-3d53-94e1-f85f75bcf1f6'

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def pin(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink() and path.is_file(), 'Noncanonical input: '+str(path))
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def save(path, value):
    require(not path.exists(), 'Refusing overwrite: '+str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')
    return pin(path)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def set_option(command, key, value):
    require(command.count(key) <= 1, 'Duplicate option: '+key)
    if key in command:
        index = command.index(key)
        require(index+1 < len(command), 'Missing option value')
        command[index+1] = value
    else:
        command.extend([key, value])

def server_command(argfile):
    text = argfile.read_text()
    require('\\' not in text and '\x00' not in text and len(text) <= 1024*1024, 'Unsupported official argument grammar')
    tokens = shlex.split(text, comments=True)
    for i, token in enumerate(tokens):
        if i and tokens[i-1] in ('-p', '-cp', '--module-path', '--class-path'):
            tokens[i] = ':'.join(str((SERVER_BASE/p).resolve()) for p in token.split(':'))
        elif token.startswith('-DlegacyClassPath='):
            tokens[i] = '-DlegacyClassPath='+':'.join(str((SERVER_BASE/p).resolve()) for p in token.split('=',1)[1].split(':'))
        elif token.startswith('-DlibraryDirectory='):
            tokens[i] = '-DlibraryDirectory='+str(SERVER_BASE/'libraries')
    require(tokens.count('--launchTarget') == 1 and tokens[tokens.index('--launchTarget')+1] == 'forgeserver', 'Expected official production server')
    require(not any(x.startswith(('-Xmx','-Xms','-XX:ActiveProcessorCount=')) for x in tokens), 'Unexpected official VM bounds')
    return [str(JAVA), '-Xms256m', '-Xmx1280m', '-XX:ActiveProcessorCount=2', '-cp',
            str(SERVER_BASE/'libraries/cpw/mods/bootstraplauncher/2.0.2/bootstraplauncher-2.0.2.jar'), *tokens, 'nogui']

def move_profile(command, source, destination):
    command = list(command)
    for i, token in enumerate(command):
        if token.startswith('-D') and '=' in token:
            key, value = token.split('=',1)
            if key not in ('-DlegacyClassPath','-DlibraryDirectory') and value.startswith(str(source)+os.sep):
                command[i] = key+'='+str(destination)+value[len(str(source)):]
    set_option(command, '--gameDir', str(destination))
    return command

def validate_command(command, side, profile, port, files):
    pins = {r['path']: r['sha256'] for r in files}
    require(command[0] == str(JAVA) and pins.get(str(JAVA)) == JAVA_SHA, 'Java identity differs')
    require([x for x in command if x.startswith('-Xmx')] == ['-Xmx1280m'], 'Heap differs')
    require([x for x in command if x.startswith('-XX:ActiveProcessorCount=')] == ['-XX:ActiveProcessorCount=2'], 'CPU bound differs')
    require(not any(x.startswith(('@','-javaagent','-agentlib','-agentpath','-XX:Flags=','-XX:VMOptionsFile=')) for x in command), 'Opaque/injected JVM input')
    expected = 'forgeclientdev' if side == 'client' else 'forgeserver'
    for key, value in [('--gameDir',str(profile)),('--launchTarget',expected)]:
        require(command.count(key) == 1 and command[command.index(key)+1] == value, 'Wrong side/profile selector')
    for i, token in enumerate(command):
        entries = None
        if token in ('-cp','-classpath','--class-path','-p','--module-path'):
            entries = command[i+1].split(':')
        elif token.startswith('-DlegacyClassPath='):
            entries = token.split('=',1)[1].split(':')
        if entries is not None:
            missing=[p for p in entries if p not in pins or not p or '*' in p]
            require(not missing, 'Unpinned explicit code input: '+repr(missing))
    if side == 'client':
        for key,value in [('--username',NAME),('--uuid',UUID),('--accessToken','0'),('--quickPlayMultiplayer','127.0.0.1:'+str(port))]:
            require(command.count(key)==1 and command[command.index(key)+1]==value, 'Client identity/endpoint differs')
        require(not set(command).intersection({'--clientId','--xuid','--userProperties','--server','--proxyHost','--proxyPort','--quickPlayRealms','--quickPlaySingleplayer'}), 'Unapproved client identity/connection')
    else:
        require(command.count('nogui')==1 and not set(command).intersection({'--username','--uuid','--accessToken','--quickPlayMultiplayer'}), 'Wrong server role')

def copy_configs(lock, target, side, game):
    provenance = []
    for relative in lock['acceptedConfigSources'][target][side]:
        source = ROOT/relative
        parts=source.parts
        require('config' in parts, 'Accepted config provenance lacks config root')
        relative_config=Path(*parts[parts.index('config')+1:])
        dest = game/'config'/relative_config
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        provenance.append({'source':pin(source),'target':pin(dest)})
    # Both known server configurations are complete before first world creation.
    for name in ('neoforge-server.toml','sophisticatedbackpacks-server.toml'):
        shutil.copyfile(game/'config'/name, game/'defaultconfigs'/name)
    return provenance

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    require(out.is_absolute() and out.resolve()==out and not out.exists(), 'Fresh canonical output required')
    require(sha(HERE/'input-lock.json')==LOCK_SHA, 'Preparation input lock changed')
    lock=json.loads((HERE/'input-lock.json').read_text())
    for row in lock['files']:
        current=pin(ROOT/row['path'])
        require(current['sha256']==row['sha256'] and current['bytes']==row['bytes'], 'Locked preparation source changed: '+row['path'])
    require(sha(JAVA)==JAVA_SHA, 'Java pin differs')
    sys.path.insert(0,str(API/'four-loader/api-contract-controls'))
    bundle=module('network_pair_upstream_helpers', API/'four-loader/api-contract-controls/prepare_unified.py')
    assembler=module('network_pair_source_assembler',API/'source-workspace/fml-unified/tools/assemble_installation.py')
    normalizer=module('network_pair_normalizer',ROOT/'work/network-pair-ci-next/normalize_exports.py')
    fixture=module('network_pair_fixture',ROOT/'work/network-pair-ci-next/prepare_profiles.py')
    client=json.loads(CLIENT_SEAL.read_text())
    client_files=[]
    for row in client['files']:
        p=Path(row['path'])
        if row.get('kind')=='declared-empty-source-output':
            require(not p.exists() or (p.is_dir() and not any(p.iterdir())), 'Nonempty project development root')
        else:
            current=pin(p);require(current['sha256']==row['sha256'], 'Official client input changed');client_files.append(current)
    pins={row['path']:row['sha256'] for row in client_files}
    flat=assembler.flatten(client['command'],pins,Path(client['workingDirectory']))
    def add_file(path):
        require(str(path) in pins and pin(path)['sha256']==pins[str(path)], 'Unknown client path')
    empty=set(client['emptyDevelopmentRoots'])
    client_command=[str(JAVA)]
    i=0
    while i<len(flat):
        value=flat[i]
        if value in normalizer.PATH_OPTIONS:
            client_command += [value,normalizer.strip_empty_paths(flat[i+1],empty,add_file)];i+=2;continue
        if value.startswith('-DlegacyClassPath.file='):
            legacy=Path(value.split('=',1)[1]);add_file(legacy)
            value='-DlegacyClassPath='+normalizer.strip_empty_paths(':'.join(legacy.read_text().splitlines()),empty,add_file)
        if value.startswith('-Xmx'): value='-Xmx1280m'
        client_command.append(value);i+=1
    require(not set(client_command).intersection({'--username','--uuid','--accessToken','--quickPlayMultiplayer'}), 'Official source already has account/connection input')
    official_lock=json.loads((API/'four-loader/forge-probe/unified-forge-probe-final26b-environment-lock.json').read_text())
    server_files=[]
    for row in official_lock['runtime_files']:
        if '/libraries/' in row['path']:
            p=SERVER_BASE/'libraries'/row['path'].split('/libraries/',1)[1]
            current=pin(p);require(current['sha256']==row['sha256'], 'Official server input changed');server_files.append(current)
    server_files.append(pin(JAVA))
    argfile=SERVER_BASE/'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt'
    require(str(argfile) in {r['path'] for r in server_files}, 'Official server argument file unpinned')
    server_args=server_command(argfile)
    builds=json.loads(TUPLE.read_text());base=json.loads(BASE_RECEIPT.read_text())
    for role,row in builds.items():require(pin(Path(row['path']))['sha256']==row['sha256'], 'Built tuple changed: '+role)
    require(base['sha256']==builds['fml']['sha256'], 'Tuple and base FML disagree')
    out.mkdir()
    results={'schema':1,'status':'SOURCE_ASSEMBLED_GAME_UNRUN','gameLaunched':False,'jvmStarted':False,'groups':{},
             'upstreamPins':{'clientSeal':pin(CLIENT_SEAL),'serverLock':pin(API/'four-loader/forge-probe/unified-forge-probe-final26b-environment-lock.json'),
                             'tuple':pin(TUPLE),'baseReceipt':pin(BASE_RECEIPT),'inputLock':pin(HERE/'input-lock.json')},
             'remaining':['Actual reviewed graphics preflight','Fresh aggregate pair memory gate','Supervisor control-file serialization lifecycle correction before execution','Final executable supervisor seal using actual graphics identity']}
    for target in ('native-neoforge','unified'):
        prep_path=ROOT/'work/network-pair-profiles-local1'/target/'profile-preparation.json'
        prep=json.loads(prep_path.read_text());port=prep['port']
        group=out/target;group.mkdir();roles={}
        for side in ('server','client'):
            original=prep['profiles'][side]
            source_profile=Path(original['workingDirectory'])
            expected={r['path']:r for r in original['files']}
            actual={str(p):pin(p) for p in source_profile.rglob('*') if p.is_file()}
            require(actual==expected,'Prepared fixture changed or contains unexpected input')
            game=group/side;shutil.copytree(source_profile,game)
            config_provenance=copy_configs(lock,target,side,game)
            if side=='server':
                props={}
                for line in (API/'run/api1-unified-server-4/server.properties').read_text().splitlines():
                    if line and not line.startswith('#'):
                        key,value=line.split('=',1);require(key not in props,'Duplicate property');props[key]=value
                props.update(fixture.properties(port))
                # Accepted Unified host carries FFAPI's required fabric pack; native NF does not.
                props['initial-enabled-packs']='vanilla,fabric' if target=='unified' else 'vanilla'
                (game/'server.properties').write_text(''.join(k+'='+v+'\n' for k,v in sorted(props.items())))
            command=list(client_command if side=='client' else server_args)
            source_cwd=Path(client['workingDirectory']) if side=='client' else SERVER_BASE
            if side=='client':
                for key,value in [('--username',NAME),('--uuid',UUID),('--accessToken','0'),('--quickPlayMultiplayer','127.0.0.1:'+str(port))]:set_option(command,key,value)
            sources=client_files if side=='client' else server_files
            launch={'workingDirectory':str(source_cwd),'command':command,'files':sources,'environment':{},
                    'provenance':results['upstreamPins'],'gameLaunched':False,'intentionalChanges':['Explicit bounded heap/CPU','Absolute official paths','Pinned explicit bootstrap classpath on server','Discarded exactly empty development outputs','Virtual loopback identity on client']}
            launch_path=group/(side+'-source-launch.json');save(launch_path,launch)
            mods=[{'source':p,'path':str(game/'mods'/Path(p).name),'sha256':sha(Path(p))} for p in [*original['original_mods'],original['probe_path']]]
            assembly_result=None
            if target=='unified':
                artifacts=[];replacements={};stock=[]
                jars=[r for r in sources if Path(r['path']).suffix=='.jar']
                for row in jars:
                    with zipfile.ZipFile(row['path']) as z:
                        if 'net/neoforged/fml/loading/FMLLoader.class' in z.namelist():stock.append(row['path'])
                require(len(stock)==1,'Expected one stock FML owner')
                for row in jars:
                    source=Path(row['path'])
                    if str(source)==stock[0]:replacements[str(source)]=str(game/'installation/boot.jar');continue
                    destination=(game/'libraries'/source.relative_to(SERVER_BASE/'libraries')) if side=='server' else (game/'installation/platform'/row['sha256']/source.name)
                    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
                    replacements[str(source)]=str(destination)
                    with zipfile.ZipFile(source) as z: ids,_=bundle.descriptor(z)
                    artifacts.append({'path':str(destination.relative_to(game)),'sha256':row['sha256'],'primaryIds':ids,'role':'PLATFORM','provenance':{'officialSource':row}})
                for name,role in [('service','ADMISSION_CONSUMER'),('game','COMPATIBILITY_GAME'),('product','PRODUCT_GAME')]:
                    row=builds[name];dest=game/'installation'/(name+'.jar');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(row['path'],dest)
                    with zipfile.ZipFile(dest) as z:ids,_=bundle.descriptor(z)
                    artifacts.append({'path':str(dest.relative_to(game)),'sha256':row['sha256'],'primaryIds':ids,'role':role,'provenance':{'buildTuple':pin(TUPLE)}})
                artifacts.append({'path':'installation/boot.jar','sha256':'SELF','primaryIds':[],'role':'BOOT_OWNER','provenance':{'baseReceipt':pin(BASE_RECEIPT)}})
                nested=[p for row in artifacts if row['role']!='BOOT_OWNER' for p in bundle.embedded(row['path'],game/row['path'])]
                apis=[r for r in nested if r['role']=='BUNDLED_API']
                require(len(apis)==46 and sum(len(r['primaryIds']) for r in apis)==47,'Changed logical API/archive closure')
                overrides={}
                for token in command:
                    if token.startswith('-D') and '=' in token:
                        key,value=token[2:].split('=',1)
                        if value in replacements:overrides[key]=replacements[value]
                if side=='server':overrides['libraryDirectory']=str(game/'libraries')
                overrides.update({'unified.infinity.qaDirectory':str(game/'qa'),'unified.infinity.progressFile':str(game/'compat-progress.json')})
                spec={'installationDirectory':str(game),'gameDirectory':str(game),'policyId':'network-pair-'+side+'-20261006',
                      'launchTarget':'forgeclientdev' if side=='client' else 'forgeserver','launchSource':pin(launch_path),
                      'pathReplacements':replacements,'propertyOverrides':overrides,'artifacts':artifacts,'embedded':nested,
                      'userMods':mods,'heapMiB':1280,'memoryGateBytes':1879048192,'firstLaunchOnly':False,
                      'classLoadLog':str(game/'class-load.log')}
                spec_path=group/(side+'-assembly-spec.json');save(spec_path,spec)
                assembly_result=assembler.assemble(spec_path,sha(spec_path),BASE_RECEIPT,sha(BASE_RECEIPT),group/(side+'-configured'))
                _,flattened,java=assembler.prepare(spec);command=[java,*flattened]
                role_files=[*sources,*[pin(game/row['path']) for row in artifacts]]
            else:
                command=move_profile(command,source_cwd,game);role_files=list(sources)
            role_files += [pin(p) for p in game.rglob('*') if p.is_file()]
            role_files=list({r['path']:r for r in role_files}.values())
            validate_command(command,side,game,port,role_files)
            roles[side]={'cwd':str(game),'command':command,'files':sorted(role_files,key=lambda r:r['path']),
                         'original_mods':[str(game/'mods'/Path(p).name) for p in original['original_mods']],
                         'probe_path':str(game/'mods'/Path(original['probe_path']).name),'managed_mods':[],
                         'configProvenance':config_provenance,'assembly':assembly_result,'gameLaunched':False}
            save(group/(side+'-launch-seal.json'),roles[side])
        require(roles['server']['cwd']!=roles['client']['cwd'],'Shared process profile')
        results['groups'][target]={'port':port,'roles':{s:pin(group/(s+'-launch-seal.json')) for s in roles},'sourceFixture':pin(prep_path)}
    save(out/'assembly-result.json',results)
    print(json.dumps({'status':results['status'],'result':pin(out/'assembly-result.json'),'roleCount':4,'jvmStarted':False,'remaining':results['remaining']},indent=2))

if __name__=='__main__':
    main()
