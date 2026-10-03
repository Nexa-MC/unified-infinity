#!/usr/bin/env python3
"""Compare every supplied Quilt public API class against pinned upstream, never load its engine."""
import difflib, hashlib, json, pathlib, re, subprocess, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
UPSTREAM = ROOT.parent.parent / 'docs/four-loader/quilt/upstream'
JDK = ROOT.parent.parent / '.toolchains/jdk-21.0.12.1+1/bin'
REFERENCE = UPSTREAM / 'loader-0.30.1.jar'
CLASSES = ROOT / 'four-loader/api-tests/classes'
assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == 'a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb'
with zipfile.ZipFile(REFERENCE) as archive: available = set(archive.namelist())
failures=[]; checked=[]
for path in sorted((CLASSES/'org/quiltmc/loader/api').rglob('*.class')):
    name=path.relative_to(CLASSES).as_posix()
    if re.search(r'\$\d', name): continue
    assert name in available, 'Unpinned API addition: '+name
    cls=name.removesuffix('.class').replace('/', '.')
    def signatures(classpath):
        out=subprocess.check_output([str(JDK/'javap'), '-classpath', str(classpath), '-public', '-s', cls], text=True)
        return sorted(line.strip() for line in out.splitlines() if line.strip().startswith(('public ', 'protected ', 'descriptor:')))
    a,b=signatures(REFERENCE),signatures(CLASSES)
    if a!=b: failures.append(cls+'\n'+'\n'.join(difflib.unified_diff(a,b)))
    checked.append(cls)
if failures: raise SystemExit('\n'.join(failures))
result={'result':'PASS','reference_sha256':hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),'classes_checked':len(checked),'classes':checked,'scope':'Public signatures/descriptors of supplied classes, not complete Loader implementation or runtime compatibility'}
(ROOT/'four-loader/api-tests/abi-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'PASS: {len(checked)} supplied API class public signatures/descriptors match Quilt Loader 0.30.1')
