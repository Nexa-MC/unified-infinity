#!/usr/bin/env python3
"""Read actual class-origin and exclusion logs; no Java, archive scan, or trust registration."""
import argparse,collections,hashlib,json,pathlib,re,urllib.parse

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--profile',type=pathlib.Path,required=True);p.add_argument('--spec',type=pathlib.Path,required=True);p.add_argument('--receipt',type=pathlib.Path,required=True);args=p.parse_args()
    root=args.profile.resolve();spec=json.loads(args.spec.read_text());receipt=json.loads(args.receipt.read_text());assert str(root)==spec['gameDirectory'];assert sha(pathlib.Path(receipt['artifact']))==receipt['sha256']
    inputs={x['path']:x for x in spec['expectedExcludedInputs']};rows=[]
    pattern=r'WARNING: External (\S+) excluded before service selection: (.*); source=SourceChain\[installationRoot=(.*), embeddedEntries=\[(.*)\]\]; original archive unchanged'
    for line in (root/'fusion-client.log').read_text().splitlines():
        m=re.search(pattern,line)
        if m:rows.append({'id':m[1],'reason':m[2],'sourceRoot':m[3],'embeddedEntries':m[4].split(', ') if m[4] else []})
    assert len(rows)==len({json.dumps(x,sort_keys=True) for x in rows})==45
    assert {x['sourceRoot'] for x in rows}==set(inputs)
    class_rows=[];log_files=sorted(root.glob('class-origins.log*'))
    for log in log_files:
        for line in log.read_text().splitlines():
            m=re.search(r'\[class,load\] (\S+) source: (.*)',line)
            if m:class_rows.append({'class':m[1],'source':m[2]})
    forbidden=[x for x in class_rows if any(name in urllib.parse.unquote(x['source']) for name in inputs)];assert not forbidden
    roles={'org.sinytra.connector.infinity.inventory.AdmissionSession':'BOOT_OWNER','org.sinytra.connector.infinity.FmlCompatibilityComponent':'ADMISSION_CONSUMER','org.sinytra.connector.service.ConnectorLoaderService':'ADMISSION_CONSUMER','org.sinytra.connector.mod.FmlGameCompatibilityComponent':'COMPATIBILITY_GAME','org.sinytra.connector.mod.ConnectorMod':'COMPATIBILITY_GAME','dev.modcompat.runtime.bundle.RuntimeBundle':'PRODUCT_GAME'}
    key_classes={}
    for name,role in roles.items():
        hits=[x for x in class_rows if x['class']==name];assert len(hits)==1,(name,len(hits));origin=hits[0]['source'];m=re.fullmatch(r'union:(.+)%23\d+!/',origin);assert m,origin
        path=pathlib.Path(urllib.parse.unquote(m[1])).resolve();pin=next(x for x in spec['artifacts'] if x['role']==role);expected=(pathlib.Path(spec['installationDirectory'])/pin['path']).resolve();assert path==expected
        digest=sha(path);assert digest==(receipt['sha256'] if role=='BOOT_OWNER' else pin['sha256'])
        key_classes[name]={'definitions':1,'runtimeSource':origin,'physicalPath':str(path),'sha256':digest,'installedRole':role}
    api=[x for x in class_rows if x['class']=='net.fabricmc.fabric.api.event.EventFactory'];assert len(api)==1
    checked={pathlib.Path(x['path']):x['sha256'] for x in spec['userMods']+spec['expectedExcludedInputs']}
    checked.update({pathlib.Path(x['source']):x['sha256'] for x in spec['userMods']+spec['expectedExcludedInputs']});assert all(sha(p)==digest for p,digest in checked.items())
    session=json.loads((root/'launch-session.json').read_text());finished='exitCode' in session
    if finished:assert session['exitCode']==0 and session['originalInputsUnchanged']
    result={'status':'PASS' if finished else 'PASS_RUNNING_OBSERVATION','scope':'actual pre-service notices and pinned class definitions; native-only API temp paths are not mapped here, so denied nested-alias exclusion additionally relies on frozen decisions and actual trusted selected snapshot classifications; not a lifecycle invocation counter','clientExitCode':session.get('exitCode'),'logicalExclusionCount':len(rows),'bySource':dict(collections.Counter(x['sourceRoot'] for x in rows)),'exclusions':rows,'keyClassDefinitions':key_classes,'apiClassDefinition':api[0],'forbiddenOuterClassDefinitions':forbidden,'classDefinitionLinesObserved':len(class_rows),'classLogFiles':[str(x) for x in log_files],'originalInputsUnchanged':True,'launcherCheckedInputPaths':session.get('checkedInputPaths'),'specSha256':sha(args.spec),'receiptSha256':sha(args.receipt)}
    (root/'exclusion-provenance-observation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('exclusions','keyClassDefinitions')}))
if __name__=='__main__':main()
