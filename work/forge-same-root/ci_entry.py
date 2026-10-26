#!/usr/bin/env python3
"""Fixed-round compile-only CI entry; no game, binary upload or old receipts."""
from pathlib import Path
import argparse, hashlib, json, os, sys, time
import first_step_anchor as anchor
import same_root as sr
import pipeline

def budget(value, now=None, wall=None):
    now=time.monotonic() if now is None else now
    wall=time.time() if wall is None else wall
    left=min(value['capturedMonotonic']+27*60-now, anchor.utc(anchor.CUTOFF_UTC)-180-wall)
    sr.require(left>=60, 'Insufficient bounded work budget')
    return now+left

def validate(repo, digest):
    sr.require(sr.sha(sr.HERE/'input-manifest.json')==digest,'Reviewed same-root source manifest mismatch')
    sr.verify_stage(sr.HERE)
    old=sr.module('original_stage_verify',repo/'work/forge-play-compile-ci/run.py')
    old.validate_source(repo,pipeline.ORIGINAL_STAGE_MANIFEST)
    sr.require((sr.HERE/'ci_entry.py').is_file(), 'CI entry absent')

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--consumer',type=Path,required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    repo=a.repo.resolve(strict=True)
    validate(repo,a.manifest_sha256)
    if a.verify_only:
        print('FORGE_SAME_ROOT_SOURCE_VERIFIED',flush=True);return
    first=anchor.read_anchor();deadline=budget(first)
    result={'schema':'forge-same-root-ci-v1','runId':os.environ['GITHUB_RUN_ID'],'headSha':os.environ['GITHUB_SHA'],'status':'IN_PROGRESS',**sr.FALSE_FLAGS}
    try:
        result['build']=pipeline.execute(repo,a.consumer,deadline,a.manifest_sha256)
        validate(repo,a.manifest_sha256)
        result['status']='FRESH_CORE_AND_BOTH_PROBES_COMPILED'
    except BaseException as e:
        result.update(status='FAILED',error=type(e).__name__+': '+str(e));raise
    finally:
        result['finishedUtc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        if a.consumer.is_dir():sr.write(a.consumer/'same-root-ci-result.json',result)
        print('FORGE_SAME_ROOT_CI_RESULT '+json.dumps(result),flush=True)
        # Text evidence remains accessible even when a producer raises.
        for name in ['evidence/core.log','evidence/core-owner.json','evidence/core-producer.json']:
            path=a.consumer/name
            if path.is_file():
                print('FORGE_SAME_ROOT_TEXT '+name,flush=True)
                print(path.read_text(errors='replace')[-24000:],flush=True)
if __name__=='__main__':main()
