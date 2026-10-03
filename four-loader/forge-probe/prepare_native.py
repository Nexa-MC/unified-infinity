#!/usr/bin/env python3
"""Run the official Forge installer in an isolated directory. Does not start Minecraft."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import urllib.parse
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROFILE = ROOT / 'run/forge-native-probe'
LOGS = ROOT / 'logs/forge-native-probe'
INSTALLER = ROOT / 'docs/four-loader/forge/upstream/forge-1.21.1-52.1.0-installer.jar'
assert hashlib.sha256(INSTALLER.read_bytes()).hexdigest() == 'f1b620f2879ad6a5bbe15daba4d8f81eab9f5e08004967604960b98996bdebc4'
PROFILE.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(INSTALLER) as archive:
    for entry in ('install_profile.json', 'version.json'):
        data = json.loads(archive.read(entry))
        for library in data['libraries']:
            artifact = library.get('downloads', {}).get('artifact', {})
            relative = artifact.get('path')
            if not relative:
                continue
            source = ROOT / 'run/neoforge-native/libraries' / relative
            dest = PROFILE / 'libraries' / relative
            if source.is_file() and not dest.exists() and artifact.get('sha1') == hashlib.sha1(source.read_bytes()).hexdigest():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
proxy = urllib.parse.urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY', ''))
options = ['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
if proxy.hostname:
    for scheme in ('http', 'https'):
        options += [f'-D{scheme}.proxyHost={proxy.hostname}', f'-D{scheme}.proxyPort={proxy.port}']
command = [str(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java'), *options,
           '-jar', str(INSTALLER), '--installServer', str(PROFILE)]
with (LOGS / 'installer.log').open('w') as log:
    result = subprocess.run(command, cwd=PROFILE, stdout=log, stderr=subprocess.STDOUT)
print(json.dumps({'exit_code': result.returncode, 'log': str(LOGS / 'installer.log')}))
raise SystemExit(result.returncode)
