"""CLI entry point. Exit 0: metadata pass or runtime deferred; 1: rejected; 2: invocation/output error."""
import argparse
import json
import sys
from pathlib import Path

from .core import Target, plan


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only JAR metadata admission. Does not prove runtime compatibility.')
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('plan', help='inspect original JAR bytes and emit a JSON metadata plan')
    command.add_argument('jars', nargs='+', type=Path)
    command.add_argument('--minecraft', default='1.21.1')
    command.add_argument('--environment', choices=('client', 'server'), default='client')
    command.add_argument('--java-version', default='21', help='declared target Java version; not a local JVM probe')
    command.add_argument('--fabric-loader-version')
    command.add_argument('--neoforge-version')
    command.add_argument('--fml-version', help='javafml language-loader version, distinct from NeoForge version')
    command.add_argument('--bundled-inventory', type=Path)
    command.add_argument('--runtime-authoritative', action='store_true', help='defer loader/candidate decisions to pinned NeoForge FML/Connector; only safety/malformed-input/invalid-target errors block')
    command.add_argument('--output', type=Path, help='new JSON file; existing files are never overwritten')
    args = parser.parse_args(argv)
    target = Target(args.minecraft, args.environment, args.java_version, args.fabric_loader_version, args.neoforge_version, args.fml_version)
    report = plan(args.jars, target=target, bundled_inventory=args.bundled_inventory, runtime_authoritative=args.runtime_authoritative)
    serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + '\n'
    if args.output:
        try:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(serialized)
        except OSError as exc:
            print(f'Cannot create report without overwriting existing data: {exc}', file=sys.stderr)
            return 2
    else:
        sys.stdout.write(serialized)
    return 0 if report['admission'] in ('metadata_pass', 'runtime_deferred') else 1
