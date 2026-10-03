#!/usr/bin/env python3
"""Explicit bounded metadata-only envelope tests. Requires the released JVM slot."""
import argparse,hashlib,io,json,os,pathlib,shutil,subprocess,zipfile
HERE=pathlib.Path(__file__).resolve().parent;REPO=HERE.parents[3];FML=REPO/'source-workspace/fml-unified';JDK=REPO/'.toolchains/jdk-21.0.12.1+1/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def archive(p,files):
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)
def run():
    a=argparse.ArgumentParser();a.add_argument('--name',default='official-envelope-v1');o=a.parse_args();out=FML/'build'/o.name;out.mkdir(exist_ok=False);classes=out/'classes';classes.mkdir()
    official=REPO/'docs/research/upstream/connector-2.0.0-beta.17+1.21.1-full.jar';assert sha(official)=='270b2d385be50932419b7d57d4f4bf7328d70e08d0dd9d88adefdb3c5d08a986'
    base=FML/'build/harmless-final-fusion-v1';baseline=json.loads((base/'report.json').read_text());assert baseline['status']=='PASS'
    dependencies=[]
    for x in json.loads((FML/'provenance/compile-classpath-lock.json').read_text())['artifacts']:
        p=REPO/x['path'];assert sha(p)==x['sha256'];dependencies.append(str(p))
    changed=[REPO/'source-workspace/admission-bootstrap/src/main/java/org/sinytra/connector/infinity/inventory'/n for n in ['AdmissionSession.java','AuditedConnectorEnvelope.java']]
    sources=changed+list((HERE/'src').rglob('*.java'))
    env={k:v for k,v in os.environ.items() if k not in ('_JAVA_OPTIONS','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS')}
    compilecmd=[str(JDK/'javac'),'-J-Xmx192m','-J-XX:ActiveProcessorCount=2','--release','21','-proc:none','-cp',os.pathsep.join([str(base/'runtime'),*dependencies]),'-d',str(classes),*map(str,sources)]
    with (out/'compile.log').open('w') as f:subprocess.run(compilecmd,stdout=f,stderr=subprocess.STDOUT,check=True,env=env)
    with zipfile.ZipFile(official) as z:original={n:z.read(n) for n in z.namelist()}
    cases=['official','changed-digest','extra-provider','unrelated-child','changed-child','trusted','api-parent-content-child','api-parent-library-content-grandchild','support-library'];results=[]
    childname='META-INF/jarjar/org.sinytra.connector-2.0.0-beta.17+1.21.1-mod.jar'
    for mode in cases:
        case=out/mode;mods=case/'game/mods';mods.mkdir(parents=True);shutil.copyfile(base/'test-owner.jar',case/'owner.jar');reverse=mode.startswith('api-parent-') or mode=='support-library';target=mods/('parent.jar' if reverse else 'connector.jar')
        if reverse:
            def meta(modid):return ('modLoader="javafml"\nloaderVersion="[4,)"\nlicense="MIT"\n[[mods]]\nmodId="'+modid+'"\nversion="1"\n').encode()
            def nested_meta(name):return json.dumps({'jars':[{'identifier':{'group':'fixture','artifact':'nested'},'version':{'range':'[1,)','artifactVersion':'1'},'path':name,'isObfuscated':False}]}).encode()
            child=io.BytesIO();archive(child,{'META-INF/neoforge.mods.toml':meta('fixture_content')} if mode!='support-library' else {'support.txt':b'private API support resource'})
            if mode=='api-parent-library-content-grandchild':
                middle=io.BytesIO();archive(middle,{'nested/content.jar':child.getvalue(),'META-INF/jarjar/metadata.json':nested_meta('nested/content.jar')});child=middle
            archive(target,{'META-INF/neoforge.mods.toml':meta('fabric_api'),'nested/child.jar':child.getvalue(),'META-INF/jarjar/metadata.json':nested_meta('nested/child.jar')})
        elif mode in ['official','trusted']:shutil.copyfile(official,target)
        else:
            data=dict(original)
            if mode=='changed-digest':data['fixture-note.txt']=b'changed release bytes only'
            if mode=='extra-provider':data['META-INF/services/net.neoforged.neoforgespi.earlywindow.GraphicsBootstrapper']=b'fixture.MustNeverInitialize\n'
            if mode=='changed-child':
                with zipfile.ZipFile(io.BytesIO(data[childname])) as z:inner={n:z.read(n) for n in z.namelist()}
                inner['fixture-note.txt']=b'changed nested bytes';buf=io.BytesIO();archive(buf,inner);data[childname]=buf.getvalue()
            if mode=='unrelated-child':
                buf=io.BytesIO();archive(buf,{'META-INF/neoforge.mods.toml':b'modLoader="javafml"\nloaderVersion="[4,)"\nlicense="MIT"\n[[mods]]\nmodId="unrelated_content"\nversion="1"\n'})
                name='META-INF/jarjar/unrelated.jar';data[name]=buf.getvalue();meta=json.loads(data['META-INF/jarjar/metadata.json']);meta['jars'].append({'identifier':{'group':'fixture','artifact':'unrelated'},'version':{'range':'[1,)','artifactVersion':'1'},'path':name,'isObfuscated':False});data['META-INF/jarjar/metadata.json']=json.dumps(meta).encode()
            archive(target,data)
        modules=[p for p in dependencies if '/securejarhandler/3.0.8/' in p or '/asm/9.8/' in p or '/asm-tree/9.8/' in p]
        cp=[p for p in dependencies if '/securejarhandler/' not in p and '/org/ow2/asm/asm/' not in p and '/org/ow2/asm/asm-tree/' not in p]
        cmd=[str(JDK/'java'),'-Xmx96m','-XX:ActiveProcessorCount=2','--module-path',os.pathsep.join(modules),'--add-modules','cpw.mods.securejarhandler','--add-opens','java.base/java.util.jar=cpw.mods.securejarhandler','--add-opens','java.base/java.lang.invoke=cpw.mods.securejarhandler','-cp',os.pathsep.join([str(classes),str(base/'runtime'),*cp]),'org.sinytra.connector.infinity.inventory.'+('ReverseNestedHarness' if reverse else 'EnvelopeHarness'),str(case),mode]
        with (case/'result.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
        text=(case/'result.log').read_text();print(text[-1800:],flush=True);results.append({'case':mode,'exitCode':r.returncode,'passLine':next((s for s in text.splitlines() if s.startswith('PASS ')),None)})
        if r.returncode:break
    report={'status':'PASS' if len(results)==len(cases) and all(x['exitCode']==0 for x in results) else 'FAIL','scope':'canonical metadata scan and real SERVICE candidate exclusion only; no official provider classes or game run','cases':results,'officialSourceUnchanged':sha(official)=='270b2d385be50932419b7d57d4f4bf7328d70e08d0dd9d88adefdb3c5d08a986','sources':{str(p.relative_to(REPO)):sha(p) for p in sources}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__':run()
