#!/usr/bin/env python3
"""Replay the unmodified official client installer inside this isolated profile."""
import hashlib,json,os,pathlib,shutil,subprocess,urllib.parse,zipfile
root=pathlib.Path(__file__).resolve().parents[2]
client=root/'run/client-dev';installer=root/'docs/research/upstream/neoforge-21.1.219-installer.jar'
client.mkdir(parents=True,exist_ok=True)
profiles=client/'launcher_profiles.json'
if not profiles.exists():profiles.write_text('{"profiles":{},"settings":{}}\n')
with zipfile.ZipFile(installer) as z:
 for data in [json.loads(z.read('install_profile.json')),json.loads(z.read('version.json'))]:
  for lib in data['libraries']:
   a=lib.get('downloads',{}).get('artifact',{});rel=a.get('path')
   if not rel:continue
   src=root/'run/neoforge-native/libraries'/rel;dest=client/'libraries'/rel
   if src.is_file() and not dest.exists() and (not a.get('sha1') or hashlib.sha1(src.read_bytes()).hexdigest()==a['sha1']):
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
p=urllib.parse.urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY',''));opts=['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
if p.hostname:
 for scheme in ['http','https']:opts.extend([f'-D{scheme}.proxyHost={p.hostname}',f'-D{scheme}.proxyPort={p.port}'])
work=client/'installer-work';work.mkdir(exist_ok=True)
cmd=[str(root/'.toolchains/jdk-21.0.12.1+1/bin/java'),*opts,'-jar',str(installer),'--installClient',str(client)]
raise SystemExit(subprocess.call(cmd,cwd=work))
