#!/usr/bin/env python3
"""Install exact official Quilt server runtime; never launches Minecraft."""
import hashlib,json,os,pathlib,shutil,subprocess,urllib.parse
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROFILE=ROOT/'run/quilt-native-probe'
PROVENANCE=HERE/'provenance'
INSTALLER=PROVENANCE/'quilt-installer-0.15.1.jar'
assert hashlib.sha256(INSTALLER.read_bytes()).hexdigest() == (PROVENANCE/'quilt-installer-0.15.1.sha256').read_text().strip()
assert not (PROFILE/'world').exists()
PROFILE.mkdir(parents=True,exist_ok=True)
manifest=ROOT/'source-workspace/gradle-cache/caches/neoformruntime/artifacts/minecraft_1.21.1_version_manifest.json'
download=json.loads(manifest.read_text())['downloads']['server']
source=ROOT/'run/fabric-native/server.jar'
assert hashlib.sha1(source.read_bytes()).hexdigest() == download['sha1']
shutil.copy2(source,PROFILE/'server.jar')
proxy=urllib.parse.urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY',''))
options=['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
if proxy.hostname:
 for scheme in ('http','https'): options += [f'-D{scheme}.proxyHost={proxy.hostname}',f'-D{scheme}.proxyPort={proxy.port}']
command=[str(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'),*options,'-jar',str(INSTALLER),'install','server','1.21.1','0.30.1',f'--install-dir={PROFILE}']
with (HERE/'installer.log').open('w') as log:
 result=subprocess.run(command,cwd=PROFILE,stdout=log,stderr=subprocess.STDOUT,timeout=600)
print(json.dumps({'exit_code':result.returncode,'log':str(HERE/'installer.log'),'minecraft_server':download}))
raise SystemExit(result.returncode)
