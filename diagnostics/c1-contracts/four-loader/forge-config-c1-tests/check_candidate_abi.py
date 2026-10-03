#!/usr/bin/env python3
"""Static facade correspondence. Does not transform, link or run input mods."""
import json,pathlib,re,sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'boundary'))
from c1_boundary import load_proposal,parse_classfile,resolve_member
p=load_proposal();mapping={x['owner']:x['target'] for x in p['types']};mapping['net/minecraftforge/fml/javafmlmod/FMLJavaModLoadingContext']=p['existing_dependencies']['context_target']
classes={}
for file in (HERE/'build/classes').rglob('*.class'):
 c=parse_classfile(file.read_bytes());classes[c['name']]=c
checks=[]
for item in p['methods']+p['fields']:
 desc=re.sub(r'L([^;]+);',lambda m:'L'+mapping.get(m[1],m[1])+';',item['descriptor'])
 target=mapping[item['owner']];found=resolve_member(classes,target,item['kind'],item['name'],desc)
 assert found is not None,(item,target,desc)
 assert found[1]['access']&1,item
 checks.append({'original':item['transformer_key'],'target':target+'.'+item['name']+desc,'resolvedOwner':found[0]})
report={'status':'PASS','checks':checks,'count':len(checks),'runtimeLinked':False,'productionAdmissionChanged':False}
(HERE/'build/candidate-abi.json').write_text(json.dumps(report,indent=2)+'\n')
print('Candidate compiled ABI matches all',len(checks),'proposed exact symbols')
