#!/usr/bin/env python3
"""Stage exact approved four-loader client; preserve previous accepted game tree. Never launch."""
import hashlib,json,pathlib,shutil,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
GAME=ROOT/'run/client-dev/development-game'
ARCHIVE=ROOT/'run/client-dev/archived-07-mixed-pack-world-game'
EVIDENCE=ROOT/'four-loader/unified-client/evidence'
SOURCES=[
('source-workspace/artifacts/unified-infinity-four-loader-98d86a92.jar','98d86a92e91a20df980cc95abc8ced4972476edff7ec982d08c88e3d4e8579fd'),
('runtime-bundle/build-quilt-range-candidate/libs/unified-infinity-0.1.0-dev.jar','746ca5e3fcaf64ae7b67836535d8aa0bcb5d1cb4fe37161cc811784cca5adbd4'),
('preload-ui/build/libs/unified-infinity-preload-0.1.0-dev.jar','7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99'),
('docs/real-mod-trial/lithium-fabric-0.15.4+mc1.21.1.jar','92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa'),
('mixed-pack/research/archives/Chunky-Fabric-1.4.23.jar','3412b170247dde7351e0945d857e713bedf6fae05ab300aa74d06ffbde0ca07e'),
('mixed-pack/research/archives/FarmersDelight-1.21.1-1.3.4.jar','139ad7696462c89c03eea463f805abffa552526c5dadaadae221dd9624cb197c'),
('docs/four-loader/forge/upstream/Clumps-forge-1.21.1-19.0.0.1.jar','e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19'),
('docs/four-loader/quilt/candidates/optab-2.0.0V1.21.1+1.21.jar','6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def main():
 if sys.argv[1:]!=['--stage']:raise SystemExit('Explicit --stage required; no game launch')
 if ARCHIVE.exists() or EVIDENCE.exists():raise SystemExit('Prior transition exists; do not overwrite')
 prior=json.loads((GAME/'profile-mods.lock.json').read_text())
 assert prior['test']=='07-mixed-pack-world','Unexpected prior profile'
 for m in prior['mods']:assert sha(ROOT/m['path'])==m['sha256'],'Prior profile mutated'
 for p,h in SOURCES:assert sha(ROOT/p)==h,'New input digest mismatch: '+p
 EVIDENCE.mkdir(parents=True)
 dump(EVIDENCE/'previous-profile-lock.json',prior)
 shutil.copy2(ROOT/'logs/client-setup-baseline-lock.json',EVIDENCE/'previous-baseline-lock.json')
 GAME.rename(ARCHIVE)
 (GAME/'mods').mkdir(parents=True)
 shutil.copytree(ARCHIVE/'config',GAME/'config')
 shutil.copy2(ARCHIVE/'options.txt',GAME/'options.txt')
 qa=ROOT/'preload-ui/reports/client-qa-next'
 if qa.exists():qa.rename(EVIDENCE/'previous-qa')
 mods=[]
 for p,h in SOURCES:
  src=ROOT/p;dst=GAME/'mods'/src.name;shutil.copy2(src,dst);assert sha(dst)==h
  mods.append({'path':str(dst.relative_to(ROOT)),'source':p,'sha256':h,'bytes':dst.stat().st_size})
 lock={'test':'08-four-loader-real-client','state':'STAGED, NOT LAUNCHED','launchRoute':'official ModDevGradle offline forgeclientdev','modCountDirect':len(mods),'mods':mods,'priorGameArchive':str(ARCHIVE.relative_to(ROOT)),'accountCredentialsReadOrSupplied':False,'externalGameServerConnections':False,'gameLaunched':False,'scope':'Approved real Fabric Lithium+Chunky, NeoForge Farmers Delight, Forge Clumps, Quilt OP Tab; internal FFAPI/QSL base+lifecycle. No probe JARs.'}
 dump(GAME/'profile-mods.lock.json',lock);dump(EVIDENCE/'staged-inputs.json',lock)
 baseline=json.loads((EVIDENCE/'previous-baseline-lock.json').read_text());baseline['current_test']=lock['test'];baseline['launch_status']='STAGED, NOT LAUNCHED';baseline['artifacts']=[a for a in baseline['artifacts'] if '/development-game/mods/' not in a['path']]+mods
 dump(ROOT/'logs/client-setup-baseline-lock.json',baseline)
 print(json.dumps({'staged':True,'direct_jars':len(mods),'game_launched':False}))
if __name__=='__main__':main()
