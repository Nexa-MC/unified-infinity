#!/usr/bin/env python3
"""Offline, compile-only glue. Never starts a process or extends an owner deadline.

The caller's existing process owner must bound this module AND the returned
compiler command. Successful validation is diagnostic compile/ABI evidence only.
"""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import importlib.util
import json
import math
import os
import stat
import sys
import time

CONTRACT_SHA256 = '0afd87b988fedc7b06445a9c160bc15ed878a722a4b1598ad7474b886d20a6c8'
CONSUMER_VALIDATOR_SHA256 = '9076351c57770ffcfa20a2d35a1e243455f707aec8eea61571afa90b123a7d3e'
STAGING_SHA256 = 'a58df908eecb8c2047bc87fdb3b65f27d5f1d46f3f2b5f42cb0c7c28898db2f6'
LOCKS = {
    'runtime': ('runtime-inputs.lock.json', 126434, '8a6457888bc302bbcb74ff0b74dbefee72d63b15140bdc9dfa639629bee4f85f'),
    'core': ('profiles/ffapi-core-dependency-lock.json', 1350706, '43ac0ce038cb00da23f0ae625f64c4b1bb83251c82ee2269b6ae698f50d4389b'),
    'product': ('product-input-lock.json', 6656, '3df7f63664e36a374f7beee8e258a96ec8e1620dc361843107d25749e3a7aa03'),
}
BASE_PATHS = {'compile_tools', 'staging_tool', 'lock_root', 'api_root',
              'source_archive', 'source_manifest', 'jdk_manifest', 'jdk_root'}
DEPENDENCIES = {
    'server_bundle': ('runtime', 'serverClosure', 'run/neoforge-native/libraries/net/minecraft/server/1.21.1/server-1.21.1.jar'),
    'mapping_owner': ('core', 'artifacts', 'source-workspace/pinned-build-maven/org/sinytra/forgified-fabric-loader/2.5.70+0.19.3+1.21.1/forgified-fabric-loader-2.5.70+0.19.3+1.21.1.jar'),
    'art': ('core', 'artifacts', 'source-workspace/pinned-build-maven/net/neoforged/AutoRenamingTool/2.0.17/AutoRenamingTool-2.0.17-all.jar'),
    'annotations': ('core', 'artifacts', 'source-workspace/pinned-build-maven/org/jetbrains/annotations/24.1.0/annotations-24.1.0.jar'),
    'loader': ('product', 'artifacts', 'docs/four-loader/quilt/upstream/loader-0.30.1.jar'),
    'qsl_base': ('product', 'artifacts', 'docs/four-loader/quilt/upstream/qsl_base-alpha5.jar'),
    'qsl_lifecycle': ('product', 'artifacts', 'docs/four-loader/quilt/upstream/lifecycle_events-alpha5.jar'),
    'mixin': ('runtime', 'serverClosure', 'run/neoforge-native/libraries/net/fabricmc/sponge-mixin/0.15.2+mixin.0.8.7/sponge-mixin-0.15.2+mixin.0.8.7.jar'),
    'jsr305': ('runtime', 'serverClosure', 'run/neoforge-native/libraries/com/google/code/findbugs/jsr305/3.0.2/jsr305-3.0.2.jar'),
    **{name: ('runtime', 'serverClosure', f'run/neoforge-native/libraries/org/ow2/asm/{name}/9.8/{name}-9.8.jar')
       for name in ('asm', 'asm-analysis', 'asm-commons', 'asm-tree', 'asm-util')},
}
LAYOUT_SCHEMA = 'quilt-compile-pipeline-layout-v1'
REQUEST_SCHEMA = 'quilt-compile-pipeline-request-v1'
FLAGS = {'diagnosticOnly': True, 'runtimeAcceptance': False, 'baselineAcceptance': False,
         'gameLaunched': False, 'ciStarted': False, 'originalArtifactLocksChanged': False}


def require(value, message):
    if not value:
        raise ValueError(message)


class Deadline:
    """Epoch admission/checks only; the outer original monotonic owner is authority.

    Reconstructed monotonic checks are supplemental across API/CLI invocations;
    they cannot replace the admission-time owner bound after a wall-clock jump.
    """
    def __init__(self, epoch):
        require(type(epoch) in (int, float) and math.isfinite(epoch), 'finite numeric deadline required')
        self.epoch = epoch
        self.monotonic = time.monotonic() + epoch - time.time()
        self.check()

    def check(self):
        if time.time() >= self.epoch or time.monotonic() >= self.monotonic:
            raise TimeoutError('existing outer deadline expired; do not renew it')


def canonical(path, root=None, *, directory=False, missing=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'canonical absolute path required')
    for parent in (*reversed(path.parents), path):
        require(not parent.is_symlink(), 'symlink path or ancestor forbidden')
    require(path.resolve(strict=False) == path, 'redirected path forbidden')
    if root is not None:
        require(path.is_relative_to(root), 'path outside caller consumer root')
    if not missing:
        mode = path.stat().st_mode
        require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'regular file/directory required')
    return path


def relative(value):
    require(type(value) is str and value and '\\' not in value, 'portable path string required')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == value
            and value != '.', 'canonical consumer-relative path required')
    return path


def local(root, value, **kwargs):
    return canonical(root / relative(value), root, **kwargs)


def load(path):
    path = canonical(path)
    require(path.stat().st_size <= 3 * 1024 * 1024, 'JSON evidence size bound')
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def invalid(_):
        raise ValueError('nonfinite JSON value')
    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), 'nonfinite JSON number')
        return parsed
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pin(root, path, deadline):
    deadline.check()
    path = canonical(path, root)
    before = path.stat()
    require(0 <= before.st_size <= 1024 * 1024 * 1024, 'bounded file required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            deadline.check()
            digest.update(data)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'file changed while hashing')
    deadline.check()
    return {'path': path.relative_to(root).as_posix(), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def check(root, path, expected, deadline):
    row = pin(root, path, deadline)
    require(row['sha256'] == expected['sha256'] and
            ('bytes' not in expected or row['bytes'] == expected['bytes']), 'frozen hash/size mismatch: ' + str(path))
    return row


def write_fresh(path, value, deadline):
    deadline.check()
    with path.open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    deadline.check()


def resolve(consumer_root, layout_path, deadline):
    """Resolve exact lock roles, with optional explicit hash-checked relocations."""
    deadline.check()
    root = canonical(consumer_root, directory=True)
    layout_path = canonical(layout_path, root)
    layout = load(layout_path)
    require(type(layout) is dict and set(layout) == {'schema', 'paths', 'dependency_paths'}
            and layout['schema'] == LAYOUT_SCHEMA, 'strict layout schema')
    require(type(layout['paths']) is dict and set(layout['paths']) == BASE_PATHS, 'exact layout path roles')
    require(type(layout['dependency_paths']) is dict and set(layout['dependency_paths']) <= set(DEPENDENCIES),
            'unknown dependency relocation role')
    paths = {key: local(root, value, directory=key in {'compile_tools', 'lock_root', 'api_root', 'jdk_root'})
             for key, value in layout['paths'].items()}
    contract_path = canonical(paths['compile_tools'] / 'reviewed-contract.json', root)
    check(root, contract_path, {'sha256': CONTRACT_SHA256}, deadline)
    contract = load(contract_path)
    require(set(contract['inputs']) == set(DEPENDENCIES) | {'source_archive', 'source_manifest', 'jdk_manifest'},
            'frozen contract input roles')
    tool_paths = []
    for row in contract['tools']:
        path = local(paths['compile_tools'], row['path'])
        check(root, path, row, deadline)
        tool_paths.append(path)
    validator_path = paths['compile_tools'] / 'validate_for_consumer.py'
    check(root, validator_path, {'sha256': CONSUMER_VALIDATOR_SHA256}, deadline)
    check(root, paths['staging_tool'], {'sha256': STAGING_SHA256}, deadline)
    locks = {}; lock_pins = {}
    for key, (name, size, sha) in LOCKS.items():
        path = local(paths['lock_root'], name)
        lock_pins[key] = check(root, path, {'bytes': size, 'sha256': sha}, deadline)
        locks[key] = load(path)
    inputs = {key: paths[key] for key in ('source_archive', 'source_manifest', 'jdk_manifest', 'jdk_root')}
    bindings = {}
    for role, (lock, collection, locked_path) in DEPENDENCIES.items():
        matches = [row for row in locks[lock][collection] if row.get('path') == locked_path]
        require(len(matches) == 1, 'one exact original lock row required: ' + role)
        row = matches[0]
        require(row['sha256'] == contract['inputs'][role]['sha256'] and
                row['bytes'] == contract['inputs'][role]['bytes'], 'lock/contract disagreement: ' + role)
        inputs[role] = (local(root, layout['dependency_paths'][role]) if role in layout['dependency_paths']
                        else local(paths['api_root'], locked_path))
        bindings[role] = {'lock': lock_pins[lock], 'collection': collection,
                          'lockedPath': locked_path, 'consumerPath': inputs[role].relative_to(root).as_posix(),
                          'bytes': row['bytes'], 'sha256': row['sha256']}
    identities = set()
    for role, path in inputs.items():
        info = path.stat(); identity = (info.st_dev, info.st_ino)
        require(identity not in identities, 'duplicate input/hardlink alias')
        identities.add(identity)
        if role != 'jdk_root':
            check(root, path, contract['inputs'][role], deadline)
    config = {'schema': 1, 'paths': {key: path.relative_to(root).as_posix() for key, path in inputs.items()}}
    deadline.check()
    return {'root': root, 'layout_path': layout_path, 'paths': paths, 'inputs': inputs,
            'contract_path': contract_path, 'contract': contract, 'config': config,
            'lock_pins': lock_pins, 'bindings': bindings, 'tool_paths': tool_paths + [validator_path]}


def output_path(context, output):
    root = context['root']
    out = canonical(output, root, missing=True)
    require(out != root, 'consumer root cannot be output')
    protected = [context['inputs']['source_manifest'].parent, context['inputs']['jdk_root'],
                 context['paths']['compile_tools'], context['paths']['staging_tool'].parent,
                 context['paths']['lock_root']]
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in protected),
            'output overlaps frozen source/tool/JDK/lock tree')
    require(not any(path.is_relative_to(out) for path in context['inputs'].values()),
            'output overlaps input files')
    return out


def request(context, operation, deadline):
    return {'schema': REQUEST_SCHEMA, 'consumerRoot': str(context['root']),
            'deadlineEpoch': deadline.epoch, 'layout': pin(context['root'], context['layout_path'], deadline),
            'contractSha256': CONTRACT_SHA256, 'compileOutput': str(operation / 'build'),
            'portableConfig': context['config'], 'dependencyBindings': context['bindings'], **FLAGS}


def prepare(consumer_root, layout_path, operation, deadline_epoch):
    """Create a fresh config/request. Return argv only; the outer owner launches it."""
    deadline = Deadline(deadline_epoch)
    context = resolve(consumer_root, layout_path, deadline)
    operation = output_path(context, operation)
    require(not operation.exists(), 'fresh operation directory required')
    operation.mkdir(parents=True)
    write_fresh(operation / 'portable-config.json', context['config'], deadline)
    write_fresh(operation / 'request.json', request(context, operation, deadline), deadline)
    return compiler_command(consumer_root, layout_path, operation, deadline_epoch)


def compiler_command(consumer_root, layout_path, operation, deadline_epoch):
    deadline = Deadline(deadline_epoch)
    context = resolve(consumer_root, layout_path, deadline)
    operation = output_path(context, operation)
    require(load(operation / 'request.json') == request(context, operation, deadline), 'prepared request changed')
    require(load(operation / 'portable-config.json') == context['config'], 'portable config disagrees with exact roles')
    require(not (operation / 'build').exists(), 'compiler output must still be fresh')
    deadline.check()
    return [sys.executable, '-B', str(context['paths']['compile_tools'] / 'build_portable.py'),
            '--consumer-root', str(context['root']), '--config', str(operation / 'portable-config.json'),
            '--contract', str(context['contract_path']), '--contract-sha256', CONTRACT_SHA256,
            '--output', str(operation / 'build'), '--deadline-epoch', str(deadline_epoch)]


@contextmanager
def frozen_modules(context):
    """Use verified source, not an ambient module cache or a local .pyc file."""
    names = ['portable_io', 'validate_portable', 'validate_for_consumer', '_quilt_pipeline_staging']
    saved = {name: sys.modules.get(name) for name in names}
    try:
        modules = {}
        for name in names:
            path = (context['paths']['staging_tool'] if name == '_quilt_pipeline_staging'
                    else context['paths']['compile_tools'] / (name + '.py'))
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            source = path.read_bytes()
            expected = (STAGING_SHA256 if name == '_quilt_pipeline_staging' else
                        CONSUMER_VALIDATOR_SHA256 if name == 'validate_for_consumer' else
                        next(row['sha256'] for row in context['contract']['tools'] if row['path'] == name + '.py'))
            require(hashlib.sha256(source).hexdigest() == expected, 'frozen source changed before import')
            exec(compile(source, str(path), 'exec'), module.__dict__)
            modules[name] = module
        yield modules['validate_for_consumer'], modules['_quilt_pipeline_staging']
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def bundle(context, receipt, output, deadline, *, original_deadline=None, expected_config=None, replay=False):
    root = context['root']; receipt = canonical(receipt, root)
    output = output_path(context, output)
    require(not output.exists(), 'fresh staging evidence directory required')
    report = load(receipt)
    require(report.get('consumerRoot') == str(root), 'receipt does not match caller boundary')
    actual_config = canonical(report['portableConfig']['path'], root)
    require(load(actual_config) == context['config'], 'receipt config disagrees with independently resolved roles')
    if expected_config is not None:
        require(actual_config == expected_config, 'receipt did not use prepared config')
    if original_deadline is not None:
        require(type(report.get('callerDeadlineEpoch')) in (int, float) and
                report['callerDeadlineEpoch'] == original_deadline, 'compiler changed inherited deadline')
    deadline.check()
    with frozen_modules(context) as (validator, staging):
        semantic = validator.validate_for_consumer(receipt, context['contract_path'], CONTRACT_SHA256, root)
        deadline.check()
        require(semantic['status'] == 'PASS_PORTABLE_COMPILE_SEMANTICS'
                and semantic['callerConsumerRoot'] == str(root)
                and semantic['independentlyReviewedContractSha256'] == CONTRACT_SHA256,
                'frozen semantic validation failed')
        # No output exists before the semantic gate passes.
        output.mkdir(parents=True)
        semantic_path = output / 'consumer-semantic-validation.json'
        write_fresh(semantic_path, semantic, deadline)
        closure = {}
        def add(path, expected=None):
            row = pin(root, canonical(path, root), deadline)
            if expected is not None:
                require(row['sha256'] == expected['sha256'] and
                        ('bytes' not in expected or row['bytes'] == expected['bytes']), 'closure file changed')
            require(row['path'] not in closure or closure[row['path']] == row, 'conflicting closure pin')
            closure[row['path']] = row
        def visit(value, trail=()):
            if type(value) is list:
                for item in value:
                    visit(item, trail)
            elif type(value) is dict:
                if 'path' in value and 'sha256' in value:
                    if trail and trail[0] in ('classFiles', 'jarEntries'):
                        return
                    path = value['path']
                    if trail and trail[0] == 'sourceFiles':
                        path = str(context['inputs']['source_manifest'].parent / relative(path))
                    add(path, value)
                for key, item in value.items():
                    visit(item, trail + (key,))
        visit(report); visit(semantic)
        for row in context['contract']['jdk_files']:
            member = PurePosixPath(row['path']).relative_to('jdk-21.0.12.1+1')
            add(context['inputs']['jdk_root'] / member, row)
        for phase in report['phases']:
            add(receipt.parent / (phase['name'] + '.process.json'))
        for iteration in (1, 2):
            for row in context['contract']['classFiles']:
                add(receipt.parent / ('classes-' + str(iteration)) / relative(row['path']), row)
        for name in ('compile-classpath.txt', 'remap-libraries.txt'):
            add(receipt.parent / name)
        for path in [receipt, semantic_path, context['layout_path'], context['contract_path'],
                     Path(__file__).absolute(), context['paths']['staging_tool'], *context['tool_paths']]:
            add(path)
        for row in context['lock_pins'].values():
            add(root / row['path'], row)
        evidence = {'schema': staging.BUNDLE_SCHEMA, **staging.FLAGS,
                    'artifact': pin(root, Path(report['artifact']['path']), deadline),
                    'source_manifest': pin(root, context['inputs']['source_manifest'], deadline),
                    'compile_receipt': pin(root, receipt, deadline),
                    'inputs': sorted(closure.values(), key=lambda row: row['path'])}
        bundle_path = output / 'bundle.json'
        write_fresh(bundle_path, evidence, deadline)
        provenance = {'schema': staging.REVIEW_SCHEMA, 'scope': staging.REVIEW_SCOPE,
                      'source_namespace': 'intermediary', 'artifact_namespace': 'intermediary',
                      'bundle_sha256': pin(root, bundle_path, deadline)['sha256'],
                      'artifact_sha256': evidence['artifact']['sha256'],
                      'source_manifest_sha256': evidence['source_manifest']['sha256'],
                      'compile_receipt_sha256': evidence['compile_receipt']['sha256'],
                      'closure_sha256': hashlib.sha256(encoded(evidence['inputs'])).hexdigest()}
        # Provenance is generated only from the frozen semantic gate above; caller receipts/hashes
        # are never accepted as independent approval. The frozen staging gate rechecks closure.
        staging.verify_source_binding(root, pin(root, bundle_path, deadline), validated_provenance=provenance)
        deadline.check()
        provenance_path = output / 'validated-provenance.json'
        write_fresh(provenance_path, provenance, deadline)
        result = {'schema': 1, 'status': ('PASS_EXISTING_COMPILE_REVALIDATED_NOT_FRESH_EXECUTION' if replay
                   else 'PASS_PIPELINE_COMPILE_STAGING_NOT_RUNTIME_ACCEPTANCE'), **FLAGS,
                  'compilerStartedByAdapter': False, 'existingEvidenceOnly': replay,
                  'operationDeadlineEpoch': deadline.epoch, 'compileDeadlineEpoch': report.get('callerDeadlineEpoch'),
                  'bundle': pin(root, bundle_path, deadline),
                  'validatedProvenance': pin(root, provenance_path, deadline),
                  'semanticValidation': pin(root, semantic_path, deadline),
                  'dependencyBindings': context['bindings'], 'closureFiles': len(evidence['inputs'])}
        write_fresh(output / 'result.json', result, deadline)
        return result


def finalize(consumer_root, layout_path, operation, deadline_epoch):
    """Call only after the outer owner establishes successful exit AND no live children."""
    deadline = Deadline(deadline_epoch)
    context = resolve(consumer_root, layout_path, deadline)
    operation = output_path(context, operation)
    require(load(operation / 'request.json') == request(context, operation, deadline), 'prepared request changed')
    require(load(operation / 'portable-config.json') == context['config'], 'portable config changed')
    return bundle(context, operation / 'build/result.json', operation / 'staging', deadline,
                  original_deadline=deadline_epoch, expected_config=operation / 'portable-config.json')


def validate_existing(consumer_root, layout_path, receipt, output, deadline_epoch):
    """Recheck old actual evidence. Does not renew or claim a new compiler deadline/run."""
    deadline = Deadline(deadline_epoch)
    return bundle(resolve(consumer_root, layout_path, deadline), receipt, output, deadline, replay=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'command', 'finalize', 'validate-existing'))
    parser.add_argument('--consumer-root', required=True, type=Path)
    parser.add_argument('--layout', required=True, type=Path)
    parser.add_argument('--deadline-epoch', required=True, type=float)
    parser.add_argument('--operation', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'validate-existing':
        parser.error('--receipt and --output required') if args.receipt is None or args.output is None else None
        require(args.operation is None, '--operation not used for existing evidence')
        result = validate_existing(args.consumer_root, args.layout, args.receipt, args.output, args.deadline_epoch)
    else:
        parser.error('--operation required') if args.operation is None else None
        require(args.receipt is None and args.output is None, '--receipt/--output not used for prepared operations')
        action = {'prepare': prepare, 'command': compiler_command, 'finalize': finalize}[args.action]
        result = action(args.consumer_root, args.layout, args.operation, args.deadline_epoch)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
