"""Qualify real compile outputs, never generate replacement production identity/classes."""
from pathlib import Path
import hashlib,json,re,struct

def qualified_exit(child_exit, source_unchanged, outputs_present, identity_valid, hook_valid):
 return 0 if child_exit==0 and all([source_unchanged,outputs_present,identity_valid,hook_valid]) else (child_exit or 1)

def class_has_install_call(data):
 try:
  if data[:4]!=b'\xca\xfe\xba\xbe' or int.from_bytes(data[6:8],'big')!=65:return False
  count=int.from_bytes(data[8:10],'big');cp=[None]*count;p=10;i=1
  while i<count:
   tag=data[p];p+=1
   if tag==1:
    size=int.from_bytes(data[p:p+2],'big');p+=2;cp[i]=(tag,data[p:p+size].decode('utf-8'));p+=size
   elif tag in (7,8,16,19,20):cp[i]=(tag,int.from_bytes(data[p:p+2],'big'));p+=2
   elif tag in (9,10,11,12,17,18):cp[i]=(tag,int.from_bytes(data[p:p+2],'big'),int.from_bytes(data[p+2:p+4],'big'));p+=4
   elif tag in (3,4):p+=4
   elif tag in (5,6):p+=8;i+=1
   elif tag==15:p+=3
   else:return False
   i+=1
  def utf(k):return cp[k][1]
  def cls(k):return utf(cp[k][1])
  this=int.from_bytes(data[p+2:p+4],'big')
  if cls(this)!='org/sinytra/connector/mod/FmlGameCompatibilityComponent':return False
  for row in cp:
   if row and row[0]==10:
    nt=cp[row[2]]
    if cls(row[1])=='org/sinytra/connector/forge/runtime/network/ForgePlayNetwork' and utf(nt[1])=='install' and utf(nt[2])=='(Lnet/neoforged/bus/api/IEventBus;)V':return True
  return False
 except (IndexError,KeyError,TypeError,UnicodeError):return False

def verify_identity(root,core,source_receipt,core_lock,required_changes,java_release):
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 m=core/'components/infinity-core/build/generated/resources/infinity/META-INF/unified-infinity/build-identity.json'
 j=core/'components/infinity-core/build/generated/sources/infinity/java/org/sinytra/connector/infinity/BuildIdentity.java'
 data=json.loads(m.read_text());allowed={}
 for row in source_receipt['sourceFilesCopiedWithExactHashes']:
  p=root/row['path']
  try:relative=p.relative_to(core).as_posix()
  except ValueError:
   try:relative='loader-sources/'+p.relative_to(core.parent).as_posix()
   except ValueError:continue
  allowed[relative]=(p,row['sha256'])
 seen=set();digest=hashlib.sha256()
 for row in data['sources']:
  path=row['path'];assert path not in seen and path in allowed;seen.add(path);p,h=allowed[path]
  assert row['sha256']==h==sha(p)
  digest.update(path.encode());digest.update(b'\0');digest.update(p.read_bytes());digest.update(b'\0')
 assert [r['path'] for r in data['sources']]==sorted(seen)
 for row in required_changes:assert row['path'] in seen and allowed[row['path']][1]==row['candidateSha256']
 candidates={(r['filename'],r['sha256']):root/'work/api1'/r['path'] for r in core_lock['artifacts']}
 names=[]
 for row in data['dependencies']:
  p=candidates[(row['filename'],row['sha256'])];assert sha(p)==row['sha256'];names.append(row['filename']);digest.update(row['filename'].encode());digest.update(b'\0');digest.update(p.read_bytes());digest.update(b'\0')
 assert names==sorted(names)
 expected=re.search(r'^JAVA_RUNTIME_VERSION="([^"]+)"$',java_release.read_text(),re.M).group(1);assert data['compiler_runtime']==expected;digest.update(expected.encode());h=digest.hexdigest();assert data['identity_sha256']==h
 expected_java='package org.sinytra.connector.infinity;\npublic final class BuildIdentity {\nprivate BuildIdentity() {}\npublic static final String SOURCE_SHA256 = "'+h+'";\npublic static final String TRANSFORM_CACHE_SUFFIX = ":unified-infinity-full-source:'+h+'";\n}\n';assert j.read_text()==expected_java
 return {'verified':True,'identitySha256':h,'sourceCount':len(seen),'dependencyCount':len(names),'allSevenReviewedChangesIncluded':True,'compilerRuntime':expected}
