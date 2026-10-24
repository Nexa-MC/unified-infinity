"""Fresh diagnostic role overlay; never mutates or re-labels baseline assembly."""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import zipfile

import pair_assembly as base
import diagnostic_fml_build as build

OUTPUT = 'work/network-pair-assembled-hardware-skip-diagnostic'
RESULT = OUTPUT + '/diagnostic-assembly.json'
POLICY = 'META-INF/unified-admission/installation.json'
SCOPE = {'diagnosticProfile': 'system-report-hardware-inventory-skip-v1',
         'behavioralChange': True,
         'hardwareScope': 'all-SystemReport-instances-including-crash-reports',
         'nonHardwareFieldsPreserved': True, 'gameJarBytesModified': False}


def require(value, message):
    if not value:
        raise ValueError(message)


def require_scope(value):
    require(all(type(value.get(k)) is type(v) and value.get(k) == v for k, v in SCOPE.items()),
            'Diagnostic hardware-skip scope changed')


def check(root, row):
    path = base.local(root, row['path'])
    require(base.pin(path) == row, 'Changed diagnostic or baseline input')
    return path


def relocate(value, old, new):
    if isinstance(value, dict):
        return {k: relocate(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [relocate(v, old, new) for v in value]
    if isinstance(value, str) and (value == str(old) or value.startswith(str(old) + '/')):
        return str(new) + value[len(str(old)):]
    return value


def rewrite_command(command, old, new, stock=None, derivative=None):
    """Only replace exact path-list entries and the exact profile prefix."""
    result = []
    replacements = 0
    for token in command:
        require(not token.startswith('@'), 'Diagnostic overlay requires flattened arguments')
        prefix, value = ('', token)
        if token.startswith('-D') and '=' in token:
            key, value = token.split('=', 1)
            prefix = key + '='
        parts = value.split(':')
        translated = []
        for part in parts:
            if stock is not None and part == str(stock):
                translated.append(str(derivative))
                replacements += 1
            else:
                translated.append(relocate(part, old, new))
        result.append(prefix + ':'.join(translated))
    if stock is not None:
        require(replacements > 0, 'Stock FML absent from native command')
        require(not any(str(stock) in item for item in result), 'Stock FML remains in diagnostic command')
    return result


def verify_configured_entries(derivative, owner):
    with zipfile.ZipFile(derivative) as source, zipfile.ZipFile(owner) as configured:
        before, after = source.namelist(), configured.namelist()
        require(len(before) == len(set(before)) and len(after) == len(set(after))
                and set(before) == set(after), 'Configured BOOT inventory changed')
        require(source.read(POLICY) == b'{"schema":1,"approved":false}\n', 'Wrong unconfigured policy')
        for name in before:
            if name != POLICY:
                require(source.read(name) == configured.read(name), 'Configured BOOT changed non-policy payload')


def configure_unified(assembler, spec, spec_path, derivative, manifest, output):
    """Use unchanged argument/policy preparation and validation, truthful receipt."""
    require(not output.exists(), 'Stale diagnostic configured output')
    base.save(spec_path, spec)
    policy, args, java = assembler.prepare(spec)
    owner_row = next(row for row in policy['artifacts'] if row['role'] == 'BOOT_OWNER')
    owner = Path(policy['installationDirectory']) / owner_row['path']
    require(not owner.exists() and owner != derivative, 'Diagnostic BOOT must be fresh')
    raw = (json.dumps(policy, sort_keys=True, separators=(',', ':')) + '\n').encode()
    owner.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(derivative) as original:
        names = original.namelist()
        require(len(names) == len(set(names)), 'Duplicate derivative')
        require(POLICY in names and original.read(POLICY) == b'{"schema":1,"approved":false}\n',
                'Unified derivative must retain exact unapproved baseline placeholder')
        require(not any(n.upper().endswith(('.SF', '.RSA', '.DSA')) for n in names), 'Signed derivative refused')
        with zipfile.ZipFile(owner, 'w', zipfile.ZIP_DEFLATED) as target:
            for name in sorted(names):
                if name == POLICY:
                    continue
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(info, original.read(name))
            info = zipfile.ZipInfo(POLICY, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, raw)
    verify_configured_entries(derivative, owner)
    receipt = {'schema': 'diagnostic-configured-fml-v1', 'diagnostic_only': True,
               'baseline_acceptance': False, 'artifact': str(owner), 'sha256': base.sha(owner),
               'installationPolicySha256': hashlib.sha256(raw).hexdigest(),
               'diagnosticManifest': base.pin(manifest), 'unconfiguredDerivative': base.pin(derivative),
               'assemblySpec': base.pin(spec_path), 'sourceLaunch': spec['launchSource'], **SCOPE}
    output.mkdir()
    receipt_path = output / 'build-receipt.json'
    base.save(receipt_path, receipt)
    result = assembler.v.validate(receipt_path, base.sha(receipt_path), args, policy['environment'])
    result.update(diagnostic_only=True, baseline_acceptance=False, jvmStarted=False,
                  configuredOwner=str(owner), configuredOwnerSha256=base.sha(owner),
                  buildReceipt=str(receipt_path), buildReceiptSha256=base.sha(receipt_path), **SCOPE,
                  javaExecutable=java, rawArgumentsStored=False, argumentCount=len(args))
    base.save(output / 'assembly-report.json', result)
    return [java, *args], result, [base.pin(spec_path), base.pin(receipt_path),
                                 base.pin(output / 'assembly-report.json')]


def assemble(repo, consumer, manifest, *, profile, build_proof):
    import seal_pair
    root = base.canonical(consumer)
    repo = base.canonical(repo)
    manifest = base.local(root, manifest)
    verified = build.validate(repo, root, manifest, profile, build_proof)
    baseline_path, baseline, proof_inputs, original_root = seal_pair.refreshed_assembly(root, profile, build_proof)
    out = root / OUTPUT
    require(not out.exists(), 'Fresh diagnostic assembly root required')
    for relative in (base.SUPPORT, base.PROFILES, base.ASSEMBLED, base.REFRESHED_SUPPORT,
                     base.REFRESHED_PROFILES, base.REFRESHED_ASSEMBLED):
        preserved = root / relative
        require(not out.is_relative_to(preserved) and not preserved.is_relative_to(out), 'Overlapping diagnostic output')
    assembler_path = root / 'work/api1/source-workspace/fml-unified/tools/assemble_installation.py'
    require(any(row['path'] == str(assembler_path) for row in proof_inputs), 'Unpinned installation assembler')
    assembler = base.module('diagnostic_original_installation_assembler', assembler_path)
    groups = {}
    extra = [base.pin(manifest), base.pin(baseline_path), *proof_inputs]
    for row in verified['inputPins']:
        extra.append(base.pin(root / row['path']))
    out.mkdir()
    for target in ('native-neoforge', 'unified'):
        group = baseline['groups'][target]
        roles = {}
        folder = out / target
        folder.mkdir()
        for side in ('server', 'client'):
            original_seal = check(root, group['roles'][side])
            role = json.loads(original_seal.read_text())
            old = base.local(root, role['cwd'])
            require(old == original_root / target / side, 'Unexpected baseline role root')
            for row in role['files']:
                check(root, row)
            expected_inside = {r['path']: r for r in role['files'] if Path(r['path']).is_relative_to(old)}
            actual_inside = {str(p): base.pin(p) for p in old.rglob('*') if p.is_file()}
            require(expected_inside == actual_inside and not any(p.is_symlink() for p in old.rglob('*')),
                    'Baseline role is not pristine or contains redirected input')
            game = folder / side
            shutil.copytree(old, game)
            copied = relocate(role, old, game)
            assembly = None
            if target == 'native-neoforge':
                stock = []
                for row in role['files']:
                    path = Path(row['path'])
                    if path.suffix == '.jar':
                        with zipfile.ZipFile(path) as z:
                            if 'net/neoforged/fml/loading/FMLLoader.class' in z.namelist():
                                stock.append(path)
                require(len(stock) == 1, 'Native role requires exactly one stock FML input')
                command = rewrite_command(role['command'], old, game, stock[0], verified['artifacts']['native'])
            else:
                prior = role['assembly']
                prior_receipt = Path(prior['buildReceipt'])
                require(base.sha(prior_receipt) == prior['buildReceiptSha256'], 'Baseline configured receipt changed')
                prior_data = json.loads(prior_receipt.read_text())
                original_spec = original_root / target / (side + '-assembly-spec.json')
                require(base.sha(original_spec) == prior_data['assemblySpecSha256'], 'Baseline configured spec changed')
                spec = relocate(json.loads(original_spec.read_text()), old, game)
                copied_owner = game / Path(prior['configuredOwner']).relative_to(old)
                require(base.sha(copied_owner) == prior['configuredOwnerSha256'], 'Copied baseline BOOT changed')
                copied_owner.unlink()  # Only the just-created diagnostic copy, never baseline.
                command, assembly, pins = configure_unified(assembler, spec,
                    folder / (side + '-assembly-spec.json'), verified['artifacts']['unified'], manifest,
                    folder / (side + '-configured'))
                extra.extend(pins)
                extra.extend([base.pin(prior_receipt), base.pin(original_spec)])
            files = [r for r in role['files'] if not Path(r['path']).is_relative_to(old)]
            files.extend(base.pin(p) for p in game.rglob('*') if p.is_file())
            files.extend(base.pin(p) for p in verified['artifacts'].values())
            files = list({r['path']: r for r in files}.values())
            # Reuse the reviewed command grammar with the new exact role inputs.
            validator = base.module('diagnostic_original_pair_validator', root / base.REFRESHED_SUPPORT / 'assemble_pairs.py')
            validator.validate_command(command, side, game, group['port'], files)
            copied.update(command=command, files=sorted(files, key=lambda r: r['path']),
                          assembly=assembly, diagnostic_only=True, baseline_acceptance=False,
                          diagnosticManifest=base.pin(manifest), baselineRole=base.pin(original_seal), **SCOPE)
            path = folder / (side + '-launch-seal.json')
            roles[side] = base.save(path, copied)
            extra.append(base.pin(original_seal))
        groups[target] = {'port': group['port'], 'roles': roles, 'sourceFixture': group['sourceFixture']}
    result = {'schema': 'diagnostic-pair-assembly-v1', 'diagnostic_only': True,
              'baseline_acceptance': False, 'gameAcceptance': False, 'gameLaunched': False,
              'jvmStarted': False, 'manifest': base.pin(manifest), 'baselineAssembly': base.pin(baseline_path),
              'assemblyRoot': str(out), 'groups': groups,
              'inputs': list({r['path']: r for r in extra}.values()), **SCOPE}
    build.validate(repo, root, manifest, profile, build_proof)
    seal_pair.refreshed_assembly(root, profile, build_proof)
    base.save(root / RESULT, result)
    return root / RESULT


def validate(repo, consumer, manifest, *, profile, build_proof):
    import seal_pair
    root = base.canonical(consumer)
    verified = build.validate(repo, root, manifest, profile, build_proof)
    baseline_path, baseline, baseline_pins, original_root = seal_pair.refreshed_assembly(root, profile, build_proof)
    path = root / RESULT
    value = json.loads(path.read_text())
    require_scope(value)
    require(value['schema'] == 'diagnostic-pair-assembly-v1' and value['diagnostic_only'] is True
            and value['baseline_acceptance'] is False and value['gameAcceptance'] is False
            and value['gameLaunched'] is False and value['jvmStarted'] is False,
            'Diagnostic assembly cannot assert baseline acceptance')
    require(value['manifest'] == base.pin(manifest) and value['baselineAssembly'] == base.pin(baseline_path)
            and value['assemblyRoot'] == str(root / OUTPUT), 'Diagnostic ancestry changed')
    require(set(value['groups']) == {'native-neoforge', 'unified'}, 'Missing diagnostic groups')
    pins = [base.pin(path), base.pin(manifest), base.pin(baseline_path), *baseline_pins]
    pins.extend(base.pin(root / row['path']) for row in verified['inputPins'])
    for row in value['inputs']:
        pins.append(base.pin(check(root, row)))
    for target, group in value['groups'].items():
        require(group['port'] == baseline['groups'][target]['port'] and set(group['roles']) == {'server', 'client'},
                'Diagnostic role or port changed')
        for side, row in group['roles'].items():
            rolepath = check(root, row)
            require(rolepath == root / OUTPUT / target / (side + '-launch-seal.json'), 'Role seal belongs elsewhere')
            role = json.loads(rolepath.read_text())
            require_scope(role)
            original_seal = check(root, baseline['groups'][target]['roles'][side])
            original = json.loads(original_seal.read_text())
            old = original_root / target / side
            game = root / OUTPUT / target / side
            require(role['cwd'] == str(root / OUTPUT / target / side) and role['diagnostic_only'] is True
                    and role['baseline_acceptance'] is False and role['diagnosticManifest'] == base.pin(manifest),
                    'Diagnostic role binding changed')
            require(role['baselineRole'] == base.pin(original_seal), 'Diagnostic role ancestry changed')
            for key in ('original_mods', 'managed_mods', 'probe_path'):
                require(role[key] == relocate(original[key], old, game), 'Diagnostic mod identity changed')
            pins.append(base.pin(rolepath))
            for item in role['files']:
                # Match seal_pair's existing mutable-client-options contract.
                # Initial pristine-copy validation above still checks these bytes;
                # the untouched Indigo baseline and supervisor govern runtime use.
                if item['path'] == str(game / 'options.txt'):
                    continue
                check(root, item)
            if target == 'native-neoforge':
                stock = []
                for item in original['files']:
                    candidate = Path(item['path'])
                    if candidate.suffix == '.jar':
                        with zipfile.ZipFile(candidate) as archive:
                            if 'net/neoforged/fml/loading/FMLLoader.class' in archive.namelist():
                                stock.append(candidate)
                require(len(stock) == 1 and role['command'] == rewrite_command(original['command'], old, game,
                        stock[0], verified['artifacts']['native']), 'Diagnostic native command changed')
            else:
                assembler = base.module('diagnostic_revalidate_configured_owner',
                    root / 'work/api1/source-workspace/fml-unified/tools/assemble_installation.py')
                receipt_path = Path(role['assembly']['buildReceipt'])
                require(receipt_path == root / OUTPUT / target / (side + '-configured/build-receipt.json'),
                        'Configured diagnostic receipt belongs elsewhere')
                require(base.sha(receipt_path) == role['assembly']['buildReceiptSha256'], 'Configured receipt changed')
                receipt = json.loads(receipt_path.read_text())
                require_scope(receipt)
                require(receipt['diagnostic_only'] is True and receipt['baseline_acceptance'] is False
                        and receipt['diagnosticManifest'] == base.pin(manifest)
                        and receipt['unconfiguredDerivative'] == base.pin(verified['artifacts']['unified']),
                        'Configured diagnostic provenance changed')
                verify_configured_entries(verified['artifacts']['unified'], Path(receipt['artifact']))
                spec_path = check(root, receipt['assemblySpec'])
                spec = json.loads(spec_path.read_text())
                policy, arguments, java = assembler.prepare(spec)
                require(role['command'] == [java, *arguments], 'Configured diagnostic arguments changed')
                checked = assembler.v.validate(receipt_path, base.sha(receipt_path), arguments, policy['environment'])
                require(checked['classOwnerCount'] == 1 and checked['gameLaunched'] is False,
                        'Configured diagnostic owner validation failed')
                pins.extend([base.pin(receipt_path), base.pin(spec_path)])
    return path, value, list({r['path']: r for r in pins}.values()), root / OUTPUT
