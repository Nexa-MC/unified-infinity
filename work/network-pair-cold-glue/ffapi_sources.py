#!/usr/bin/env python3
"""Explicit, portable FFAPI-refreshed source and restoration input profile.

Historical source_materialize.py and its default manifest/lock are unchanged.
This module never downloads, launches a JVM, edits historical files or accepts
compiled outputs. A caller must explicitly select the refreshed profile.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os

HERE = Path(__file__).resolve().parent
AREA = 'work/network-pair-cold-glue'
PROFILE_REL = AREA + '/profiles/ffapi-20261023.json'
PROFILE_SHA256 = '902b79f990a210fd63d864f463143f4f26cd6f2c0eba8fd9f075efca86e8d438'
DELTA_REL = AREA + '/profiles/ffapi-refresh-inputs.json'
DELTA_SHA256 = '328ec2545be9abfea0365359a71ff601748a82938545847bed2f1606eaebaf6d'
MANIFEST_REL = AREA + '/profiles/ffapi-source-manifest.json'
MANIFEST_SHA256 = '3b61001d76f6ffc9a30c4aab440411e29e629432f0dd17aae2a4554a5b6d52f5'
LOCK_REL = AREA + '/profiles/ffapi-core-dependency-lock.json'
LOCK_SHA256 = '43ac0ce038cb00da23f0ae625f64c4b1bb83251c82ee2269b6ae698f50d4389b'
BASE_MANIFEST_SHA256 = '70ebe485d8266e821cae41eec10495350b3a4081f2f75bbfd09eace2edf892c3'
BASE_LOCK_SHA256 = '72a7503a405dd2dd80be2466164b472f4db263707b51261b03840c410a53214a'
MATERIALIZER_SHA256 = 'b49f42bcbc5f81d980526550f412e9f8efcde37eceb14e304f950cf95061ad41'
BASE_IDENTITY = '54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6'
IDENTITY = '8f53a44cf220eaddca79cf68be6b4c76cae74f7a9f3bc5982ac7d9719b211170'
AGGREGATE_SHA256 = 'f66cf2e5604053ae073652c4baf93721173f06560bf93458d427341f13892690'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    path = Path(path).absolute()
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'Symlink input rejected: ' + str(path))
    require(path.is_file(), 'Missing exact input: ' + str(path))
    data = path.read_bytes()
    require(digest(data) == expected, 'Input SHA-256 differs: ' + str(path))
    return data


def _local(relative):
    # Only constant reviewed relative paths are accepted here.
    return HERE / Path(relative).relative_to(AREA)


def _materializer():
    path = HERE / 'source_materialize.py'
    pinned(path, MATERIALIZER_SHA256)
    # Load a private module instance; do not alter the historical module globals.
    spec = importlib.util.spec_from_file_location('_ffapi_pinned_source_materializer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MANIFEST = _local(MANIFEST_REL)
    module.MANIFEST_SHA256 = MANIFEST_SHA256
    return module


def verify_bundle():
    """Recheck the immutable selected input closure without creating a consumer."""
    base = json.loads(pinned(HERE / 'source-manifest.json', BASE_MANIFEST_SHA256))
    old_lock = json.loads(pinned(HERE / 'core-dependency-lock.json', BASE_LOCK_SHA256))
    manifest = json.loads(pinned(_local(MANIFEST_REL), MANIFEST_SHA256))
    lock = json.loads(pinned(_local(LOCK_REL), LOCK_SHA256))
    delta = json.loads(pinned(_local(DELTA_REL), DELTA_SHA256))
    profile = json.loads(pinned(_local(PROFILE_REL), PROFILE_SHA256))
    require(profile.get('coreIdentity') == IDENTITY, 'Shared profile source identity differs')
    require(profile.get('ffapiDelta', {}).get('sha256') == DELTA_SHA256 and
            profile['ffapiDelta'].get('path') == DELTA_REL, 'Shared profile FFAPI delta differs')
    require(delta['baseSourceManifestSha256'] == BASE_MANIFEST_SHA256 and
            delta['baseCoreLockSha256'] == BASE_LOCK_SHA256, 'FFAPI delta belongs to another baseline')
    require(delta['moduleCount'] == 42 and delta['changedArtifactCount'] == 46 and
            delta['changedIdentityDependencies'] == 23, 'FFAPI scope differs')
    require(delta['runtimeAcceptance'] is False and delta['newOutputAcceptancePins'] is None,
            'Input record cannot accept runtime or output artifacts')
    require(manifest['candidate_identity'] == lock['candidate_identity'] == delta['coreIdentity'] == IDENTITY,
            'Mixed input identity profiles')
    require(delta['historicalCoreIdentity'] == base['candidate_identity'] == BASE_IDENTITY,
            'Historical identity differs')
    old_files = {r['destination']: r for r in base['files']}
    new_files = {r['destination']: r for r in manifest['files']}
    require(set(old_files) == set(new_files), 'Source destination roster changed')
    expected = {
        'portable-bootstrap/verification-metadata.xml',
        'work/api1/source-workspace/connector-four-loader/gradle/verification-metadata.xml',
        'work/api1/runtime-bundle/gradle/verification-metadata.xml',
        'work/emi-render-integration/build-identity.json',
    }
    require({k for k in old_files if old_files[k] != new_files[k]} == expected,
            'Unrelated source binding changed')
    require({k: v for k, v in manifest['archives'].items() if k != 'ffapi-refresh'} == base['archives'],
            'Historical source archive changed')
    old_artifacts = {r['path']: r for r in old_lock['artifacts']}
    new_artifacts = {r['path']: r for r in lock['artifacts']}
    require(set(old_artifacts) == set(new_artifacts), 'Restoration coordinate roster changed')
    changed = {r['path']: r for r in delta['observations'] if r['changed']}
    prefix = 'source-workspace/pinned-build-maven/'
    require({p for p in old_artifacts if old_artifacts[p] != new_artifacts[p]} == {prefix + p for p in changed},
            'Unrelated restoration record changed')
    for path, change in changed.items():
        old, new = old_artifacts[prefix + path], new_artifacts[prefix + path]
        require((old['sha256'], old['bytes']) == (change['oldSha256'], change['oldBytes']), 'Wrong baseline restoration pin')
        require((new['sha256'], new['bytes']) == (change['newSha256'], change['newBytes']), 'Wrong refreshed restoration pin')
        require(new['urls'] == old['urls'] and new['version'] == old['version'], 'Restoration route/version changed')
    require(lock['allowedHosts'] == old_lock['allowedHosts'], 'Restoration host scope changed')
    aggregates = [r for r in lock['artifacts'] if r['artifact'] == 'forgified-fabric-api' and r['filename'].endswith('.jar')]
    require(len(aggregates) == 1 and aggregates[0]['sha256'] == AGGREGATE_SHA256 == delta['runtimeAggregateSha256'],
            'Runtime FFAPI aggregate changed')
    require(lock['counts']['included_bytes'] == sum(r['bytes'] for r in lock['artifacts']), 'Restoration byte total differs')
    return {'status': 'FFAPI_INPUT_BUNDLE_VERIFIED', 'coreIdentity': IDENTITY,
            'ffapiInputsSha256': DELTA_SHA256, 'source_manifest_sha256': MANIFEST_SHA256,
            'coreLockSha256': LOCK_SHA256, 'profileSha256': PROFILE_SHA256,
            'runtimeAcceptance': False, 'outputAcceptancePinsChanged': False}


def core_lock():
    """Return only the reviewed refreshed restoration lock, never a fallback."""
    pinned(_local(LOCK_REL), LOCK_SHA256)
    return _local(LOCK_REL)


def _support_records(profile):
    names = {AREA + '/' + name for name in
             ('build_candidate.py', 'bounded_process.py', 'fml_metadata.py', 'forge_fixture.py',
              'generated_output_diagnostics.py', 'product_tuple_diagnostics.py',
              'profiles/product-diagnostic-baseline.json')}
    rows = {row['path']: row for row in profile['inputPins'] if row['path'] in names}
    require(set(rows) == names, 'Reviewed build-support source roster differs')
    return rows


def prepare(repo_root, consumer_root):
    """Create one fresh exact source consumer and copy its reviewed profile data."""
    bundle = verify_bundle()
    module = _materializer()
    # Validate selected profile input bytes before the first consumer write.
    copies = {relative: pinned(_local(relative), expected) for relative, expected in
              [(PROFILE_REL, PROFILE_SHA256), (DELTA_REL, DELTA_SHA256), (LOCK_REL, LOCK_SHA256)]}
    profile = json.loads(copies[PROFILE_REL])
    for relative, row in _support_records(profile).items():
        data = pinned(_local(relative), row['sha256'])
        require(len(data) == row['bytes'], 'Reviewed build support size differs')
        copies[relative] = data
    report = module.prepare(repo_root, consumer_root)
    root = Path(consumer_root).absolute()
    for relative, data in copies.items():
        target = root / relative
        module._no_symlink_ancestors(target)
        require(not os.path.lexists(target), 'Refusing existing profile input: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    report.update(bundle)
    report['status'] = 'PASS_FFAPI_SOURCE_MATERIALIZATION_ONLY'
    report['profile'] = PROFILE_REL
    # The materializer's original receipt remains present; this adds the explicit
    # selected-profile binding without rewriting a historical source file.
    with (root / 'ffapi-source-materialization.json').open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    return report


def verify_sources(consumer_root):
    bundle = verify_bundle()
    root = Path(consumer_root).absolute()
    for relative, expected in [(PROFILE_REL, PROFILE_SHA256), (DELTA_REL, DELTA_SHA256), (LOCK_REL, LOCK_SHA256)]:
        pinned(root / relative, expected)
    profile = json.loads(pinned(root / PROFILE_REL, PROFILE_SHA256))
    for relative, row in _support_records(profile).items():
        require(len(pinned(root / relative, row['sha256'])) == row['bytes'], 'Consumer build support size differs')
    result = _materializer().verify_sources(root)
    require(result['candidate_identity'] == IDENTITY, 'Consumer source identity differs')
    result.update(bundle)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'prepare', 'verify'])
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--consumer-root', type=Path)
    args = parser.parse_args()
    if args.action == 'inspect': result = verify_bundle()
    elif args.action == 'prepare':
        parser.error('--repo-root and --consumer-root are required') if args.repo_root is None or args.consumer_root is None else None
        result = prepare(args.repo_root, args.consumer_root)
    else:
        parser.error('--consumer-root is required') if args.consumer_root is None else None
        result = verify_sources(args.consumer_root)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
