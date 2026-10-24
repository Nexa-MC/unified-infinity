#!/usr/bin/env python3
"""Build own native Quilt fixture from official ABI inputs. No game execution."""
import hashlib,json,pathlib,subprocess,zipfile,shutil
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parents[1]; BUILD=HERE/'build'; JAVA=ROOT/'.toolchains/jdk-21.0.12.1+1/bin'; UP=ROOT/'docs/four-loader/quilt/upstream'
pins={'loader-0.30.1.jar':'a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb','qsl_base-alpha5.jar':'7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465','lifecycle_events-alpha5.jar':'1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,value in pins.items(): assert sha(UP/name)==value,name
cp=[UP/n for n in pins]+[ROOT/'run/fabric-native/.fabric/remappedJars/minecraft-1.21.1-0.19.3/server-intermediary.jar']+sorted((ROOT/'run/fabric-native/libraries').rglob('*.jar'))
classes=BUILD/'classes'
if classes.exists(): shutil.rmtree(classes)
classes.mkdir(parents=True,exist_ok=True)
sources=sorted((HERE/'src').rglob('*.java'))
for p in sources:
    assert 'net.fabricmc' not in p.read_text() and 'net.neoforged' not in p.read_text()
subprocess.run([str(JAVA/'javac'),'-proc:none','--release','21','-cp',':'.join(map(str,cp)),'-d',str(classes),*map(str,sources)],check=True)
jar=BUILD/'unified-native-quilt-probe-0.1.0.jar'
subprocess.run([str(JAVA/'jar'),'--create','--date=2026-01-01T00:00:00Z','--file',str(jar),'-C',str(classes),'.','-C',str(HERE/'resources'),'.'],check=True)
with zipfile.ZipFile(jar) as z:
    assert 'quilt.mod.json' in z.namelist() and 'fabric.mod.json' not in z.namelist()
    assert all(b'net/fabricmc' not in z.read(n) and b'net/neoforged' not in z.read(n) for n in z.namelist() if n.endswith('.class'))
negatives=[]
for name,dependency in [('missing-dependency',{'id':'native_quilt_missing_dependency','versions':'=9.9.9'}),('loader-version',{'id':'quilt_loader','versions':'>=0.31.0'})]:
    target=BUILD/f'unified-native-quilt-probe-{name}.jar'
    with zipfile.ZipFile(jar) as source,zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for entry in source.infolist():
            data=source.read(entry.filename)
            if entry.filename=='quilt.mod.json':
                meta=json.loads(data);meta['quilt_loader']['depends']=[d for d in meta['quilt_loader']['depends'] if d['id']!=dependency['id']]+[dependency];data=json.dumps(meta,indent=2).encode()
            info=zipfile.ZipInfo(entry.filename,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;output.writestr(info,data)
    negatives.append({'path':str(target.relative_to(ROOT)),'sha256':sha(target),'must_reject_before':'NATIVE_QUILT_PROBE CLASS_DEFINED'})
report={'negative_controls':negatives,'probe' :str(jar.relative_to(ROOT)),'sha256':sha(jar),'compile_only_pins':pins,'native_descriptor_only':True,'foreign_loader_api_references':False,'runtime_status':'NOT RUN','sources':{str(p.relative_to(ROOT)):sha(p) for p in sources}}
(BUILD/'build-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
