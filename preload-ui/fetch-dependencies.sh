#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .deps
python3 - <<'PY'
import hashlib,json,pathlib,urllib.request
for item in json.loads(pathlib.Path('dependencies-lock.json').read_text())['dependencies']:
    target=pathlib.Path('.deps')/item['filename']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:
        print('Verified',target.name); continue
    data=urllib.request.urlopen(item['url'],timeout=30).read()
    if hashlib.sha256(data).hexdigest()!=item['sha256']: raise SystemExit('Checksum mismatch: '+item['filename'])
    target.write_bytes(data)
    print('Fetched and verified',target.name)
PY
