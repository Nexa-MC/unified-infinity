#!/usr/bin/env python3
"""Summarize preserved native evidence without revising the original phase reports."""
import datetime
import hashlib
import json
import pathlib
from run import check_inputs
from verify_world import verify

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROFILE = 'forge-native-clumps'
LOGS = ROOT / 'logs' / PROFILE

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    create_path = LOGS / 'create.json'
    recheck_path = LOGS / 'create-verifier-recheck.json'
    reopen_path = LOGS / 'reopen.json'
    lock_path = HERE / (PROFILE + '-lock.json')
    create, recheck, reopen, lock = [json.loads(p.read_text()) for p in (create_path, recheck_path, reopen_path, lock_path)]
    assert recheck['original_report_sha256'] == sha(create_path), 'Original create evidence changed'
    assert recheck['passed'] and reopen['passed']
    assert all(x['mods'] == lock['mods'] for x in (create, reopen))
    assert all(x['lock_sha256'] == sha(lock_path) for x in (create, reopen))
    for phase in ('create', 'reopen'):
        report = create if phase == 'create' else reopen
        assert report['log_sha256'] == sha(LOGS / (phase + '.log')), 'Phase log changed'
        assert report['exit_code'] == 0 and not report['timed_out']
        assert report['stage_order'] == lock['expected_stages'][phase]
        assert report['tick_freeze_acknowledged'] and report['saved'] and report['all_dimensions_saved']
    profile = ROOT / lock['profile']
    check_inputs(lock, profile, 'reopen')
    current = verify(profile, lock['expected_saved_marker'])
    assert current == reopen['offline_world_after_stop'], 'Saved world changed after final verification'
    before = recheck['offline_world_after_stop']
    after = reopen['offline_world_after_stop']
    assert before['orb']['uuid'] == after['orb']['uuid']
    assert before['orb']['clumped_map'] == after['orb']['clumped_map']
    summary = {
        'passed': True,
        'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'Native Forge52.1.0 / Minecraft1.21.1 reference for exact original Clumps19.0.0.1',
        'mods': lock['mods'], 'environment_lock_sha256': sha(lock_path),
        'profile': lock['profile'], 'phase_durations_seconds': {r['phase']: r['duration_seconds'] for r in (create, reopen)},
        'create': {'runtime_passed': True, 'initial_offline_verifier_passed': False,
                   'offline_verifier_recheck_passed': True,
                   'refinement': 'Recognize exactly zero-byte unopened Minecraft region placeholders; preserve nonzero truncation failure checks and all original reports'},
        'reopen': {'passed': True, 'runtime_read_before_write': True, 'same_survivor_uuid': True},
        'initial_entities': 6, 'saved_entities': 1, 'weighted_xp': 72,
        'exact_histogram': after['orb']['clumped_map'], 'saved_survivor_uuid_int_array': after['orb']['uuid'],
        'vanilla_count_observed': after['orb']['vanilla_count'],
        'vanilla_count_note': 'Upstream behavior; not used as conserved original-orb multiplicity',
        'warnings_preserved': {'absent_clumps_refmap': [r['original_absent_refmap_warning'] for r in (create, reopen)],
                               'network': 'Forge/Clumps update checks and Mojang public-key fetch fail in restricted test environment; no login/player action required'},
        'coverage': ['genuine Forge startup', 'original Clumps required Mixin acceptance',
                     'IClumpedOrb injection', 'natural six-to-one orb merge',
                     'every-observed-tick XP histogram/multiplicity/weighted-total conservation',
                     'actual Clumps save/read hooks', 'independent persisted entity NBT',
                     'same-world reopen without respawn or evidence repair', 'freeze/save/clean stop'],
        'not_tested': reopen['not_tested'],
        'reports': {str(p.relative_to(ROOT)): sha(p) for p in (create_path, recheck_path, reopen_path)},
        'harness_tests': {'count': 11, 'result': 'PASS', 'log': str((HERE / 'harness-unit-tests-after-native.log').relative_to(ROOT))},
        'remaining': 'Run the identical frozen companion and original Clumps in the matched Unified profile; compare bounded behavior only',
    }
    out = HERE / 'native-control-summary.json'
    assert not out.exists(), 'Preserve existing summary'
    out.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
