#!/usr/bin/env python3
"""Explicit bounded JVM tests, no game/GLFW. Parent must release the JVM budget first."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,zipfile
HERE=pathlib.Path(__file__).resolve().parent
REPO=HERE.parents[3]
FML=REPO/'source-workspace/fml-unified'
JDK=REPO/'.toolchains/jdk-21.0.12.1+1/bin'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def jar(path, files):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,value in sorted(files.items()):archive.writestr(name,value)
def metadata(modid):return ('modLoader="javafml"\nloaderVersion="[1,)"\nlicense="MIT"\n[[mods]]\nmodId="'+modid+'"\nversion="1.0"\ndisplayName="Admission fixture"\n').encode()
def run():
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-compiled',type=pathlib.Path);parser.add_argument('--name',default='harmless-markers-v3');options=parser.parse_args()
    output=FML/'build'/options.name
    if output.exists():raise SystemExit('Refusing to overwrite existing test evidence')
    output.mkdir(parents=True);classes=output/'classes';classes.mkdir()
    lock=json.loads((FML/'provenance/compile-classpath-lock.json').read_text());dependencies=[]
    for item in lock['artifacts']:
        p=REPO/item['path'];assert sha(p)==item['sha256'];dependencies.append(str(p))
    production=sorted((FML/'src/main/java').rglob('*.java'))+sorted((REPO/'source-workspace/admission-bootstrap/src/main/java').rglob('*.java'))
    test=sorted((HERE/'src').rglob('*.java'))+sorted((HERE/'harness').rglob('*.java'))+sorted((HERE/'dependency-src').rglob('*.java'))
    args=['--release','21','-proc:none','-encoding','UTF-8','-classpath',os.pathsep.join(dependencies),'-d',str(classes),*map(str,production+test)]
    argfile=output/'javac.args';argfile.write_text('\n'.join('"'+x.replace('\\','\\\\').replace('"','\\"')+'"' for x in args)+'\n')
    if options.reuse_compiled:
        previous=json.loads((options.reuse_compiled/'report.json').read_text())
        for path in production+test:assert previous['sources'][str(path.relative_to(REPO))]==sha(path),'Changed compiled source'
        shutil.copytree(options.reuse_compiled/'classes',classes,dirs_exist_ok=True)
        shutil.copyfile(options.reuse_compiled/'compile.log',output/'compile.log')
    else:
        with (output/'compile.log').open('w') as log:subprocess.run([str(JDK/'javac'),'-J-Xmx192m','-J-XX:ActiveProcessorCount=2','@'+str(argfile)],stdout=log,stderr=subprocess.STDOUT,check=True)
    runtime=output/'runtime';runtime.mkdir();provider={};api={};content={};owner={}
    for file in classes.rglob('*.class'):
        name=file.relative_to(classes).as_posix();data=file.read_bytes()
        if name.startswith('org/unifiedinfinity/gatefixture/'):provider[name]=data
        elif name.startswith('fixture/api/'):api[name]=data
        elif name.startswith('fixture/content/'):content[name]=data
        else:
            target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            if 'AdmissionMarkerHarness' not in name:owner[name]=data
    for file in (FML/'src/main/resources').rglob('*'):
        if file.is_file():owner[file.relative_to(FML/'src/main/resources').as_posix()]=file.read_bytes()
    owner['META-INF/unified-admission/installation.json']=b'{"schema":1,"approved":false}\n'
    owner_path=output/'test-owner.jar';jar(owner_path,owner)
    services={'net.neoforged.neoforgespi.earlywindow.GraphicsBootstrapper':'MarkedGraphics','cpw.mods.modlauncher.api.ITransformationService':'MarkedTransformer','net.neoforged.neoforgespi.earlywindow.ImmediateWindowProvider':'MarkedWindow','net.neoforged.neoforgespi.locating.IModFileCandidateLocator':'MarkedLocator','net.neoforged.neoforgespi.locating.IModFileReader':'MarkedReader','net.neoforged.neoforgespi.locating.IDependencyLocator':'MarkedDependency'}
    provider.update({'META-INF/services/'+name:('org.unifiedinfinity.gatefixture.'+impl+'\n').encode() for name,impl in services.items()})
    provider['META-INF/MANIFEST.MF']=b'Manifest-Version: 1.0\nAutomatic-Module-Name: admission.fixture.provider\n\n'
    results=[]
    for name in ['denied','forged','copied','reentry','ordinary','trusted','nested']:
        case=output/name;mods=case/'game/mods';mods.mkdir(parents=True);(case/'markers').mkdir();shutil.copyfile(owner_path,case/'owner.jar')
        files=dict(provider);files['META-INF/neoforge.mods.toml']=metadata('fixture_content' if name=='ordinary' else 'connector')
        if name=='forged':files['META-INF/neoforge.mods.toml']+=b'\n[properties]\nbuiltin=true\ntrusted=true\n'
        if name=='nested':
            files['META-INF/neoforge.mods.toml']=metadata('fabric_api');child=case/'denied-child-template.jar';jar(child,files)
            parent=dict(content);parent['META-INF/neoforge.mods.toml']=metadata('fixture_content')+b'\n[[dependencies.fixture_content]]\nmodId="fabric_api"\ntype="required"\nversionRange="[1,2)"\nordering="NONE"\nside="BOTH"\n'
            parent['nested/api.jar']=child.read_bytes();parent['META-INF/jarjar/metadata.json']=json.dumps({'jars':[{'identifier':{'group':'fixture','artifact':'api'},'version':{'range':'[1,2)','artifactVersion':'1.0'},'path':'nested/api.jar','isObfuscated':False}]}).encode();jar(mods/'parent.jar',parent)
            builtin=dict(api);builtin['META-INF/neoforge.mods.toml']=metadata('fabric_api');jar(case/'builtin.jar',builtin)
        else:
            jar(mods/'provider.jar',files)
            if name=='copied':(case/'trusted').mkdir();shutil.copyfile(mods/'provider.jar',case/'trusted/provider.jar')
        module_dependencies=[p for p in dependencies if '/securejarhandler/3.0.8/' in p or '/asm/9.8/' in p or '/asm-tree/9.8/' in p]
        class_dependencies=[p for p in dependencies if '/securejarhandler/' not in p and '/org/ow2/asm/asm/' not in p and '/org/ow2/asm/asm-tree/' not in p]
        command=[str(JDK/'java'),'-Xmx96m','-XX:ActiveProcessorCount=2','--module-path',os.pathsep.join(module_dependencies),'--add-modules','cpw.mods.securejarhandler','--add-opens','java.base/java.util.jar=cpw.mods.securejarhandler','--add-opens','java.base/java.lang.invoke=cpw.mods.securejarhandler','--add-exports','java.base/sun.security.util=cpw.mods.securejarhandler','-cp',os.pathsep.join([str(runtime),*class_dependencies]),'org.sinytra.connector.infinity.inventory.AdmissionMarkerHarness',str(case),name]
        log=case/'result.log'
        with log.open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        text=log.read_text();print(text[-2500:],flush=True)
        results.append({'case':name,'exitCode':result.returncode,'passLine':next((line for line in text.splitlines() if line.startswith('PASS case=')),None)})
        if result.returncode:break
    report={'status':'PASS' if len(results)==7 and all(r['exitCode']==0 for r in results) else 'FAIL','scope':'fresh-process patched FML discovery and JarJar selector edges; not full production BootstrapInstallation or ModLauncher layer launch','productionSourcesCompiled':len(production),'fixtureSourcesCompiled':len(test),'javaHeapMiB':96,'javacHeapMiB':192,'testOwnerSha256':sha(owner_path),'gameOrGlfwStarted':False,'cases':results,'sources':{str(p.relative_to(REPO)):sha(p) for p in production+test}}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='sources'}));raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__':run()
