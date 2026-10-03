#!/usr/bin/env python3
"""Fail-closed join of an exact same-fixture native create/reopen pair."""
import argparse,datetime,hashlib,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--create-attempt',required=True);p.add_argument('--reopen-attempt',required=True);a=p.parse_args()
 paths=[HERE/'logs'/f'native-{phase}-{attempt}.json' for phase,attempt in [('create',a.create_attempt),('reopen',a.reopen_attempt)]]
 create,reopen=[json.loads(p.read_text()) for p in paths]
 checks={'both_phases_passed':create['passed'] and reopen['passed'],'same_original_probe':create['probe_sha256']==reopen['probe_sha256'],'same_runtime_lock':create['native_environment_lock_sha256']==reopen['native_environment_lock_sha256'],'persisted_data_read_before_reopen':create['offline_world_after_stop'].get('saved_data_sha256')==reopen['offline_world_before_launch'].get('saved_data_sha256'),'all_stages_exactly_once':all(all(n==1 for n in r['stage_counts'].values()) for r in (create,reopen))}
 report={'passed':all(checks.values()),'checks':checks,'native_runtime':'Minecraft 1.21.1 / Quilt Loader 0.30.1 / original QSL base+lifecycle 10.0.0-alpha.5+1.21.1','probe_sha256':create['probe_sha256'],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence':[{'path':str(p.relative_to(HERE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'log_path':str(p.with_suffix('.log').relative_to(HERE)),'log_sha256':hashlib.sha256(p.with_suffix('.log').read_bytes()).hexdigest()} for p in paths],'scope':'Native control for own Quilt-only original probe. Does not prove Unified compatibility, arbitrary Quilt mods, clients, or OP Tab.','fixture_corrections':['create-1: separate ordinary entrypoint and Mixin packages','create-2/reopen-1: replace unsupported vanilla null DataFixTypes with SAVED_DATA_COMMAND_STORAGE'], 'fixture_corrections_scope':'Fixture owner corrected native portability defects only; no Unified adapter behavior change and no cross-version DFU claim'}
 (HERE/'native-control-summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
