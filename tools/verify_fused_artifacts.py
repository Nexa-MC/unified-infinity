#!/usr/bin/env python3
"""Verify the source-fusion package boundary without executing artifact code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tomllib
import zipfile

DESCRIPTORS = (
    'cpw.mods.modlauncher.api.ITransformationService',
    'net.neoforged.neoforgespi.language.IModLanguageLoader',
    'net.neoforged.neoforgespi.locating.IModFileReader',
    'net.neoforged.neoforgespi.coremod.ICoreMod',
    'net.neoforged.neoforgespi.locating.IModFileCandidateLocator',
    'net.neoforged.neoforgespi.locating.IDependencyLocator',
)
MODEL = 'org/sinytra/connector/infinity/inventory/'
MOD_ANNOTATION = b'Lnet/neoforged/fml/common/Mod;'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def open_archive(path):
    archive = zipfile.ZipFile(path)
    entries = archive.infolist()
    names = [i.filename for i in entries]
    if len(entries) > 50000 or len(names) != len(set(names)):
        raise ValueError('Duplicate or excessive artifact entries')
    if sum(i.file_size for i in entries) > 256 * 1024 * 1024:
        raise ValueError('Artifact exceeds verification byte budget')
    for entry in entries:
        name = PurePosixPath(entry.filename)
        if name.is_absolute() or '..' in name.parts or entry.file_size > 32 * 1024 * 1024:
            raise ValueError('Unsafe artifact entry')
    return archive

def require(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    parser = argparse.ArgumentParser()
    for name in ('service', 'game', 'fml', 'source_root', 'output'):
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--product', type=Path)
    args = parser.parse_args()
    with open_archive(args.service) as service, open_archive(args.game) as game, open_archive(args.fml) as fml:
        sn, gn, fn = set(service.namelist()), set(game.namelist()), set(fml.namelist())
        require('org/sinytra/connector/infinity/FmlCompatibilityComponent.class' in sn, 'Missing SERVICE component')
        require('org/sinytra/connector/mod/FmlGameCompatibilityComponent.class' in gn, 'Missing GAME component')
        for name in DESCRIPTORS:
            require('META-INF/services/' + name not in sn, 'Autonomous compatibility SPI remains: ' + name)
        require(not any(n.startswith(MODEL) and n.endswith('.class') for n in sn | gn), 'Duplicate BOOT model packaged')
        require(MODEL + 'AdmissionSession.class' in fn, 'BOOT owner lacks authoritative session')
        require('net/neoforged/fml/loading/unified/CompatibilityRuntime.class' in fn, 'FML owner is absent')
        for name in ('ConnectorMod', 'ConnectorModClient'):
            require(MOD_ANNOTATION not in game.read('org/sinytra/connector/mod/' + name + '.class'), 'Ordinary @Mod annotation remains')
        metadata = tomllib.loads(game.read('META-INF/neoforge.mods.toml').decode())
        require(metadata['modLoader'] == 'unified_internal' and metadata['loaderVersion'] == '[1]', 'GAME uses ordinary mod loader')
        require({m['modId'] for m in metadata['mods']} == {'connector', 'unified_forge52_adapter'}, 'Legacy capability declarations changed')
        require(any(m['config'] == 'connector.mixins.json' for m in metadata['mixins']), 'Original compatibility mixins lost')
        nested = json.loads(service.read('META-INF/jarjar/metadata.json'))
        nested_ids = [j['identifier'] for j in nested['jars']]
        require(not any(i.get('artifact') == 'connector-mod' for i in nested_ids), 'GAME implementation remains embedded in SERVICE')
        require(any(i.get('artifact') == 'runtime' for i in nested_ids), 'Adapter runtime dependency lost')
        identity = json.loads(service.read('META-INF/unified-infinity/build-identity.json'))
        require(identity['schema'] == 2, 'Missing expanded source identity')
        seen = set()
        for item in identity['sources']:
            name = PurePosixPath(item['path'])
            require(not name.is_absolute() and '..' not in name.parts and item['path'] not in seen, 'Invalid source identity path')
            seen.add(item['path'])
            if name.parts[0] == 'loader-sources':
                path = args.source_root.parent.joinpath(*name.parts[1:])
            else:
                path = args.source_root.joinpath(*name.parts)
            require(digest(path) == item['sha256'], 'Source changed after compilation: ' + item['path'])
        require(any(p.startswith('loader-sources/fml-unified/src/') for p in seen), 'FML source excluded from identity')
        require(any(p.startswith('loader-sources/admission-bootstrap/src/') for p in seen), 'BOOT source excluded from identity')
    if args.product:
        with open_archive(args.product) as product:
            pn = set(product.namelist())
            require(not any(n.startswith(MODEL) and n.endswith('.class') for n in pn), 'Product duplicates BOOT model')
            require(MOD_ANNOTATION not in product.read('dev/modcompat/runtime/bundle/RuntimeBundle.class'), 'Product ordinary @Mod annotation remains')
            metadata = tomllib.loads(product.read('META-INF/neoforge.mods.toml').decode())
            require(metadata['modLoader'] == 'unified_internal', 'Product is still ordinary mod bootstrap')
    paths = {'service': args.service, 'game': args.game, 'fml': args.fml}
    if args.product:
        paths['product'] = args.product
    report = {'schema': 1, 'result': 'PASS_STATIC_PACKAGE_BOUNDARIES',
              'source_records_verified': len(seen),
              'artifacts': {k: {'path': str(v), 'sha256': digest(v)} for k, v in paths.items()},
              'runtime_validation': 'NOT_RUN_BY_THIS_CHECK'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
