#!/usr/bin/env python3
"""Verify an actual portable receipt against independently reviewed immutable content, offline."""
import argparse,hashlib,json,os,pathlib,zipfile
from portable_io import canonical,consumer_path,no_aliases,load as load_json
T=canonical(pathlib.Path(__file__).absolute().parent,kind='directory')
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def pin(p):p=pathlib.Path(p).resolve();return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def check_file(row,expected=None):
 require(type(row.get('bytes')) is int and row['bytes']>=0 and isinstance(row.get('sha256'),str) and len(row['sha256'])==64,'typed file pin');p=canonical(row['path']);require(pathlib.Path(row['path']).is_absolute() and str(p)==row['path'],'canonical absolute file path');require(sha(p)==row['sha256'] and p.stat().st_size==row['bytes'],'actual file binding '+str(p))
 if expected is not None:require(row['sha256']==expected['sha256'] and row['bytes']==expected['bytes'],'reviewed file identity '+str(p))
 return p
def validate(receipt,contract_path,contract_sha):
 contract_path=canonical(contract_path);receipt=canonical(receipt);require(sha(contract_path)==contract_sha,'caller-reviewed contract hash mismatch');c=load_json(contract_path);require(c['schema']==1 and c['scope']=='COMPILE_ABI_ONLY_DIAGNOSTIC','reviewed contract schema');d=load_json(receipt);out=receipt.parent
 tools={x['path']:x for x in c['tools']}
 for name,row in tools.items():check_file(pin(T/name),row)
 require(d['schema']==1 and d['portableVersion']==1 and d['status']=='PASS_COMPILE_ABI_ONLY','completed portable receipt required')
 require(d['diagnosticOnly'] is True and all(d[k] is False for k in ['runtimeAcceptance','baselineAcceptance','gameLaunched','ciStarted','originalArtifactLocksChanged','foreignLoaderApiReferences','historicalArtifactReproduced']),'no acceptance expansion')
 require(d['nativeDescriptorOnly'] is True and d['serialJvmOnly'] is True and d['deterministicRecompile'] is True,'required compile boundaries')
 check_file(d['builder'],tools['build_portable.py']);check_file(d['reviewedContract'],pin(contract_path));check_file(d['portableConfig']);require(d['limits']==c['limits'],'explicit conservative JVM limits')
 require(set(d['sourceInputRoles'])==set(c['inputs']),'all original input roles required');roles={key:check_file(d['sourceInputRoles'][key],row) for key,row in c['inputs'].items()}
 root=canonical(d['consumerRoot'],kind='directory');require(str(root)==d['consumerRoot'] and out.is_relative_to(root),'exact canonical consumer root');config=load_json(d['portableConfig']['path']);require(set(config)=={'schema','paths'} and type(config['schema']) is int and config['schema']==1 and set(config['paths'])==set(c['inputs'])|{'jdk_root'},'exact portable path config')
 configured={key:consumer_path(root,value,'directory' if key=='jdk_root' else 'file') for key,value in config['paths'].items()};no_aliases(configured.values());require({k:str(v) for k,v in configured.items()}=={**{k:str(v) for k,v in roles.items()},'jdk_root':d['jdkRoot']},'config and actual input/JDK paths must agree')
 require(d['sourceManifest']==d['sourceInputRoles']['source_manifest'] and d['sourceArchive']==d['sourceInputRoles']['source_archive'],'original source provenance')
 source_root=roles['source_manifest'].parent;source=load_json(roles['source_manifest']);require(source['files']==c['source_files'] and d['sourceFiles']==c['source_files'],'exact nine source identities')
 for row in c['source_files']:check_file(pin(source_root/row['path']),row)
 fixture=source_root/'four-loader/quilt-probe';require({str(p.relative_to(source_root)) for p in fixture.rglob('*') if p.is_file()}=={x['path'] for x in c['source_files']},'no unlisted source inputs')
 require(d['historicalBuildReport']['notFreshProof'] is True,'historical report explicitly stale');check_file(d['historicalBuildReport'],next(x for x in c['source_files'] if x['path'].endswith('build/build-report.json')))
 with zipfile.ZipFile(roles['source_archive']) as z:
  for row in c['source_files']:require(hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256'],'archive-source binding')
 jdk=canonical(d['jdkRoot'],kind='directory');require(str(jdk)==d['jdkRoot'],'canonical JDK root');require(d['jdkCanonicalFilesVerified']==249 and load_json(roles['jdk_manifest'])['files']==c['jdk_files'],'full original JDK manifest')
 for row in c['jdk_files']:check_file(pin(jdk/pathlib.PurePosixPath(row['path']).relative_to('jdk-21.0.12.1+1')),row)
 require(d['jdkManifest']==d['sourceInputRoles']['jdk_manifest'],'JDK role binding')
 game=d['derivedGame'];check_file(game);require(game['notHistorical'] is True and game['resourcesIntentionallyExcluded'] is True and game['runnableGameArchive'] is False and game['gameClassCount']==6148,'derived-not-historical full classes-only game')
 require(game['parentServerBundle']==d['sourceInputRoles']['server_bundle'] and game['mappingOwner']==d['sourceInputRoles']['mapping_owner'] and game['remapper']==d['sourceInputRoles']['loader'],'native remapping original input chain')
 mapping=check_file(game['mapping']);require(sha(mapping)==c['mappingSha256']==game['mappingSha256'],'original mapping digest')
 with zipfile.ZipFile(roles['mapping_owner']) as z:require(z.read('mappings/mappings.tiny')==mapping.read_bytes(),'mapping owner content')
 with zipfile.ZipFile(game['path']) as z:
  names=z.namelist();require(len(names)==len(set(names)) and all(n.endswith(('.class','/')) for n in names),'classes-only derived archive')
  classes=[{'path':n,'bytes':len(z.read(n)),'sha256':hashlib.sha256(z.read(n)).hexdigest()} for n in sorted(names) if n.endswith('.class')]
 require(len(classes)==6148 and hashlib.sha256(json.dumps(classes,sort_keys=True,separators=(',',':')).encode()).hexdigest()==c['derivedGameClassContentSha256']==game['classContentSha256'],'exact real derived game class content')
 embedded=[]
 with zipfile.ZipFile(roles['server_bundle']) as z:
  for category in ['versions','libraries']:
   for line in z.read('META-INF/'+category+'.list').decode().splitlines():
    expected,coordinate,relative=line.split('\t');entry='META-INF/'+category+'/'+relative;blob=z.read(entry);require(hashlib.sha256(blob).hexdigest()==expected,'official embedded input')
    embedded.append({'entry':entry,'coordinate':coordinate,'path':str(out/'official-inputs'/category/relative),'sha256':expected,'bytes':len(blob)})
 require(len(d['embeddedOfficialInputs'])==len(embedded),'complete official embedded closure')
 for row,expected in zip(d['embeddedOfficialInputs'],embedded):
  check_file(row,expected);require(row['path']==expected['path'] and row['archiveEntry']==expected['entry'] and row['coordinate']==expected['coordinate'],'embedded original provenance')
 require(game['embeddedEntry']==d['embeddedOfficialInputs'][0],'one original server entry')
 remap_tools=[roles['loader'],*[roles[n] for n in c['asmRoles']]];require(d['remapperInputs']==[pin(p) for p in remap_tools] and d['abiVerifierInputs']==[pin(roles['art'])],'tool closure identities')
 libs=[pathlib.Path(x['path']) for x in embedded[1:]]+[roles['annotations'],roles['jsr305']]
 closure=[roles['loader'],roles['qsl_base'],roles['qsl_lifecycle'],pathlib.Path(game['path']),roles['mixin'],*libs]
 require(len(d['compileInputs'])==len(closure) and len(set(closure))==len(closure),'exact compile closure size')
 for row,path in zip(d['compileInputs'],closure):require(row['path']==str(path),'compile closure order/path');check_file(row)
 require((out/'remap-libraries.txt').read_text()==''.join(str(p)+'\n' for p in libs) and (out/'compile-classpath.txt').read_text()==''.join(str(p)+'\n' for p in closure),'classpath byte bindings')
 for p in closure:
  with zipfile.ZipFile(p) as z:
   if 'META-INF/MANIFEST.MF' in z.namelist():require(not any(s.lower().startswith('class-path:') for s in z.read('META-INF/MANIFEST.MF').decode().splitlines()),'no implicit classpath')
 artifact=check_file(d['artifact'],c['artifact']);rebuild=check_file(d['rebuildArtifact'],c['artifact']);require(artifact==out/'unified-native-quilt-probe-0.1.0.jar' and rebuild==out/'unified-native-quilt-probe-0.1.0-rebuild.jar','distinct deterministic build outputs');no_aliases([artifact,rebuild]);require(d['artifact']['namespace']=='intermediary','native compile namespace')
 with zipfile.ZipFile(artifact) as z:
  require(len(z.namelist())==8 and set(z.namelist())=={x['path'] for x in c['jarEntries']},'exact compiled archive inventory')
  for row in c['jarEntries']:
   blob=z.read(row['path']);require(len(blob)==row['bytes'] and hashlib.sha256(blob).hexdigest()==row['sha256'],'compiled source/class/resource binding')
   if row['path'].endswith('.class'):require(blob[:4]==b'\xca\xfe\xba\xbe' and int.from_bytes(blob[6:8],'big')==65 and b'net/fabricmc/' not in blob and b'net/neoforged/' not in blob,'Java21 native class boundary')
  for n in ['quilt.mod.json','infinity_native_quilt_probe.mixins.json','native-quilt-proof.txt']:require(z.read(n)==(fixture/'resources'/n).read_bytes(),'native source resource unchanged')
  require(len(d['negativeControls'])==2 and {x['case'] for x in d['negativeControls']}==set(c['negativeControls']),'both distinct negative controls')
  for row in d['negativeControls']:
   check_file(row,c['negativeControls'][row['case']]);require(row['runtimeRejectionNotRun'] is True,'negative runtime not established')
   with zipfile.ZipFile(row['path']) as negative:
    require(negative.namelist()==z.namelist(),'negative archive inventory')
    for n in z.namelist():
     if n!='quilt.mod.json':require(negative.read(n)==z.read(n),'negative only changes descriptor')
 require(d['classFiles']==c['classFiles'] and d['jarEntries']==c['jarEntries'] and d['abiChecks']==c['abiChecks'],'reviewed exact class/ABI inventories')
 limits=c['limits'];javac=[str(jdk/'bin/javac'),*['-J'+x for x in limits],'-proc:none','--release','21','-encoding','UTF-8','-implicit:none','-sourcepath',str(out/'empty')];java=[str(jdk/'bin/java'),*limits];sources=sorted((fixture/'src').rglob('*.java'));require(len(sources)==3,'source roster')
 expected=[('compile-tools',[*javac,'-cp',os.pathsep.join(map(str,[roles['art'],*remap_tools])),'-d',str(out/'tools'),str(T/'RemapServer.java'),str(T/'AbiCheck.java')]),('derive-real-server',[*java,'-cp',os.pathsep.join(map(str,[out/'tools',*remap_tools])),'RemapServer',str(mapping),game['embeddedEntry']['path'],game['path'],str(out/'remap-libraries.txt')])]
 for i in [1,2]:expected.append(('compile-fixture-'+str(i),[*javac,'-verbose','-cp',os.pathsep.join(map(str,closure)),'-d',str(out/('classes-'+str(i))),*map(str,sources)]))
 expected.append(('actual-abi',[*java,'-cp',str(out/'tools')+os.pathsep+str(roles['art']),'AbiCheck',str(artifact),str(out/'compile-classpath.txt')]))
 require(len(d['phases'])==5,'complete executed phase count')
 for row,(name,argv) in zip(d['phases'],expected):
  require(row['name']==name and row['argv']==argv and type(row['exitCode']) is int and row['exitCode']==0 and row['reaped'] is True and row['groupGone'] is True,'actual command/exits/cleanup binding '+name)
  require(all(type(row[k]) in (int,float) for k in ['timeoutSeconds','elapsedSeconds']) and all(type(row[k]) is int and row[k]>0 for k in ['pid','pgid','sid','cleanupOwnerPid']) and row['pid']==row['pgid']==row['sid'] and row['cleanupOwnerPid']!=row['pid'],'typed owned process identity');require(0<row['timeoutSeconds']<=120 and 0<=row['elapsedSeconds']<=row['timeoutSeconds']+9,'bounded phase');check_file(row['log']);require(row==load_json(out/(name+'.process.json')),'independent process record '+name)
 require((out/'derive-real-server.log').read_text()=='NATIVE_TINYREMAPPER_OFFICIAL_TO_INTERMEDIARY_COMPILE_CLASSES_ONLY PASS\n','native remapper completed without conflict warnings')
 abi=(out/'actual-abi.log').read_text();require([s for s in abi.splitlines() if s.startswith(('METHOD ','FIELD '))]==c['abiChecks'] and abi.rstrip().endswith('ACTUAL_CLASSFILE_ABI_BINDING classes=5 members=61 PASS'),'executed actual ABI pass')
 for i in [1,2]:
  text=(out/('compile-fixture-'+str(i)+'.log')).read_text();require(all(str(s) in text for s in sources),'compiler actually read all original sources')
  for row in c['classFiles']:check_file(pin(out/('classes-'+str(i))/row['path']),row)
 require({pathlib.Path(x['path']).name for x in d['tools']}=={'RemapServer.java','AbiCheck.java','build_recovery.py','portable_io.py'},'runtime tool references')
 for row in d['tools']:check_file(row,tools[pathlib.Path(row['path']).name])
 return {'schema':1,'status':'PASS_PORTABLE_COMPILE_SEMANTICS','scope':'COMPILE_ABI_ONLY_DIAGNOSTIC','independentlyReviewedContractSha256':contract_sha,'reviewedContract':pin(contract_path),'compileReceipt':pin(receipt),'artifact':d['artifact'],'sourceManifest':d['sourceManifest'],'sourceArchive':d['sourceArchive'],'sourceFiles':d['sourceFiles'],'artifactClasses':5,'actualResolvedMembers':61,'realGameClasses':6148,'runtimeAcceptance':False,'gameLaunched':False,'callerMustReviewContractIndependently':True,'validator':pin(__file__)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--receipt',required=True,type=pathlib.Path);p.add_argument('--contract',required=True,type=pathlib.Path);p.add_argument('--contract-sha256',required=True);p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args();a.output=canonical(a.output,missing=True);require(not a.output.exists(),'fresh validator output');r=validate(a.receipt,a.contract,a.contract_sha256);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
