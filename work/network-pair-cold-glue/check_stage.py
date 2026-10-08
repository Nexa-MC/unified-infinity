#!/usr/bin/env python3
"""Read-only verification of the exact diagnostic publication source closure."""
import hashlib
import json
from pathlib import Path
import source_materialize

ROOT=Path(__file__).resolve().parents[2]
manifest=json.loads((ROOT/'pair-publication-manifest.json').read_text())
expected={row['path'] for row in manifest['files']}
actual={str(path.relative_to(ROOT)) for path in ROOT.rglob('*') if path.is_file()
        and not set(path.relative_to(ROOT).parts).intersection({'.git','__pycache__'})
        and path.name!='pair-publication-manifest.json'}
# A diagnostic branch may retain the existing main tree. Every staged payload
# file is exact-pinned; unrelated pre-existing main files are not imported as inputs.
for row in manifest['files']:
    path=ROOT/row['path']
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=row['bytes']:
        raise ValueError('Missing or redirected publication input: '+row['path'])
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=row['sha256']:raise ValueError('Changed publication source: '+row['path'])
    if path.suffix.lower() in ('.class','.jar','.so','.dll','.exe','.pyc'):
        raise ValueError('Compiled binary in diagnostic publication')
for row in source_materialize._load_manifest()['archives'].values():
    path=ROOT/row['path'];source_materialize._source_only(path.read_bytes(),path.name)
print(json.dumps({'status':'PUBLICATION_SOURCE_VERIFIED','files':len(expected),
                  'sourceArchives':len(source_materialize._load_manifest()['archives']),'coldExecutionVerified':False,'downloads':False,'jvmStarted':False}))
