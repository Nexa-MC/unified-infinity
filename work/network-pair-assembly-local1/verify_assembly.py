#!/usr/bin/env python3
"""Rehash exact assembled roles and official assets/native entries. No process starts."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import assemble_pairs as a

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--assembly',type=Path,required=True);parser.add_argument('--result-sha256',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result_path=args.assembly/'assembly-result.json'
    a.require(a.sha(result_path)==args.result_sha256,'Assembly result pin mismatch')
    result=json.loads(result_path.read_text());seen={};roles=[]
    for target,group in result['groups'].items():
        for side,seal in group['roles'].items():
            p=Path(seal['path']);a.require(a.pin(p)==seal,'Changed launch role seal');row=json.loads(p.read_text())
            for pin in row['files']:
                if pin['path'] not in seen:seen[pin['path']]=a.pin(Path(pin['path']))
                a.require(seen[pin['path']]==pin,'Changed assembled input')
            profile=Path(row['cwd']);a.require(not (profile/'world').exists(),'Unexpected started world')
            a.require(len(list((profile/'mods').iterdir()))==4,'Changed four-mod fixture')
            a.validate_command(row['command'],side,profile,group['port'],row['files'])
            roles.append({'target':target,'side':side,'launchSeal':seal,'inputCount':len(row['files']),
                          'actualModCount':4,'worldAbsent':True,'sourceOwnedAssemblyValidated':bool(row['assembly'] and row['assembly']['status']=='validated-before-jvm')})
    index=a.ASSETS/'indexes/17.json';raw=index.read_bytes()
    a.require(hashlib.sha1(raw).hexdigest()=='9b16298b1dc0697878cec88bb2d96168f5239e4f','Official asset index identity differs')
    objects=json.loads(raw)['objects'];unique={};asset_pins=[a.pin(index)]
    for row in objects.values():
        h=row['hash'];a.require(h not in unique or unique[h]==row['size'],'Asset index conflicting object size');unique[h]=row['size']
    for h,size in sorted(unique.items()):
        p=a.ASSETS/'objects'/h[:2]/h;record=a.pin(p)
        a.require(record['bytes']==size,'Official asset size differs')
        with p.open('rb') as stream:a.require(hashlib.file_digest(stream,'sha1').hexdigest()==h,'Official asset SHA1 differs')
        asset_pins.append(record)
    a.require({str(p) for p in a.ASSETS.rglob('*') if p.is_file()}=={p['path'] for p in asset_pins},'Unexpected asset-tree file')
    client=json.loads(a.CLIENT_SEAL.read_text());native_entries=[]
    for row in client['nativeLibraries']['jars']:
        archive=Path(row['jar']['path']);a.require(a.sha(archive)==row['jar']['sha256'],'Native archive pin differs')
        with zipfile.ZipFile(archive) as z:
            for name,digest in row['entries'].items():
                data=z.read(name);a.require(hashlib.sha256(data).hexdigest()==digest,'Official native entry changed')
                native_entries.append({'archive':str(archive),'entry':name,'bytes':len(data),'sha256':digest})
    report={'schema':1,'status':'ASSEMBLY_AND_CLIENT_INPUTS_VERIFIED_GAME_UNRUN','assemblyResult':a.pin(result_path),'roles':roles,
            'uniqueRoleInputFiles':len(seen),'logicalAssetRecords':len(objects),'uniqueAssetObjects':len(unique),'assetBytes':sum(unique.values()),
            'assetPins':asset_pins,'nativeArchiveEntryCount':len(native_entries),'nativeEntries':native_entries,
            'gameLaunched':False,'jvmStarted':False,'coldCiReconstructionProven':False,'actualWireAcceptance':False}
    a.save(args.output,report)
    print(json.dumps({k:report[k] for k in ['status','uniqueRoleInputFiles','logicalAssetRecords','uniqueAssetObjects','assetBytes','nativeArchiveEntryCount']},indent=2))
    print(json.dumps({'receipt':a.pin(args.output)},indent=2))

if __name__=='__main__':main()
