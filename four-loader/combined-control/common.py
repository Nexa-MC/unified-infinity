"""Exact inputs and read-only reuse of the accepted single-lane verifiers."""
import hashlib
import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = '25621'  # Retain the Quilt parser's exact loopback-binding assertion.
CLUMPS_MARKER = 'clumps_forge_19_0_0_1_probe_v1'
INPUTS = {
    'source-workspace/artifacts/unified-infinity-four-loader-98d86a92.jar': '98d86a92e91a20df980cc95abc8ced4972476edff7ec982d08c88e3d4e8579fd',
    'runtime-bundle/build-quilt-range-candidate/libs/unified-infinity-0.1.0-dev.jar': '746ca5e3fcaf64ae7b67836535d8aa0bcb5d1cb4fe37161cc811784cca5adbd4',
    'run/source-built-lithium-unified/mods/unified-infinity-preload-0.1.0-dev.jar': '7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99',
    'docs/real-mod-trial/lithium-fabric-0.15.4+mc1.21.1.jar': '92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa',
    'mixed-pack/research/archives/Chunky-Fabric-1.4.23.jar': '3412b170247dde7351e0945d857e713bedf6fae05ab300aa74d06ffbde0ca07e',
    'mixed-pack/research/archives/FarmersDelight-1.21.1-1.3.4.jar': '139ad7696462c89c03eea463f805abffa552526c5dadaadae221dd9624cb197c',
    'docs/four-loader/forge/upstream/Clumps-forge-1.21.1-19.0.0.1.jar': 'e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19',
    'four-loader/clumps-probe/build/unified-clumps-probe-0.1.0.jar': 'b8b6822fc80d53b9a44daa994abeaa53b19ec0838649d9eb7e55f1a766bb6d09',
    'four-loader/quilt-probe/build/unified-native-quilt-probe-0.1.0.jar': 'f420e2021563d25931f1783f5a5744943dfbafc7557ae5c52ff2090331066b04',
}
QUILT_SHA = INPUTS['four-loader/quilt-probe/build/unified-native-quilt-probe-0.1.0.jar']
REUSED_FILES = [
    'mixed-pack/harness/run_mixed_pack.py',
    'integration-tests/run_lithium_hopper_parity.py',
    'four-loader/clumps-control/prepare.py',
    'four-loader/clumps-control/verify_world.py',
    'four-loader/quilt-unified-control/run_unified.py',
    'four-loader/quilt-unified-control/verify_world.py',
    'registry-probe/region_nbt.py',
    'mixed-pack/harness/verify_saved_parity.py',
    'mixed-pack/logs/source-acceptance-v1-saved-worldgen-parity.json',
]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def valid_profile(value):
    return re.fullmatch(r'unified-combined-[a-z0-9]+(?:-[a-z0-9]+)*', value) is not None

def load(name, relative, aliases=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    aliases = aliases or {}
    prior = {key: sys.modules.get(key) for key in aliases}
    prior_path = list(sys.path)
    try:
        sys.modules.update(aliases)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = prior_path
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module

mixed = load('combined_mixed', REUSED_FILES[0])
clumps_prepare = load('combined_clumps_prepare', REUSED_FILES[2])
clumps_world = load('combined_clumps_world', REUSED_FILES[3])
quilt_world = load('combined_quilt_world', REUSED_FILES[5])
quilt = load('combined_quilt_parser', REUSED_FILES[4], {'verify_world': quilt_world})

def both_ready(lines):
    return all(any(marker in line for line in lines) for marker in (
        'Done (', 'UNIFIED_CLUMPS_PROBE PASS stage=ready_to_save ',
        'NATIVE_QUILT_PROBE PASS stage=ready_to_save '))

def probe_evidence(raw, phase):
    result = quilt.parse(raw, phase, QUILT_SHA)
    booleans = ['entrypoint_order_valid', 'original_jar_identity_verified', 'saved_data_phase_verified',
                'qsl_and_mixin_tick_verified', 'server_ready', 'save_acknowledged',
                'all_dimensions_saved', 'no_probe_failure', 'loopback_binding_verified']
    result['passed'] = result['class_defined_count'] == 1 and all(n == 1 for n in result['stage_counts'].values()) and all(result[key] for key in booleans)
    lines = raw.decode(errors='replace').splitlines()
    markers = [line for line in lines if 'UNIFIED_CLUMPS_PROBE' in line]
    found = [match[1] for line in markers if (match := re.search(r'UNIFIED_CLUMPS_PROBE PASS stage=([a-z_]+)(?:\s|$)', line))]
    expected = clumps_prepare.STAGES[phase]
    clumps = {'markers': markers, 'stage_order': found, 'expected_stage_order': expected,
              'stage_counts': {stage: found.count(stage) for stage in expected},
              'passed': found == expected and not any('UNIFIED_CLUMPS_PROBE FAIL' in line for line in lines)}
    return {'quilt': result, 'clumps': clumps, 'passed': result['passed'] and clumps['passed']}

parity = load('combined_saved_parity', REUSED_FILES[7])

def canonical_targets(profile):
    baseline = json.loads((ROOT / REUSED_FILES[8]).read_text())
    assert baseline['passed'] and len(baseline['chunks']) == 9, 'Expected accepted native target baseline'
    values = []
    for row in baseline['chunks']:
        digest = parity.digest(parity.canonical(mixed.read_chunk(profile / 'world', row['x'], row['z'])))
        assert digest == row['native_neoforge_sha256'], f'Chunky canonical block/biome mismatch: {row}'
        values.append({'x': row['x'], 'z': row['z'], 'sha256': digest, 'native_equal': True})
    return values

def verify_world(profile):
    forced = clumps_world.read_nbt(profile / 'world/data/chunks.dat')
    assert forced['data']['Forced'] == [0], 'Persisted forced chunk differs'
    platform = mixed.block_state(mixed.read_chunk(profile / 'world', 0, 0), (8, 99, 8))
    assert platform['Name'] == 'minecraft:stone', 'Clumps platform missing'
    return {'mixed_pack': mixed.saved_evidence(profile, 'unified'),
            'clumps': clumps_world.verify(profile, CLUMPS_MARKER),
            'quilt': quilt_world.verify(profile), 'canonical_chunky_targets': canonical_targets(profile),
            'forced_chunks': forced['data']['Forced'], 'clumps_platform': platform, 'passed': True}
