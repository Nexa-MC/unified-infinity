#!/usr/bin/env python3
"""Reconstruct an ordinary pinned source clone; linked worktrees break upstream JGit."""
import hashlib,json,pathlib,shutil,subprocess,sys,zipfile
base=pathlib.Path(__file__).resolve().parent;lock=json.loads((base/'source-lock.json').read_text())
name=sys.argv[1] if len(sys.argv)>1 else 'connector-combined'
if '/' in name or name in ('.','..'):raise SystemExit('Use a new direct child directory name')
target=base/name
if target.exists():raise SystemExit(f'Refusing to overwrite existing tree: {target}')
for rel,expected in lock['files'].items():
 if hashlib.sha256((base/rel).read_bytes()).hexdigest()!=expected:raise SystemExit(f'Input digest mismatch: {rel}')
repo=base/'connector';pin=lock['connector_commit']
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==pin
subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(repo),str(target)],check=True)
subprocess.run(['git','-C',str(target),'checkout','--detach',pin],check=True)
for component,filename,license_file,license_name in [('infinity-fart','ForgeAutoRenamingTool-1.0.14-sources.jar','FART-LICENSE.txt','LICENSE-FART-LGPL-2.1.txt'),('infinity-adapter','adapter-core-2.0.43+1.21.1-sources.jar','Adapter-LICENSE.txt','LICENSE-Adapter-MIT.txt')]:
 archive=base/'upstream'/filename
 with zipfile.ZipFile(archive) as z:
  for n in z.namelist():
   if not n.endswith('.java'):continue
   if n.startswith('/') or '..' in pathlib.PurePosixPath(n).parts:raise ValueError(n)
   f=target/f'components/{component}/src/main/java'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(n))
 resources=target/f'components/{component}/src/main/resources/META-INF/unified-infinity';resources.mkdir(parents=True,exist_ok=True)
 if component=='infinity-fart':shutil.copy2(archive,resources/archive.name)
 shutil.copy2(base/'upstream'/license_file,resources/license_name)
for p in sorted((base/'patches').glob('*.patch')):
 subprocess.run(['git','-C',str(target),'apply','--check',str(p)],check=True)
 subprocess.run(['git','-C',str(target),'apply',str(p)],check=True)
print(f'Prepared {target}; no build or game launch was performed')
