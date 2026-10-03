#!/usr/bin/env python3
"""Seal isolated final sources and receipts; does not integrate or execute Java."""
import datetime,difflib,hashlib,json,pathlib,zipfile
H=pathlib.Path(__file__).resolve().parent;R=H.parents[1];W=R/'source-workspace/forge-config-c1';S=W/'src/main/java';B=H/'build'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((W/'base-manifest.json').read_text());assert sha(R/manifest['archive'])==manifest['archive_sha256'];origins={x['path']:x['archive_member'] for x in manifest['selected']}
for x in manifest['selected']:assert sha(R/x['archive_member'])==x['sha256'],'Canonical source changed: '+x['archive_member']
for receipt in [B/'receipt.json',B/'real-integrations/receipt.json']:
 d=json.loads(receipt.read_text());assert 'PASS' in d['status'],d['status']
 for name,expected in d['sources'].items():assert sha(R/name)==expected,'Final source differs from tested receipt: '+name
patch=[];changes=[]
for p in sorted(S.rglob('*.java')):
 rel=p.relative_to(S).as_posix();old=W/'base'/rel;before=old.read_text() if old.exists() else ''
 if p.read_text()==before:continue
 target=origins.get(rel,('source-workspace/fml-unified/src/main/java/' if rel.startswith('net/neoforged/fml/') else 'source-workspace/connector-four-loader/components/infinity-forge/src/main/java/')+rel)
 patch.extend(difflib.unified_diff(before.splitlines(keepends=True),p.read_text().splitlines(keepends=True),fromfile='a/'+target if old.exists() else '/dev/null',tofile='b/'+target))
 changes.append({'candidate':str(p.relative_to(R)),'proposedIntegrationPath':target,'sha256':sha(p),'baseSha256':sha(old) if old.exists() else None})
(W/'patches/c1-unmerged.patch').write_text(''.join(patch));(W/'proposed-source-changes.json').write_text(json.dumps({'status':'UNMERGED_GAME_RUNTIME_UNVERIFIED','files':changes},indent=2)+'\n')
derived=[]
for original,candidate in [('docs/api-coverage/forge-config/sources/net/minecraftforge/common/ForgeConfigSpec.java','org/sinytra/connector/forge/config/ForgeConfigSpec.java'),('docs/api-coverage/forge-config/sources/net/minecraftforge/fml/config/IConfigSpec.java','org/sinytra/connector/forge/config/IForgeConfigSpec.java')]:
 derived.extend(difflib.unified_diff((R/original).read_text().splitlines(keepends=True),(S/candidate).read_text().splitlines(keepends=True),fromfile='a/'+original,tofile='b/'+str((S/candidate).relative_to(R))))
(W/'patches/upstream-forge-derivation.patch').write_text(''.join(derived))
files=[]
for base in [W,H]:
 for p in sorted(base.rglob('*')):
  if not p.is_file() or any(x in p.relative_to(base).parts for x in ['build','__pycache__']) or p.name in ['final-handoff.json']:continue
  files.append(p)
archive=B/'final-source-only.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files:
  info=zipfile.ZipInfo(str(p.relative_to(R)),date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
evidence=[B/'canonical-preservation-final.json',B/'static-final-results.json',B/'candidate-abi.json',B/'receipt.json',B/'official-inputs/receipt.json',B/'official-inputs/static-reference-results.json',B/'real-integrations/receipt.json',B/'real-integrations/watch-bus.log',B/'real-integrations/transform.log',B/'real-integrations/attempt-001/receipt.json',B/'native-baseline/receipt.json',B/'native-baseline/barrier-false.log',B/'native-baseline/barrier-true.log',B/'failure-order-before-fix/receipt.json',B/'failure-order-before-fix/failure-order.log',B/'failure-order.log',B/'run-003-final/tested-sources.zip']
report={'schema':1,'status':'SOURCE_AND_PURE_JVM_VERIFIED_UNMERGED_GAME_UNVERIFIED','sealedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'baseSourceArchive':{'path':manifest['archive'],'sha256':manifest['archive_sha256'],'entries':736},'sourceArchive':{'path':str(archive.relative_to(R)),'sha256':sha(archive),'entries':len(files)},'patch':{'path':str((W/'patches/c1-unmerged.patch').relative_to(R)),'sha256':sha(W/'patches/c1-unmerged.patch'),'changedOrAddedSourceFiles':len(changes)},'checks':{'sourceStatic':6,'boundaryStatic':12,'candidateExactSymbols':29,'independentOfficialInputClasses':2,'actualTransformerAcceptedClasses':2,'actualTransformerRejectedClasses':22,'deterministicOwnerAssertions':107,'realNativeBusWatcherAssertions':21,'failureOrder':'PASS: original and candidate WritingException, cached4, raw6, persisted4; successful cache commit runs after save under same native lock'},'failedEvidencePreserved':['Initial real watcher test missed first write before asynchronous registration acknowledgement; unchanged frozen native owner reproduced it. Both succeed with a no-op removeWatchFuture control-queue acknowledgement.','Pre-fix candidate returned cached6 after failed synchronous save while original Forge retained cached4; final source fixes this and retains original outward WritingException.'],'canonicalPreservation':json.loads((B/'canonical-preservation-final.json').read_text()),'noCanonicalChanges':True,'noGameLaunch':True,'noProductionAdmission':True,'noGitMutation':True,'javaMaxHeapMiB':512,'javaActiveProcessors':1,'finalSourceHashes':{str(p.relative_to(R)):sha(p) for p in files},'evidence':{str(p.relative_to(R)):sha(p) for p in evidence},'remainingRisks':['Actual transformed mod constructor injection, Loading-before-common-setup timing, module/classloader linking and assembled Minecraft runtime remain unverified.','Real watcher proof acknowledges registration before the first edit; inherited upstream async registration can miss an immediate edit and remains unchanged in production.','Full assembly/rebase and review of neutral FML policy hook remain before integration; canonical transformer, source artifacts, launch profiles and admission ledger remain untouched.','SERVER/CLIENT/legacy context/raw tracker/direct constructors/custom specs/public unload/sync and omitted builder methods remain explicitly unsupported.']}
(W/'final-handoff.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['status','sourceArchive','patch','checks']},indent=2))
