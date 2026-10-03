#!/usr/bin/env python3
import hashlib,json,os,pathlib,subprocess,sys
base=pathlib.Path(__file__).resolve().parent;repo=base.parent
artifact=next((base/'connector-combined/build/libs').glob('*-full.jar'));baseline=next((base/'connector/build/libs').glob('*-full.jar'));tests=base/'regression-tests';classes=tests/'classes';classes.mkdir(exist_ok=True)
java=repo/'.toolchains/jdk-21.0.12.1+1/bin';libs=repo/'run/lithium-unified/libraries';asm=sorted((libs/'org/ow2/asm').glob('*/9.8/*.jar'));others=sorted(libs.rglob('*.jar'));guava=libs/'com/google/guava/guava/32.1.2-jre/guava-32.1.2-jre.jar'
cp=os.pathsep.join(map(str,[artifact,guava,*asm,*others]));env=os.environ.copy();env['JAVA_TOOL_OPTIONS']='-Xmx512m -XX:ActiveProcessorCount=2';env.pop('_JAVA_OPTIONS',None)
subprocess.run([str(java/'javac'),'-proc:none','--release','21','-encoding','UTF-8','-cp',cp,'-d',str(classes),*[str(p) for p in sorted((tests/'src').rglob('*.java'))]],env=env,check=True)
lithium=repo/'docs/real-mod-trial/lithium-fabric-0.15.4+mc1.21.1.jar';host=libs/'net/neoforged/neoforge/21.1.219/neoforge-21.1.219-server.jar'
commands=[('parameters','org.sinytra.adapter.transform.param.RemoveParameterTransformerRegression',str(lithium)),('postprocess','PostprocessRegression',str(host))]
report={'schema':1,'artifact':str(artifact.relative_to(repo)),'artifact_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'original_lithium_sha256':hashlib.sha256(lithium.read_bytes()).hexdigest(),'results':[]}
for name,main,arg in commands:
 command=[str(java/'java'),'-ea',f'-Dlog4j2.configurationFile={tests}/log4j2.xml','-cp',str(classes)+os.pathsep+cp,main,arg]
 p=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(repo/f'logs/full-source-regression-{name}.log').write_text(p.stdout);print(p.stdout);report['results'].append({'test':name,'exit_code':p.returncode});assert p.returncode==0
negativecp=os.pathsep.join(map(str,[classes,baseline,guava,*asm,*others]));p=subprocess.run([str(java/'java'),'-ea',f'-Dlog4j2.configurationFile={tests}/log4j2.xml','-cp',negativecp,commands[0][1],str(lithium),'--lithium-only'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(repo/'logs/full-source-regression-negative-control.log').write_text(p.stdout);print(p.stdout)
assert p.returncode!=0 and 'Lithium ASM serialization failed: java.lang.ArrayIndexOutOfBoundsException' in p.stdout and 'Lithium after removal invisible count: expected 7, actual 9' in p.stdout
report['negative_control']={'exit_code':p.returncode,'expected_failure':True,'artifact':str(baseline.relative_to(repo))};(base/'provenance/regression-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
