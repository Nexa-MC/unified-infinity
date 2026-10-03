#!/usr/bin/env python3
"""Aggregate native control evidence without broadening the compatibility claim."""
import hashlib
import json
import pathlib
from verify_world import verify

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / 'logs/forge-native-probe'
BUILD = json.loads((HERE / 'build/build-report.json').read_text())
PIN = json.loads((HERE / 'native-environment-lock.json').read_text())
original = ROOT / BUILD['probe']
sha = hashlib.sha256(original.read_bytes()).hexdigest()
assert sha == BUILD['sha256'] == PIN['probe_sha256']
runs = {phase: json.loads((LOGS / f'native-{phase}.json').read_text()) for phase in ('create', 'reopen')}
for phase, report in runs.items():
    assert report['passed'] and report['probe_sha256'] == sha, phase
    assert all(count == 1 for count in report['stage_counts'].values())
assert runs['reopen']['offline_world_before_launch']['passed']
assert runs['reopen']['offline_world_after_stop']['passed']
assert any('read_before_write=true' in marker for marker in runs['reopen']['markers'])
assert runs['create']['world_files']['world/data/unified_forge_probe.dat'] == runs['reopen']['world_files']['world/data/unified_forge_probe.dat']
assert not any('LanServerPinger' in line for line in (LOGS / 'native-reopen.log').read_text().splitlines())
result = {
    'passed': True, 'probe_sha256': sha, 'minecraft': '1.21.1', 'forge': '52.1.0',
    'java': '21.0.12.1+1-LTS', 'eventbus': '6.2.27', 'namespace': 'Mojmap production',
    'original_jar': str(original.relative_to(ROOT)),
    'runs': {phase: {'passed': report['passed'], 'exit_code': report['exit_code'],
                    'stage_counts': report['stage_counts'], 'report': f'logs/forge-native-probe/native-{phase}.json',
                    'log': f'logs/forge-native-probe/native-{phase}.log'} for phase, report in runs.items()},
    'independent_persistence_verification': verify(ROOT / 'run/forge-native-probe'),
    'saved_data_bytes_identical_across_reopen': True,
    'coverage': ['Forge-only metadata/annotation/context constructor', 'exactly-once constructor/setup/work/item supplier',
                 'DeferredRegister vanilla item key and RegistryObject semantics', 'real registry identity',
                 'server lifecycle and explicit Post.getServer/haveTime', 'chest custom-item and SavedData save/reopen',
                 'read-before-write on reopened world', 'independent region/NBT reads', 'clean save and stop'],
    'limitations': ['Native Forge control only; Unified adapter has not run in this task',
                    'One original Item; no custom block or IForgeRegistry overload',
                    'No third-party mod, Mixin, capability, client, account, player or network protocol test',
                    'First create attempted default LAN advertising, blocked by sandbox; disabled explicitly for reopen',
                    'Forge logged missing pack metadata because this code-only probe supplies no resource/data pack',
                    'Mojang public-key fetch was unavailable without network configuration; online-mode remained true and no players connected'],
}
(LOGS / 'native-summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
