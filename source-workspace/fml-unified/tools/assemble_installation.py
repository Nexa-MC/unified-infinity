#!/usr/bin/env python3
"""Assemble a new source-owned installation policy from explicitly pinned build/launch provenance.

Never imports trust from candidate metadata or discovers jars by walking a directory.
No JVM starts here. Only the policy resource is configured in an already full-source-built FML archive.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,shlex,shutil,zipfile
HERE=pathlib.Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('validator',HERE/'validate_launch.py')
v=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(v)
JVM_VALUE_OPTIONS={'--add-opens','--add-exports','--add-reads','--add-modules','--limit-modules'}
PATH_OPTIONS={'-cp':'java.class.path','-classpath':'java.class.path','--class-path':'java.class.path','-p':'jdk.module.path','--module-path':'jdk.module.path'}
ROLES={'BOOT_OWNER','ADMISSION_CONSUMER','COMPATIBILITY_GAME','PRODUCT_GAME','PLATFORM','MANAGED_ROOT'}

def load_pinned(path,expected):
    if v.sha(path)!=expected:raise ValueError('Pinned source/launch document changed: '+str(path))
    return json.loads(path.read_text())
def exact_file(path,pins):
    path=path.resolve(strict=True)
    if str(path) not in pins or v.sha(path)!=pins[str(path)]:raise ValueError('Unpinned launch input: '+str(path))
    return path

def restricted_tokens(path,pins):
    path=exact_file(path,pins)
    if path.stat().st_size>1024*1024:raise ValueError('Argument file exceeds bounded launch grammar')
    text=path.read_text()
    # This deliberately supports the generated Linux NeoForge files only. It is not a permissive shell parser.
    if '\\' in text or '\x00' in text:raise ValueError('Escaped argument files require an independently audited expansion')
    lexer=shlex.shlex(text,posix=True);lexer.whitespace_split=True;lexer.commenters='#';lexer.escape=''
    return list(lexer)
def flatten(command,pins,cwd):
    def expand(args,depth=0):
        if depth>8:raise ValueError('Nested argument-file bound exceeded')
        result=[]
        for arg in args:
            if arg.startswith('@@'):raise ValueError('Literal @ arguments unsupported by this bounded recipe')
            if arg.startswith('@'):
                p=pathlib.Path(arg[1:]);p=p if p.is_absolute() else cwd/p
                result.extend(expand(restricted_tokens(p,pins),depth+1))
            else:result.append(arg)
        if len(result)>65536:raise ValueError('Launch argument count bound exceeded')
        return result
    args=expand(command[1:])
    # Official DevLaunch1.0.2 performs only bounded @ expansion and main delegation; no loader initialization.
    if 'net.neoforged.devlaunch.Main' in args:
        index=args.index('net.neoforged.devlaunch.Main');args.pop(index)
        if args[index]!='cpw.mods.bootstraplauncher.BootstrapLauncher':raise ValueError('Unexpected delegated launch main')
    return args

def prepare(spec):
    installation=pathlib.Path(spec['installationDirectory']).resolve(strict=True)
    game=pathlib.Path(spec['gameDirectory']).resolve()
    sealpath=pathlib.Path(spec['launchSource']['path']).resolve(strict=True)
    seal=load_pinned(sealpath,spec['launchSource']['sha256'])
    cwd=pathlib.Path(seal['workingDirectory']).resolve(strict=True)
    if game==cwd:raise ValueError('Successor assembly cannot overwrite the frozen source game profile')
    pins={str((pathlib.Path(row['path']) if pathlib.Path(row['path']).is_absolute() else HERE.parents[2]/row['path']).resolve()):row['sha256'] for row in seal['files']}
    for row in spec.get('additionalLaunchInputs',[]):
        pins[str(pathlib.Path(row['path']).resolve())]=row['sha256']
    args=flatten(seal['command'],pins,cwd)
    replacements={str(pathlib.Path(old).resolve()):str(pathlib.Path(new).resolve()) for old,new in spec.get('pathReplacements',{}).items()}
    empty={str(pathlib.Path(p).resolve()) for p in spec.get('emptyDevelopmentRoots',[])}
    for path in empty:
        p=pathlib.Path(path)
        if p.exists() and (not p.is_dir() or any(p.iterdir())):raise ValueError('Declared empty development root contains content')
    def rewrite_path(path):
        normalized=str(pathlib.Path(path).resolve())
        return replacements.get(normalized,normalized)
    def path_list(value):
        result=[]
        for entry in value.split(os.pathsep):
            if not entry or '*' in entry:raise ValueError('Empty/wildcard JVM input unsupported')
            actual=str(pathlib.Path(entry).resolve())
            if actual in empty:continue
            result.append(rewrite_path(actual))
        return os.pathsep.join(result)
    properties={key:'' for key in ('java.class.path','jdk.module.path','legacyClassPath','legacyClassPath.file','fml.modFolders','fml.modFoldersFile')}
    i=0;main=None;rewritten=[]
    while i<len(args):
        arg=args[i]
        if arg in PATH_OPTIONS:
            if i+1>=len(args):raise ValueError('Missing JVM path value')
            value=path_list(args[i+1]);properties[PATH_OPTIONS[arg]]=value;rewritten.extend([arg,value]);i+=2;continue
        if arg.startswith('-D'):
            key,sep,value=arg[2:].partition('=')
            if not sep:raise ValueError('Unvalued JVM property unsupported')
            if key in ('fml.modFolders','fml.modFoldersFile','java.system.class.loader') and value:raise ValueError('Unsupported grouped/custom classloader launch')
            if key=='legacyClassPath.file':
                source=exact_file(pathlib.Path(value),pins)
                if source.stat().st_size>1024*1024:raise ValueError('Oversized legacy classpath file')
                paths=[line.strip() for line in source.read_text().splitlines() if line.strip()]
                value=path_list(os.pathsep.join(paths));key='legacyClassPath'
            elif key in PATH_OPTIONS.values() or key=='legacyClassPath':value=path_list(value)
            else:
                value=spec.get('propertyOverrides',{}).get(key,value)
                if value.startswith(str(cwd)+os.sep):value=str(game)+value[len(str(cwd)):]
            if key in properties:properties[key]=value
            rewritten.append('-D'+key+'='+value);i+=1;continue
        if arg in JVM_VALUE_OPTIONS:
            rewritten.extend(args[i:i+2]);i+=2;continue
        if arg.startswith(('-javaagent','-agentpath','-agentlib','-Xbootclasspath','--patch-module','--upgrade-module-path')):raise ValueError('Unsupported pre-BOOT code injection')
        if arg.startswith('-'):
            if arg.startswith(('-Xmx','-Xms','-XX:')):
                if arg.startswith('-Xmx') and 'heapMiB' in spec:arg='-Xmx'+str(int(spec['heapMiB']))+'m'
                rewritten.append(arg);i+=1;continue
            raise ValueError('Unsupported JVM option in source recipe: '+arg.split('=',1)[0])
        main=arg;rewritten.extend(args[i:]);break
    if main!='cpw.mods.bootstraplauncher.BootstrapLauncher':raise ValueError('Successor must use the ordinary pinned BootstrapLauncher/ModLauncher path')
    for option,value in (('--gameDir',str(game)),('--launchTarget',spec['launchTarget'])):
        matches=[i for i,arg in enumerate(rewritten) if arg==option]
        if len(matches)>1:raise ValueError('Duplicate launch selector')
        if matches:rewritten[matches[0]+1]=value
        else:rewritten.extend([option,value])
    if 'classLoadLog' in spec:
        trace=pathlib.Path(spec['classLoadLog']).resolve()
        if trace.parent!=game or any(c in str(trace) for c in ':,\n\r'):
            raise ValueError('Class-origin diagnostic must be a plain file directly inside the isolated game profile')
        # Observation only: one explicit sealed JVM log option, never arbitrary extra launch arguments.
        rewritten.insert(rewritten.index(main),'-Xlog:class+load=info:file='+str(trace)+':uptime,level,tags:filecount=1,filesize=32M')
    if any(arg.startswith('@') for arg in rewritten):raise ValueError('Opaque argument file survived source expansion')
    artifacts=[]
    for row in spec['artifacts']:
        if row['role'] not in ROLES:raise ValueError('Unknown source component role')
        if not row.get('provenance'):raise ValueError('Missing explicit source/official provenance for installation artifact')
        relative=pathlib.Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Uncontained artifact root')
        path=(installation/relative).resolve()
        if not path.is_relative_to(installation):raise ValueError('Artifact escaped installation root')
        if row['role']!='BOOT_OWNER' and (not path.is_file() or v.sha(path)!=row['sha256']):raise ValueError('Pinned component bytes changed')
        artifacts.append({key:row[key] for key in ('path','sha256','primaryIds','role')})
    environment={key:'' for key in ('MOD_CLASSES','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')}
    policy={'schema':1,'approved':True,'policyId':spec['policyId'],'gameDirectory':str(game),'installationDirectory':str(installation),'launchTarget':spec['launchTarget'],'processArgumentsSha256':v.digest_strings(rewritten),'properties':properties,'environment':environment,'artifacts':artifacts,'embedded':spec['embedded'],'argumentFiles':[]}
    return policy,rewritten,seal['command'][0]

def assemble(specpath,specsha,base_receipt_path,base_receipt_sha,output):
    spec=load_pinned(specpath,specsha);policy,args,java=prepare(spec)
    base=load_pinned(base_receipt_path,base_receipt_sha);source=pathlib.Path(base['artifact']).resolve(strict=True)
    if v.sha(source)!=base['sha256']:raise ValueError('Full-source FML input artifact changed')
    repo=HERE.parents[2]
    for relative,expected in base['sources'].items():
        path=repo/'source-workspace'/relative
        if v.sha(path)!=expected:raise ValueError('FML source no longer matches compile receipt')
    output.mkdir(parents=True,exist_ok=False)
    owner_pin=next(row for row in policy['artifacts'] if row['role']=='BOOT_OWNER')
    owner=pathlib.Path(policy['installationDirectory'])/owner_pin['path']
    if owner.resolve()==source or owner.exists():raise ValueError('Refusing to overwrite an existing source/frozen FML artifact')
    owner.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(policy,sort_keys=True,separators=(',',':'))+'\n').encode()
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(owner,'w',zipfile.ZIP_DEFLATED) as target:
        names=original.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate compiled source archive entries')
        for name in sorted(names):
            if name.upper().endswith(('.SF','.RSA','.DSA')):raise ValueError('Cannot configure a signed source archive in place')
            if name=='META-INF/unified-admission/installation.json':continue
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;target.writestr(info,original.read(name))
        info=zipfile.ZipInfo('META-INF/unified-admission/installation.json',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;target.writestr(info,raw)
    receipt=dict(base,artifact=str(owner.resolve()),sha256=v.sha(owner),installationPolicySha256=hashlib.sha256(raw).hexdigest(),installationApproved=True,compiledBaseSha256=base['sha256'],assemblySpecSha256=specsha,sourceLaunchSealSha256=spec['launchSource']['sha256'])
    receipt_path=output/'build-receipt.json';receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    (output/'installation.json').write_bytes(raw)
    result=v.validate(receipt_path,v.sha(receipt_path),args,policy['environment'])
    result.update({'buildReceipt':str(receipt_path),'buildReceiptSha256':v.sha(receipt_path),'configuredOwner':str(owner),'configuredOwnerSha256':receipt['sha256'],'javaExecutable':java,'argumentCount':len(args),'rawArgumentsStored':False,'jvmStarted':False})
    (output/'assembly-report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spec',type=pathlib.Path,required=True);p.add_argument('--expected-spec-sha256',required=True);p.add_argument('--base-receipt',type=pathlib.Path,required=True);p.add_argument('--expected-base-receipt-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    print(json.dumps(assemble(a.spec,a.expected_spec_sha256,a.base_receipt,a.expected_base_receipt_sha256,a.output),sort_keys=True))
