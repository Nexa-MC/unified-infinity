#!/usr/bin/env python3
"""Verify pinned static research inputs. Never load JVM/mod code."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APPROVED_MOD = 'Clumps-forge-1.21.1-19.0.0.1.jar'
APPROVED_MOD_SHA256 = 'e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19'

def verify(records):
    for record in records:
        path = ROOT / record['path']
        if path.name == APPROVED_MOD:
            assert record['sha256'] == APPROVED_MOD_SHA256
            approved = json.loads((HERE / 'candidate-lock.json').read_text())
            assert approved['status'] == 'approved-hash-verified-static-inspection-complete'
        raw = path.read_bytes()
        assert len(raw) == record['size'], f'Size mismatch: {path}'
        assert hashlib.sha256(raw).hexdigest() == record['sha256'], f'Hash mismatch: {path}'

source = json.loads((HERE / 'source-lock.json').read_text())
assert not any('error' in row for row in source['artifacts'])
verify(source['artifacts'])
inspection = json.loads((HERE / 'inspection-lock.json').read_text())
verify(inspection['files'])
records = {Path(row['path']).name: row for row in source['artifacts']}
assert records['forge-1.21.1-52.1.0-installer.jar']['sha1'] == 'fa4f90047c23e6df4d2b4e649aec7fd5d1e20acd'
assert records['forge-1.21.1-52.1.0-mdk.zip']['sha1'] == 'a081da53578f1bd9b053cf7d65dbe9e95d2b351c'
print(json.dumps({'status': 'passed', 'source_artifacts': len(source['artifacts']),
                  'inspection_files': len(inspection['files']),
                  'runtime_or_mod_execution': False,
                  'approved_mod_hash_verified': True}, indent=2))
