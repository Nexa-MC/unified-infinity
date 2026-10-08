#!/usr/bin/env python3
"""Bind a sealed input base to genuine live graphics evidence; never start games."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from prepare_inputs import require, pin, load, save

# Filled with the reviewed final supervisor identity before source freeze.
SUPERVISOR_SHA = '01f3796c0d6e9c54a770375f0ae1cc3451a89074bb88934023f997f7c48dc1bf'

def merge_pins(left,right):
    result={r['path']:r for r in left}
    require(len(result)==len(left),'Duplicate prepared input')
    for row in right:
        if row['path'] in result:require(result[row['path']]==row,'Conflicting producer input pin')
        result[row['path']]=row
    return sorted(result.values(),key=lambda r:r['path'])

def add_owned_root(roots,path):
    path=Path(path)
    require(path.resolve()==path and path.is_dir() and path.stat().st_uid==os.geteuid(),'Producer root must be canonical and owned')
    if any(path.is_relative_to(Path(root)) for root in roots):return sorted(roots)
    require(not any(Path(root).is_relative_to(path) for root in roots),'Do not broaden an existing preparation root')
    return sorted([*roots,str(path)])

def bind(base,ready,ready_pin,review_reference):
    require(base['schema']=='prepared-network-ci-pair-v2' and base['status']=='NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE','Wrong prepared input state')
    require(ready['schema']==1 and ready['status']=='GRAPHICS_PREFLIGHT_READY' and ready['pair_acceptance'] is False,'Actual graphics-ready producer receipt required')
    require(isinstance(review_reference,str) and 0<len(review_reference)<=512 and '\n' not in review_reference,'Existing reviewed pair authorization reference required')
    spec={key:value for key,value in base.items() if key not in ('status','mutable_client_options_initially_pinned_in_role_receipt')}
    spec['schema']='network-ci-pair-v2'
    spec['authorization']=dict(base['authorization'],ci_pair_review_reference=review_reference)
    spec['inputs']=merge_pins(base['inputs'],[*ready['inputs'],ready_pin])
    spec['source_receipts']=[*base['source_receipts'],ready_pin['path']]
    spec['graphics']=ready['graphics']
    roots=list(base['preparation_roots'])
    for row in [*ready['inputs'],ready_pin]:
        path=Path(row['path'])
        if path.stat().st_uid==os.geteuid():roots=add_owned_root(roots,path.parent)
    spec['preparation_roots']=roots
    for side in ('server','client'):
        spec[side]=dict(base[side],environment=dict(base[side]['environment'],DISPLAY=ready['graphics']['display']))
    return spec

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('input-base','input-base-sha256','graphics-ready','graphics-ready-sha256','supervisor','review-reference','output'):
        p.add_argument('--'+key,required=True)
    args=p.parse_args()
    require(SUPERVISOR_SHA!='PENDING_FINAL_REVIEWED_SOURCE','Final supervisor source review is not sealed')
    supervisor=Path(args.supervisor);require(pin(supervisor)['sha256']==SUPERVISOR_SHA,'Reviewed supervisor identity differs')
    m=importlib.util.spec_from_file_location('reviewed_pair_supervisor',supervisor);s=importlib.util.module_from_spec(m);m.loader.exec_module(s)
    base=load(Path(args.input_base),args.input_base_sha256)
    ready=load(Path(args.graphics_ready),args.graphics_ready_sha256)
    spec=bind(base,ready,pin(Path(args.graphics_ready)),args.review_reference)
    # Static byte/ownership/tree/role gates and actual graphics PID/Unix-display
    # observation must all pass before any final supervisor seal is emitted.
    s.verify_spec(spec)
    graphics=s.verify_graphics(spec,s.Proc())
    output=Path(args.output)
    require(output.is_absolute() and output.resolve()==output and not output.exists() and output.parent.is_dir(),'Fresh canonical final spec path required')
    require(any(output.is_relative_to(Path(root)) for root in spec['preparation_roots']),'Final spec must remain inside an owned preparation root')
    saved=save(output,spec)
    print(json.dumps({'status':'STATIC_SPEC_AND_LIVE_GRAPHICS_VERIFIED_GAMES_NOT_STARTED','spec':saved,
                      'graphicsReserveBytes':graphics['reserve_bytes'],'gameLaunched':False,'remaining':'Fresh supervisor aggregate memory gate and authorized actual pair execution'},indent=2))

if __name__=='__main__':main()
