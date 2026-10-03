#!/usr/bin/env python3
"""Stage exact original closure for official Loom remapping, with no game launch."""
import io, json, pathlib, shutil, zipfile
from verify_profile import ROOT, PROFILE, PINNED_MODS, checked, digest

report_path=PROFILE/'seed-report.json'
report=json.loads(report_path.read_text())
if report.get('profileMode')=='loom_named_classpath':
    raise SystemExit('Named inputs already staged; verify rather than repeating the transition.')
archive=PROFILE/'archive/client-2-original-profile'
archive.mkdir(parents=True,exist_ok=False)
shutil.copy2(report_path,archive/'seed-report.json')
records=[]
for record in report['mods']:
    original=ROOT/record['source'];name=original.name
    checked(original,PINNED_MODS[name]);checked(ROOT/record['path'],PINNED_MODS[name])
    target=PROFILE/'original-mods'/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(original,target);checked(target,PINNED_MODS[name])
    record['path']=str(target.relative_to(ROOT))
    records.append({'source':record['source'],'path':record['path'],'sha256':record['sha256']})
    with zipfile.ZipFile(original) as z:
        if 'fabric.mod.json' not in z.namelist():continue
        metadata=json.loads(z.read('fabric.mod.json'))
        for item in metadata.get('jars',[]):
            entry=item['file'];data=z.read(entry);name=pathlib.PurePosixPath(entry).name
            target=PROFILE/'original-nested-mods'/name
            if target.exists():raise RuntimeError(f'Duplicate extracted input: {name}')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            records.append({'source':record['source']+'!/'+entry,'path':str(target.relative_to(ROOT)),'sha256':digest(target)})
if len(records)!=52:raise RuntimeError(f'Original closure count changed: {len(records)}')
original_closure=json.loads((ROOT/'four-loader/quilt-native-client/provenance/mod-closure.json').read_text())
if sorted(r['sha256'] for r in records)!=sorted(r['sha256'] for r in original_closure):raise RuntimeError('Staged closure differs from approved originals')
shutil.move(str(PROFILE/'game/mods'),str(archive/'mods'))
(PROFILE/'game/mods').mkdir()
report['profileMode']='loom_named_classpath'
report['loomInputClosure']=records
report_path.write_text(json.dumps(report,indent=2)+'\n')
(PROFILE/'loom-original-inputs.json').write_text(json.dumps(records,indent=2)+'\n')
print('Staged 52 unchanged original direct/nested inputs for official Loom. No game launch or Gradle invocation.')
