"""Semantic validation and portable bundle production for the reviewed FFAPI recipe."""
from pathlib import Path
import json
import math
import shutil
import zipfile
import fabric_probe_overlay as b

SOURCE_SHA256 = 'a9316a2bef37b6bc356094d49df4a28deb9a5c03c1d1c96ce14300de9fac1df7'
ARTIFACT_SHA256 = 'ea962bca4cc4d52cacefb1de59d69fe2f8cb4b864d83c984bca95048da5e7dc7'
BUILDER_SHA256 = 'f76786b20efe5a7d7a2baa8590bca72f1bdebc9850199185cc8f217eea129ad7'
UTILITY_SHA256 = '8c4880ce68677d93ca7bba69dccda80a3f9ca4aea7d545bc000a38e9123a8810'
JDK_MANIFEST_SHA256 = 'f01898929ae478e4bdb546eae2b056ef87e9d91232713f1568070fc53ba9de71'
MAPPING_SHA256 = 'b4f0963e90d433f03d3597252da42ff1e38ce9928777c4ce65c779aae71ecdfa'
CLASSPATH_IDENTITY = '2373e81359159882551577cb092a3bfe32cad48ad6487204c66a02b0b4f0039e'
REMAP_TREES = {'probe-intermediary-raw.jar': 'e08e81615ee6b154b9f82f8cff907f9f4a41b89b0f6835e9f8b348cf255b65df',
               'probe-roundtrip.jar': '86454a77490ae8570c9acd5f5a5b34b48c77b53085f80bf6ac34f101275eea58'}
CLASS_TREES = {'main': (12, '1d6d49e417bbc269580a51212f7b9a3c73fe5761c4d89097d9f6e8ee69a4b955'),
               'test': (2, 'e8fa314bfa6eb2991253ff86efe30eb0d90970d248aa9bc02527ca157b17b915'),
               'tools': (8, 'baf6e3b6074984c0f66e88988c988f5d9a7d7bd80088c8fde637ef4270bc2155')}
NAMED_SHA256 = 'ae01e49ada9f53055586f3fbc552bba904283f1a14b43b0dc0a4906ec78c69ec'
ART_SHA256 = 'e977ee4422efb51eb54cc99f939833cef769de8b4aa1043294ce5400c60f3b1f'
EXTRAS = {'networking':(169809,'8752ba0c80491dc56c51ecd037339ec015f73869db5d488eda7189a1a0f45888'),
          'lifecycle':(88814,'b316ff8cb3c7739143e713a1654c1072123079d0e3a07e76c18f94820c0ba767'),
          'base':(34806,'55845058007a954f8ffc2dc313731faf391f48ed52b1b7d31a752a887173ac23'),
          'ffloader':(3459840,'dc8829a0d9b5fa19eb0c50d54c981445fb21cba2abd2a39c5ff0b58ff7d5c1e1')}
PHASES = ('compile-main','compile-test','actual-game-codecs','shared-wire','compile-remapper','actual-remap-roundtrip')
require = b.require


def semantic_result(root, result_path):
    """Rehash complete actual source/tool/95+4/API/remap/log/output proof, no JVM."""
    root=b.root_path(root); result_path=b.absolute(root,result_path); result=b.load(result_path,2*1024*1024)
    require(type(result.get('schema')) is int and result['schema']==1
            and result.get('status')=='PASS_COMPILE_REAL_CODEC_REMAP_ONLY'
            and type(result.get('checks')) is int and result['checks']==184
            and all(result.get(k) is False for k in ('gameLaunched','networkAcceptance','baselineAcceptance')),
            'Actual complete compile/codec/remap proof required')
    owner=result.get('processOwnership')
    b.exact_keys(owner,('mode','builderPid','builderPgrp','builderSession','childCreatesSession'),'owned builder session proof')
    require(owner['mode']=='outer-owned-builder-session' and owner['childCreatesSession'] is False
            and all(type(owner[key]) is int and 0<owner[key]<=2147483647 for key in ('builderPid','builderPgrp','builderSession'))
            and owner['builderPid']==owner['builderPgrp']==owner['builderSession'],
            'Actual outer-owned builder session and nonescaping JVM children required')
    inputs={}
    def add(row, expected=None):
        path=b.check_absolute(root,row)
        require(expected is None or row['sha256']==expected,'Reviewed compiler/source/mapping identity changed')
        portable=b.pin(root,path)
        require(portable['path'] not in inputs or inputs[portable['path']]==portable,'Conflicting build provenance')
        inputs[portable['path']]=portable
        return path
    add(b.absolute_pin(root,result_path))
    source_manifest=add(result['sourceManifest'],SOURCE_SHA256)
    require(result['sourceManifestSha256']==SOURCE_SHA256,'Compiled source manifest identity changed')
    source=b.load(source_manifest);b.exact_keys(source,('schema','status','files'),'compiled source manifest')
    require(source['schema']==1 and source['status']=='SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE','Compiled source schema changed')
    source_root=source_manifest.parent
    for row in source['files']:
        path=b.local(source_root,row['path']);current=b.absolute_pin(root,path)
        require(dict(current,path=row['path'])==row,'Actual compiled source/resource changed');add(current)
    builder=add(result['builder'],BUILDER_SHA256);utility=add(result['remapperUtility'],UTILITY_SHA256)
    require(builder==source_root/'build_probe.py' and utility==source_root/'tools/RemapProbe.java','Build recipe left source closure')
    config_path=add(result['callerConfig']);config=b.load(config_path)
    b.exact_keys(config,('classpath_export','jdk_root','jdk_manifest','art','extra_inputs'),'builder config')
    require(config['classpath_export']==result['classpathSourceManifest'] and config['jdk_manifest']==result['jdkVerificationManifest']
            and config['art']==result['remapper'],'Builder config/proof bindings changed')
    export_path=add(result['classpathSourceManifest']);export=b.load(export_path,2*1024*1024)
    require(type(export.get('inputs')) is list and len(export['inputs'])==95 and export.get('environment')=={}
            and export.get('gameLaunched') is False,'Genuine unchanged 95-input runtime export required')
    expected_cp=[]
    for row in export['inputs']:
        path=b.absolute(root,row['path']);actual=b.absolute_pin(root,path)
        require(actual['sha256']==row['sha256'],'Official runtime classpath changed');expected_cp.append(actual)
    require(type(config['extra_inputs']) is dict and set(config['extra_inputs'])==set(EXTRAS),'Exact four FFAPI inputs required')
    for name,(size,digest) in EXTRAS.items():
        row=config['extra_inputs'][name]
        require(type(row['bytes']) is int and row['bytes']==size and row['sha256']==digest,'Original FFAPI input changed')
        add(row);expected_cp.append(row)
    expected_cp=list({row['path']:row for row in expected_cp}.values())
    require(result['classpathInputs']==expected_cp and len(expected_cp)==99,'Exact 95+4 compiler closure required')
    require(b.digest(b.canonical([{k:row[k] for k in ('bytes','sha256')} for row in expected_cp]))==CLASSPATH_IDENTITY,
            'Reviewed path-independent compiler inventory changed')
    for row in expected_cp:
        path=add(row)
        with zipfile.ZipFile(path) as archive:
            if 'META-INF/MANIFEST.MF' in archive.namelist():
                require(not any(line.lower().startswith('class-path:') for line in archive.read('META-INF/MANIFEST.MF').decode().splitlines()),
                        'Implicit compiler classpath refused')
    jmanifest=add(result['jdkVerificationManifest'],JDK_MANIFEST_SHA256);jreference=b.load(jmanifest)
    jdk=b.absolute(root,config['jdk_root'])
    require(jdk.name=='jdk-21.0.12.1+1' and all(Path(row['path']).parts[0]==jdk.name for row in jreference['files']),
            'Selected compiler root differs from reviewed JDK closure')
    expected_jdk=[b.absolute_pin(root,jdk.parent/row['path']) for row in jreference['files']]
    require(len(expected_jdk)==249 and result['compilerInputs']==expected_jdk,'Exact 249-file compiler closure required')
    require(all(any(row['path']==str(jdk/'bin'/name) for row in expected_jdk) for name in ('java','javac')),
            'Executed compiler tools are not pinned')
    for expected,reference in zip(expected_jdk,jreference['files']):
        require(expected['sha256']==reference['sha256'] and expected['bytes']==reference['bytes'],'Original JDK file changed');add(expected)
    mapping=add(result['mapping'],MAPPING_SHA256);loader=add(result['mappingOwner'],EXTRAS['ffloader'][1]);art=add(result['remapper'],ART_SHA256)
    require(result['mappingOwner']==config['extra_inputs']['ffloader'],'Mapping owner differs from compile loader')
    with zipfile.ZipFile(loader) as archive:require(archive.read('mappings.tsrg')==mapping.read_bytes(),'Original mapping extraction changed')
    require(type(result['callerDeadlineEpoch']) in (int,float) and math.isfinite(result['callerDeadlineEpoch'])
            and result['callerDeadlineEpoch']>0,'Inherited absolute build deadline required')
    out=result_path.parent;cp=':'.join(row['path'] for row in expected_cp)
    libraries=add(b.absolute_pin(root,out/'libraries.txt'))
    require(libraries.read_bytes()==''.join(row['path']+'\n' for row in expected_cp).encode(),
            'Remapper library list differs from exact compiler inputs')
    add(b.absolute_pin(root,out/'probe-named.jar'),NAMED_SHA256)
    # Retain the actual remapping products too; their reviewed executable output
    # is independently fixed by the final canonical artifact hash below.
    for name,digest in REMAP_TREES.items():
        path=add(b.absolute_pin(root,out/name))
        with zipfile.ZipFile(path) as archive:
            names=archive.namelist()
            require(len(names)==len(set(names)) and len(names)<=32,'Invalid remapping output inventory')
            require(sum(info.file_size for info in archive.infolist())<=1024*1024,'Remapping output bound')
            rows=[{'path':n,'bytes':len(archive.read(n)),'sha256':b.digest(archive.read(n))} for n in sorted(names) if not n.endswith('/')]
        require(b.digest(b.canonical(rows))==digest,'Reviewed remapping output inventory changed')
    for group,(count,digest) in CLASS_TREES.items():
        folder=b.absolute(root,out/group);rows=[]
        for path in sorted(folder.rglob('*')):
            require(not path.is_symlink(),'Redirected compiler class output')
            if path.is_file():
                row=b.absolute_pin(root,path);add(row);rows.append(dict(row,path=path.relative_to(folder).as_posix()))
        require(len(rows)==count and b.digest(b.canonical(rows))==digest,'Reviewed executable class output inventory changed')
    empty=b.absolute(root,out/'empty')
    require(empty.is_dir() and not any(empty.iterdir()),'Compiler sourcepath must stay exactly empty')
    limits=['-Xms16m','-Xmx384m','-XX:MaxMetaspaceSize=128m','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC']
    opts=['-proc:none','--release','21','-g','-encoding','UTF-8','-implicit:none','-sourcepath',str(out/'empty')]
    main=sorted(source_root/'src/main/java'/Path(row['path']).relative_to('src/main/java') for row in source['files'] if row['path'].startswith('src/main/java/') and row['path'].endswith('.java'))
    tests=sorted(source_root/row['path'] for row in source['files'] if row['path'].startswith('src/test/java/') and row['path'].endswith('.java'))
    javac=[str(jdk/'bin/javac'),*['-J'+x for x in limits],*opts];java=[str(jdk/'bin/java'),*limits]
    commands=[[*javac,'-cp',cp,'-d',str(out/'main'),*map(str,main)],
              [*javac,'-cp',str(out/'main')+':'+cp,'-d',str(out/'test'),*map(str,tests)],
              [*java,'-cp',str(out/'test')+':'+str(out/'main')+':'+cp,'dev.infinity.fabricnetworkcontrol.PreparedCodecTest'],
              [*java,'-cp',str(out/'test')+':'+str(out/'main'),'dev.infinity.fabricnetworkcontrol.NonceWireTest'],
              [*javac,'-cp',str(art),'-d',str(out/'tools'),str(utility)],
              [*java,'-cp',str(out/'tools')+':'+str(art),'net.neoforged.art.internal.RemapProbe',str(mapping),str(out/'probe-named.jar'),
               str(out/'probe-intermediary-raw.jar'),str(out/'probe-roundtrip.jar'),str(out/'libraries.txt')]]
    require([row['name'] for row in result['phases']]==list(PHASES),'Complete ordered actual build phases required')
    for row,name,command in zip(result['phases'],PHASES,commands):
        require(type(row['exitCode']) is int and row['exitCode']==0 and row['argv']==command
                and type(row['elapsedSeconds']) in (int,float) and math.isfinite(row['elapsedSeconds'])
                and 0<=row['elapsedSeconds']<=90,'Exact bounded build phase changed')
        log=out/(name+'.log');pin=row['log'];b.exact_keys(pin,('path','bytes','sha256'),'phase observation')
        require(pin['path']==str(log) and type(pin['bytes']) is int and 0<=pin['bytes']<=1024*1024
                and b.absolute(root,log)==log and log.is_file(),'Bounded compiler log required')
        data=log.read_bytes();require(len(data)==pin['bytes'] and b.digest(data)==pin['sha256'],'Compiler/remap log changed')
        # Zero-byte compiler observations stay hashed in this nonempty receipt,
        # never weaken supervisor file_pin or export a zero-byte runtime input.
        if data:add(pin)
        token={'actual-game-codecs':b'Prepared codec/input checks: 46; no network or game acceptance',
               'shared-wire':b'ACTUAL_SHARED_NONCE_WIRE assertions=138 PASS',
               'actual-remap-roundtrip':b'ACTUAL_ART_PROBE_ROUNDTRIP classes=12 mapped_classes=6 invokedynamic=34 PASS'}.get(name)
        if token:require(data.splitlines().count(token)==1,'Actual codec/remap assertions absent')
    artifact=add(result['artifact'],ARTIFACT_SHA256)
    require(artifact==out/b.ARTIFACT_NAME,'Wrong final remapped artifact path')
    b.verify_archive(artifact,source_root/'src/main/resources/fabric.mod.json')
    with zipfile.ZipFile(artifact) as archive:
        require(archive.read('META-INF/MANIFEST.MF')==b'Manifest-Version: 1.0\r\nFabric-Mapping-Namespace: intermediary\r\n\r\n',
                'Named-only artifact cannot be staged')
        require(len([n for n in archive.namelist() if n.endswith('.class')])==12,'Reviewed class inventory changed')
    return {'result':result,'inputPins':sorted(inputs.values(),key=lambda row:row['path'])}


def _descriptor(root,bundle_pin):
    value=b.load(b.check(root,bundle_pin))
    require(value['source_manifest']['sha256']==SOURCE_SHA256 and value['artifact']['sha256']==ARTIFACT_SHA256,
            'Bundle is not the immutable reviewed source/artifact')
    return {'bundle_pin':bundle_pin,'reviewed':{'source_manifest_sha256':SOURCE_SHA256,'artifact_sha256':ARTIFACT_SHA256,
                                             'namespace_proof_sha256':value['namespace_proof']['sha256']}}


def validate_bundle(root,descriptor):
    root=b.root_path(root);b.exact_keys(descriptor,('bundle_pin','reviewed'),'FFAPI opt-in descriptor')
    require(descriptor==_descriptor(root,descriptor['bundle_pin']),'Self-declared reviewed identities refused')
    bound=b.verify_source_binding(root,descriptor['bundle_pin'],reviewed=descriptor['reviewed'])
    semantic=semantic_result(root,b.check(root,bound['bundle']['build_result']))
    result=semantic['result']
    require(result['artifact']['sha256']==bound['bundle']['artifact']['sha256']
            and result['sourceManifest']['sha256']==bound['bundle']['source_manifest']['sha256'],'Compiled/staged source artifact differs')
    namespace=b.load(b.check(root,bound['bundle']['namespace_proof']))
    expected_evidence=[b.pin(root,Path(result[key]['path'])) for key in
                       ('mapping','mappingOwner','remapper','remapperUtility','builder')]
    expected_evidence += [bound['bundle']['build_result']]
    require(namespace['evidence']==expected_evidence,'Namespace proof not bound to complete actual remap evidence')
    merged={row['path']:row for row in bound['inputs']}
    for row in semantic['inputPins']:
        require(row['path'] not in merged or merged[row['path']]==row,'Conflicting semantic closure');merged[row['path']]=row
    return {'binding':bound,'inputPins':sorted(merged.values(),key=lambda row:row['path']),'descriptor':descriptor}


def describe_bundle(root,bundle_pin):
    """Derive dynamic path-specific proof hash only after immutable semantic checks."""
    root=b.root_path(root);descriptor=_descriptor(root,bundle_pin);validate_bundle(root,descriptor);return descriptor


def create_bundle(root,source_root,output):
    """Validate output/result.json, materialize clean sources, write proof/bundle.

    No compile is run here. output is the successful builder output directory.
    Existing bundle/source outputs are refused; no baseline is overwritten.
    """
    root=b.root_path(root);source_root=b.absolute(root,source_root);output=b.absolute(root,output)
    semantic=semantic_result(root,output/'result.json');result=semantic['result']
    source_manifest=source_root/'source-manifest.json'
    require(b.pin(root,source_manifest)['sha256']==SOURCE_SHA256,'Requested source tree changed')
    staged=output/'sealed-sources';require(not staged.exists(),'Stale staged source tree');staged.mkdir()
    source=b.load(source_manifest)
    for row in source['files']:
        source_path=b.local(source_root,row['path']);target=staged/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        require(dict(b.pin(root,source_path),path=row['path'])==row,'Source copy changed');shutil.copyfile(source_path,target)
    shutil.copyfile(source_manifest,staged/'source-manifest.json')
    def write(name,value):
        path=output/name
        with path.open('xb') as stream:stream.write(b.canonical(value)+b'\n')
        return b.pin(root,path)
    result_pin=b.pin(root,output/'result.json')
    namespace={'schema':b.MAPPING_SCHEMA,'status':'REMAP_VERIFIED_NOT_RUNTIME_ACCEPTANCE',
               'source_namespace':'mojang','artifact_namespace':'intermediary','runtime_namespace':'mojang',
               'mechanism':'pinned-fart-mojang-to-intermediary','source_manifest_sha256':SOURCE_SHA256,
               'artifact_sha256':ARTIFACT_SHA256,'evidence':[b.pin(root,Path(result[key]['path'])) for key in
                   ('mapping','mappingOwner','remapper','remapperUtility','builder')]+[result_pin]}
    namespace_pin=write('namespace-proof.json',namespace)
    bundle={'schema':b.BUNDLE_SCHEMA,'diagnostic_only':True,'baseline_acceptance':False,
            'artifact':b.pin(root,Path(result['artifact']['path'])),'source_manifest':b.pin(root,staged/'source-manifest.json'),
            'build_binding':b.pin(root,output/'probe-build-binding.json'),'build_result':result_pin,'namespace_proof':namespace_pin}
    bundle_pin=write('bundle.json',bundle)
    return describe_bundle(root,bundle_pin)


def build_bundle(root, source_root, build_output):
    """Driver alias; validates and packages proof only, never launches a JVM."""
    return create_bundle(root, source_root, build_output)
