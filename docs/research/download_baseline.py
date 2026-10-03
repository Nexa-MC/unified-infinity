#!/usr/bin/env python3
"""Download only the three locked public artifacts; never install or launch them.

Usage: python docs/research/download_baseline.py --output .cache/baseline
No Mojang game assets, EULA acceptance, runtime execution, or credentials involved.
"""
import argparse, hashlib, json, pathlib, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--lock',type=pathlib.Path,default=ROOT/'baseline-lock.json')
p.add_argument('--output',type=pathlib.Path,required=True)
args=p.parse_args()
lock=json.loads(args.lock.read_text())
args.output.mkdir(parents=True,exist_ok=True)
for a in lock['artifacts']:
    name=a.get('download_filename',a['filename'])
    if pathlib.Path(name).name != name:
        raise SystemExit('Unsafe filename in lock')
    target=args.output/name
    if target.exists():
        data=target.read_bytes()
        if hashlib.sha256(data).hexdigest()!=a['sha256']:
            raise SystemExit(f'Existing file hash mismatch: {target}; left unchanged')
        print(f'VERIFIED {target}')
        continue
    with urllib.request.urlopen(a['url'],timeout=90) as response:
        data=response.read()
    digest=hashlib.sha256(data).hexdigest()
    if digest!=a['sha256'] or len(data)!=a['size']:
        raise SystemExit(f'Integrity failure for {a["id"]}: got sha256={digest}, bytes={len(data)}')
    # Exclusive creation avoids overwriting a concurrent writer or user data.
    with target.open('xb') as stream:
        stream.write(data)
    print(f'DOWNLOADED {target} sha256={digest}')
