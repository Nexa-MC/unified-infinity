#!/usr/bin/env python3
import difflib,hashlib,json,pathlib,subprocess,zipfile
base=pathlib.Path(__file__).resolve().parent;t=base/'connector-combined';out=base/'patches';out.mkdir(exist_ok=True)
tracked=['build.gradle.kts','settings.gradle.kts','transformer/build.gradle.kts']
build=subprocess.check_output(['git','-C',str(t),'diff','--',*tracked],text=True)
runtime=subprocess.check_output(['git','-C',str(t),'diff','--','src/main/java','transformer/src/main/java'],text=True)
def newfile(f):return ''.join(difflib.unified_diff([],f.read_text().splitlines(True),fromfile='/dev/null',tofile='b/'+f.relative_to(t).as_posix()))
for f in sorted((t/'components').rglob('*')):
 if not f.is_file() or 'build' in f.relative_to(t).parts:continue
 p=f.relative_to(t).as_posix()
 if p.endswith('.gradle.kts'):build+=newfile(f)
 elif p.endswith('.java') and not any(x in p for x in ['infinity-fart/src/main/java','infinity-adapter/src/main/java']):runtime+=newfile(f)
build+=newfile(t/'gradle/infinity-upstream-pins.json')
patches={'0001-source-build-layout.patch':build,'0002-owned-runtime-sources.patch':runtime}
for component,archive,name in [('infinity-fart','ForgeAutoRenamingTool-1.0.14-sources.jar','0003-fart-direct-entry.patch'),('infinity-adapter','adapter-core-2.0.43+1.21.1-sources.jar','0004-adapter-lithium-fixes.patch')]:
 chunks=[]
 with zipfile.ZipFile(base/'upstream'/archive) as z:
  for n in sorted(z.namelist()):
   if not n.endswith('.java'):continue
   rel=f'components/{component}/src/main/java/{n}';old=z.read(n).decode();new=(t/rel).read_text()
   if old!=new:chunks.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
 patches[name]=''.join(chunks)
for n,s in patches.items():(out/n).write_text(s)
inputs=[*sorted(out.glob('*.patch')),*sorted((base/'upstream').glob('*'))]
lock={'schema':2,'connector_url':'https://github.com/Sinytra/Connector','connector_commit':'8b27f1ad042aae8037bcc522b321c03fcce1a12a','connector_tag':'2.0.0-beta.17+1.21.1','status':'built-tested-repeatable-in-observed-cache','files':{p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()}}
(base/'source-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
print('Exported four digest-pinned source patches')
