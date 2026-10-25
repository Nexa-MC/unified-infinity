"""Source-bound Quilt phase specs using the unchanged finalizer and supervisor.

No game, JVM, graphics server, CI or download is started. A returned executable
create seal requires the actual original static AND live-graphics validators.
A reopen spec is only a pristine input to the separately reviewed continuation
owner; the original supervisor's identity never names its runtime derivative.
"""
from pathlib import Path
import copy
import hashlib
import sys
import types

SUPERVISOR_SHA = '2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'
FINALIZER_SHA = 'e713ea481a00a760e6767fd373256fca5d1dc0f5a2dd7553ae2ffa13bbea1839'
PREPARE_SHA = '3fe5393ffc0dfe6a7bfe4a23ac9fe55dc133913a66e1908d7ff03e34ce44249e'
STAGING_SHA = 'a58df908eecb8c2047bc87fdb3b65f27d5f1d46f3f2b5f42cb0c7c28898db2f6'
CONTRACT_SHA = '0afd87b988fedc7b06445a9c160bc15ed878a722a4b1598ad7474b886d20a6c8'
COMPILER_TOOLS = {
    'portable_io.py': '93b28129279cb74c4917908ec1e426f7cd438420cf82b83ce7c1a38f06b945b7',
    'validate_portable.py': '061bf9a1dce48d5d70769467d0d2bf29b8f7ee2e879355b17e37e5406cc044e7',
    'validate_for_consumer.py': '9076351c57770ffcfa20a2d35a1e243455f707aec8eea61571afa90b123a7d3e',
}
SCHEMA = 'quilt-phase-seal-derivation-v1'


def require(value, message):
    if not value: raise ValueError(message)


def _module(path, expected, name):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file(), 'Canonical reviewed source required')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Independently reviewed source identity changed')
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(path.read_bytes() == raw, 'Reviewed source changed during import')
    return module


def load_staging(staging_pin):
    require(staging_pin['sha256'] == STAGING_SHA, 'Frozen staging identity required')
    module = _module(staging_pin['path'], STAGING_SHA, 'quilt_seal_frozen_staging')
    require(Path(staging_pin['path']).stat().st_size == staging_pin['bytes'], 'Staging source size changed')
    return module


def _engines(root, q, supervisor_pin, finalizer_pin, prepare_inputs_pin):
    for row in (supervisor_pin, finalizer_pin, prepare_inputs_pin): q.check_absolute(root, row)
    require(supervisor_pin['sha256'] == SUPERVISOR_SHA and finalizer_pin['sha256'] == FINALIZER_SHA
            and prepare_inputs_pin['sha256'] == PREPARE_SHA, 'Exact original sealer sources required')
    supervisor = _module(supervisor_pin['path'], SUPERVISOR_SHA, 'quilt_seal_original_supervisor')
    helper = _module(prepare_inputs_pin['path'], PREPARE_SHA, 'prepare_inputs')
    previous = sys.modules.get('prepare_inputs')
    try:
        sys.modules['prepare_inputs'] = helper
        finalizer = _module(finalizer_pin['path'], FINALIZER_SHA, 'quilt_seal_original_finalizer')
    finally:
        if previous is None: sys.modules.pop('prepare_inputs', None)
        else: sys.modules['prepare_inputs'] = previous
    return supervisor, finalizer


def _classify_observations(root, q, verified, report):
    """Exact log observations only; caller has already rerun compiler semantics."""
    inputs = {str(q.local(root, row['path'])): dict(row, path=str(q.local(root, row['path'])))
              for row in verified['inputs']}
    logs = {}
    require(type(report.get('phases')) is list and 1 <= len(report['phases']) <= 32, 'Exact compiler phases required')
    for phase in report['phases']:
        require(type(phase) is dict and type(phase.get('log')) is dict, 'Exact compiler phase log required')
        row = phase['log']; q.check_absolute(root, row)
        require(inputs.get(row['path']) == row and row['path'] not in logs,
                'Compiler observation is not uniquely bound in full closure')
        require(type(row['bytes']) is int and 0 <= row['bytes'] <= 16 * 1024 * 1024,
                'Compiler observation bound exceeded')
        logs[row['path']] = row
    empty = [row for row in logs.values() if row['bytes'] == 0]
    require(all(row['sha256'] == hashlib.sha256(b'').hexdigest() for row in empty), 'Empty observation digest changed')
    require(all(row['bytes'] > 0 or logs.get(path) == row for path, row in inputs.items()),
            'Empty runtime/source/artifact input cannot be classified as observation')
    protected = {str(q.local(root, verified['bundle'][key]['path'])) for key in ('artifact', 'source_manifest', 'compile_receipt')}
    require(not any(row['path'] in protected for row in empty), 'Empty artifact/source/receipt refused')
    return sorted(empty, key=lambda row: row['path'])


def validate_compiler_observations(root, *, verified, staging_pin):
    """Rerun independent compiler semantics; rehash zero and nonzero log evidence."""
    q = load_staging(staging_pin); root = q.root_path(root); q.check_absolute(root, staging_pin)
    require(q.verify_source_binding(root, verified['bundle_pin'],
        validated_provenance=verified['validated_provenance']) == verified, 'Reviewed compiler closure changed')
    candidates = verified['inputs']; modules = {}; old_modules = {}
    try:
        for filename, expected in COMPILER_TOOLS.items():
            rows = [row for row in candidates if Path(row['path']).name == filename and row['sha256'] == expected]
            require(len(rows) == 1, 'Exact independently reviewed compiler validator missing')
            path = q.check(root, rows[0]); name = filename[:-3]
            old_modules[name] = sys.modules.get(name)
            modules[name] = _module(path, expected, name); sys.modules[name] = modules[name]
        parents = {Path(module.__file__).parent for module in modules.values()}
        require(len(parents) == 1, 'Compiler validator source roots differ')
        report_path = q.check(root, verified['bundle']['compile_receipt']); report = q.load(report_path)
        contract_pin = report.get('reviewedContract')
        require(type(contract_pin) is dict and contract_pin.get('sha256') == CONTRACT_SHA,
                'Independently reviewed compiler contract required')
        contract_path = q.check_absolute(root, contract_pin)
        require(any(dict(row, path=str(q.local(root, row['path']))) == contract_pin for row in candidates),
                'Compiler contract missing from full closure')
        result = modules['validate_for_consumer'].validate_for_consumer(report_path, contract_path, CONTRACT_SHA, root)
        require(result['status'] == 'PASS_PORTABLE_COMPILE_SEMANTICS'
                and result['callerConsumerRoot'] == str(root) and result['runtimeAcceptance'] is False,
                'Compiler semantic gate failed')
        empty = _classify_observations(root, q, verified, report)
    finally:
        for name, previous in old_modules.items():
            if previous is None: sys.modules.pop(name, None)
            else: sys.modules[name] = previous
    return empty


def _source_matches(root, q, source_spec, source_spec_pin, manifest):
    require(source_spec.get('schema') == 'network-ci-pair-v2' and source_spec.get('target') == 'unified'
            and source_spec.get('port') == 25632, 'Pristine original Unified Fabric source seal required')
    expected_diagnostic = {'manifest_path': manifest['diagnosticManifest']['path'],
                           'manifest_sha256': manifest['diagnosticManifest']['sha256'],
                           'diagnostic_only': True, 'baseline_acceptance': False}
    require(source_spec.get('diagnostic_profile') == expected_diagnostic,
            'Source diagnostic profile does not match materialized build ancestry')
    source_pins = {row['path']: row for row in source_spec['inputs']}
    require(len(source_pins) == len(source_spec['inputs']), 'Duplicate source spec input')
    allowed = dict(source_pins); allowed[source_spec_pin['path']] = source_spec_pin
    for side in ('server', 'client'):
        source_role_pin = manifest['sourceRoles'][side]
        require(source_pins.get(source_role_pin['path']) == source_role_pin
                and source_role_pin['path'] in source_spec['source_receipts'], 'Source role is not sealed producer ancestry')
        role = q.load(q.check_absolute(root, source_role_pin)); sealed = source_spec[side]
        require(all(role[key] == sealed[key] for key in ('cwd', 'command', 'original_mods', 'managed_mods')),
                'Source seal does not describe exact pristine materializer source roles')
        require(Path(source_spec['probe_path']).name == q.TRANSPORT_NAME
                and role['probe_path'] == str(Path(role['cwd']) / 'mods' / q.TRANSPORT_NAME),
                'Unchanged Fabric transport source required')
        for name in ('mods', 'config', 'defaultconfigs', 'installation', 'libraries'):
            tree = Path(role['cwd']) / name
            require(not tree.is_dir() or str(tree) in source_spec['immutable_trees'],
                    'Original role immutable tree omitted: ' + name)
        options = str(Path(role['cwd']) / 'options.txt')
        for row in role['files']:
            if row['path'] == options: allowed[options] = row
            else: require(source_pins.get(row['path']) == row, 'Source role input missing from original sealed closure')
    for row in manifest['sourceInputs']:
        require(allowed.get(row['path']) == row,
                'Unintended source input outside original seal, including foreign phase mutable input')
    return source_pins


def _compose(root, q, finalizer, source_spec, source_spec_pin, manifest, manifest_pin,
             ready, ready_pin, extra_source_pins, empty_logs):
    source_pins = _source_matches(root, q, source_spec, source_spec_pin, manifest)
    require(ready_pin['path'] in source_spec['source_receipts']
            and source_pins.get(ready_pin['path']) == ready_pin and ready['graphics'] == source_spec['graphics'],
            'Exact existing live graphics producer required')
    require(manifest['phase'] in ('create', 'reopen'), 'Exact phase required')
    excluded = {row['path']: row for row in empty_logs}
    source_roots = {}; phase_roots = {}; roles = {}; live_options = {}
    for side in ('server', 'client'):
        source_roots[side] = Path(source_spec[side]['cwd'])
        role = q.load(q.check_absolute(root, manifest['roles'][side])); phase_roots[side] = Path(role['cwd'])
        require(role['command'][1] == q.PHASE_PROPERTY + manifest['phase'], 'Role phase does not match materialized phase')
        roles[side] = {key: copy.deepcopy(role[key]) for key in ('cwd', 'command', 'original_mods', 'managed_mods')}
        roles[side]['environment'] = q.relocate_role_paths(source_spec[side]['environment'], source_roots[side], phase_roots[side])
        for row in role['files']:
            if row['path'] == str(phase_roots[side] / 'options.txt'):
                live_options[row['path']] = row
    require(not any(Path(path).is_relative_to(game) for path in excluded for game in phase_roots.values()),
            'Phase runtime input cannot be treated as compiler observation')
    pins = dict(source_pins)
    additions = [source_spec_pin, manifest_pin, *manifest['inputs'], *extra_source_pins]
    for row in additions:
        q.check_absolute(root, row)
        if row['path'] in excluded:
            require(excluded[row['path']] == row, 'Excluded compiler observation identity changed'); continue
        if row['path'] in live_options:
            require(live_options[row['path']] == row, 'Mutable options original receipt identity changed'); continue
        require(row['bytes'] > 0, 'Empty non-observation runtime/source input refused')
        require(row['path'] not in pins or pins[row['path']] == row, 'Conflicting phase input pin')
        pins[row['path']] = row
    trees = []
    for value in source_spec['immutable_trees']:
        path = Path(value); matches = [side for side, game in source_roots.items() if path.is_relative_to(game)]
        require(len(matches) <= 1, 'Overlapping source role immutable roots')
        if matches:
            side = matches[0]; path = phase_roots[side] / path.relative_to(source_roots[side])
        trees.append(str(path))
    require(len(trees) == len(set(trees)), 'Duplicate relocated immutable tree')
    # Do not invent or omit any role tree. The original supervisor checks complete
    # JDK/assets/native/config/module ownership against these exact relocated trees.
    base = {key: copy.deepcopy(value) for key, value in source_spec.items()
            if key not in ('schema', 'graphics', 'authorization', 'server', 'client', 'inputs', 'immutable_trees', 'source_receipts')}
    base.update(schema='prepared-network-ci-pair-v2', status='NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE',
        authorization={key: value for key, value in source_spec['authorization'].items() if key != 'ci_pair_review_reference'},
        server=roles['server'], client=roles['client'], inputs=sorted(pins.values(), key=lambda row: row['path']),
        immutable_trees=trees, source_receipts=list(dict.fromkeys([
            *[path for path in source_spec['source_receipts'] if path != ready_pin['path']], source_spec_pin['path'],
            manifest_pin['path'], *[manifest['roles'][side]['path'] for side in ('server', 'client')],
            *[manifest['phaseConfigurations'][side]['path'] for side in ('server', 'client')]])))
    spec = finalizer.bind(base, ready, ready_pin, source_spec['authorization']['ci_pair_review_reference'])
    for key in ('pair_lock', 'target', 'port', 'graphics', 'jdk_legal_links', 'preparation_roots',
                'probe_path', 'probe_source_manifest', 'probe_build_receipt', 'authorization'):
        require(spec[key] == source_spec[key], 'Original runtime gate changed: ' + key)
    require(spec.get('diagnostic_profile') == source_spec.get('diagnostic_profile'), 'Diagnostic ancestry changed')
    return spec, sorted(live_options.values(), key=lambda row: row['path'])


def prepare_phase_spec(root, *, manifest_pin, verified, source_spec_pin, graphics_ready_pin,
                       supervisor_pin, finalizer_pin, prepare_inputs_pin, staging_pin):
    """Static original validation only; no output or live-readiness claim."""
    q = load_staging(staging_pin); root = q.root_path(root)
    for row in (manifest_pin, source_spec_pin, graphics_ready_pin, staging_pin): q.check_absolute(root, row)
    supervisor, finalizer = _engines(root, q, supervisor_pin, finalizer_pin, prepare_inputs_pin)
    manifest = q.validate_materialized_phase(root, manifest_pin, verified)
    source_spec = q.load(Path(source_spec_pin['path']))
    supervisor.verify_spec(source_spec)
    empty = validate_compiler_observations(root, verified=verified, staging_pin=staging_pin)
    ready = q.load(Path(graphics_ready_pin['path']))
    own_pin = q.absolute_pin(root, Path(__file__))
    spec, options = _compose(root, q, finalizer, source_spec, source_spec_pin, manifest, manifest_pin,
        ready, graphics_ready_pin, [supervisor_pin, finalizer_pin, prepare_inputs_pin, staging_pin, own_pin], empty)
    supervisor.verify_spec(spec)
    return spec, {'evidenceOnlyCompilerLogs': empty, 'mutableOptionsPinnedByRoleReceipts': options}, supervisor


def create_phase_seal(root, *, manifest_pin, verified, source_spec_pin, graphics_ready_pin,
                      supervisor_pin, finalizer_pin, prepare_inputs_pin, staging_pin, output):
    """Write only after original static AND actual live-graphics verification."""
    q = load_staging(staging_pin); root = q.root_path(root); output = q.absolute(root, str(output))
    derivative_path = output.with_name(output.stem + '-derivation.json')
    require(output.parent.is_dir() and not output.exists() and not derivative_path.exists(), 'Fresh phase seal output required')
    kwargs = dict(manifest_pin=manifest_pin, source_spec_pin=source_spec_pin, graphics_ready_pin=graphics_ready_pin,
        supervisor_pin=supervisor_pin, finalizer_pin=finalizer_pin, prepare_inputs_pin=prepare_inputs_pin, staging_pin=staging_pin)
    spec, classification, supervisor = prepare_phase_spec(root, verified=verified, **kwargs)
    require(any(output.is_relative_to(Path(path)) for path in spec['preparation_roots']), 'Phase seal leaves owned preparation roots')
    supervisor.verify_graphics(spec, supervisor.Proc())
    # Repeat all exact observation checks immediately before publishing the seal.
    require(validate_compiler_observations(root, verified=verified, staging_pin=staging_pin)
            == classification['evidenceOnlyCompilerLogs'], 'Compiler observations changed during sealing')
    with output.open('xb') as stream: stream.write(q.canonical(spec) + b'\n')
    phase = q.load(Path(manifest_pin['path']))['phase']
    receipt = {'schema': SCHEMA, **q.FLAGS, 'phase': phase, 'spec': q.absolute_pin(root, output),
        'arguments': kwargs, 'classification': classification, 'fixtureBundle': verified['bundle_pin'],
        'validatedProvenance': verified['validated_provenance'], 'sealAdapter': q.absolute_pin(root, Path(__file__)),
        'originalStaticSpecVerified': True, 'liveGraphicsVerifiedAtSeal': True,
        'executionOwner': 'original-supervisor' if phase == 'create' else 'reviewed-continuation-required'}
    with derivative_path.open('xb') as stream: stream.write(q.canonical(receipt) + b'\n')
    return {'spec': receipt['spec'], 'derivation': q.absolute_pin(root, derivative_path),
            'supervisorForStaticValidation': supervisor_pin, 'phase': phase,
            'executionOwner': receipt['executionOwner'], **q.FLAGS}


def validate_phase_seal(root, *, spec_pin, derivation_pin, verified):
    """Recheck before dispatch. Reopen execution still belongs to continuation."""
    # The caller pins this adapter through its independent driver source plan.
    from json import loads
    root_path = Path(root).absolute(); path = Path(derivation_pin['path'])
    require(root_path.is_dir() and root_path.resolve() == root_path and path.is_absolute()
            and path.is_relative_to(root_path) and path.resolve() == path and path.is_file()
            and type(derivation_pin.get('bytes')) is int and 0 < derivation_pin['bytes'] <= 4 * 1024 * 1024,
            'Canonical bounded derivation pin required')
    raw = path.read_bytes()
    require(len(raw) == derivation_pin['bytes'] and hashlib.sha256(raw).hexdigest() == derivation_pin['sha256'],
            'Untrusted phase derivation bytes')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate derivation JSON key'); result[key] = value
        return result
    def invalid(_): raise ValueError('Nonfinite derivation JSON value')
    receipt = loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    q = load_staging(receipt['arguments']['staging_pin']); root = q.root_path(root)
    q.check_absolute(root, derivation_pin); q.check_absolute(root, spec_pin)
    q.exact(receipt, ('schema', *q.FLAGS, 'phase', 'spec', 'arguments', 'classification', 'fixtureBundle',
        'validatedProvenance', 'sealAdapter', 'originalStaticSpecVerified', 'liveGraphicsVerifiedAtSeal', 'executionOwner'), 'phase derivation receipt')
    require(receipt['schema'] == SCHEMA and receipt['spec'] == spec_pin
            and receipt['sealAdapter'] == q.absolute_pin(root, Path(__file__))
            and receipt['fixtureBundle'] == verified['bundle_pin']
            and receipt['validatedProvenance'] == verified['validated_provenance']
            and all(type(receipt[key]) is type(value) and receipt[key] == value for key,value in q.FLAGS.items()),
            'Untrusted phase seal derivation')
    expected, classification, supervisor = prepare_phase_spec(root, verified=verified, **receipt['arguments'])
    require(q.load(Path(spec_pin['path'])) == expected and receipt['classification'] == classification
            and receipt['phase'] == q.load(Path(receipt['arguments']['manifest_pin']['path']))['phase']
            and receipt['originalStaticSpecVerified'] is True and receipt['liveGraphicsVerifiedAtSeal'] is True
            and receipt['executionOwner'] == ('original-supervisor' if receipt['phase'] == 'create' else 'reviewed-continuation-required'),
            'Phase spec differs from independently derived original contract')
    supervisor.verify_graphics(expected, supervisor.Proc())
    return receipt
