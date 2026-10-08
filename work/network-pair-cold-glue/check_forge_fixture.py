#!/usr/bin/env python3
"""Exercise original Forge fixture source/ordering guards without any JVM."""
import ast
import json
from pathlib import Path
import tempfile
import build_candidate
import forge_fixture
import source_materialize


def rejected(function):
    try:
        function()
    except (ValueError, FileExistsError):
        return
    raise AssertionError('Expected fail-closed rejection')


def main():
    repo = Path(__file__).resolve().parents[2]
    checks = []
    with tempfile.TemporaryDirectory(prefix='forge-fixture-port-') as temporary:
        consumer = Path(temporary) / 'consumer'
        source_materialize.prepare(repo, consumer)
        prepared = build_candidate.prepare(consumer)
        assert len(prepared['forgeFixtureSourcePreparation']['sourceInputs']) == 8
        checks.append('fresh preparation restores eight exact fixture source/config/resource files')
        assert prepared['forgeFixtureExpectedSha256'] == forge_fixture.EXPECTED
        checks.append('build plan requires exact original fixture3a016e')
        fixture = consumer / 'work/api1/four-loader/forge-probe'
        source = fixture / 'src/dev/infinity/forgeprobe/ForgeProbe.java'
        original = source.read_bytes()
        source.write_bytes(original + b'\n')
        rejected(lambda: forge_fixture.verify_sources(consumer))
        source.write_bytes(original)
        checks.append('tampered original Forge source rejected')
        extra = fixture / 'src/dev/infinity/forgeprobe/Extra.java'
        extra.write_text('class Extra {}')
        rejected(lambda: forge_fixture.verify_sources(consumer))
        extra.unlink()
        checks.append('extra unpinned Forge source rejected')
        rejected(lambda: forge_fixture.verify_inputs(consumer))
        checks.append('missing official fixture prerequisites rejected before spawn')
        (fixture / 'build').mkdir()
        calls = []
        rejected(lambda: forge_fixture.execute(consumer, lambda *args: calls.append(args), 1))
        assert not calls
        checks.append('existing fixture build prevents repeat compilation')
        data = forge_fixture.lock(consumer / forge_fixture.SUPPORT / 'input-lock.json')
        assert len(data['compileDependencyFiles']) == 12 and len(data['inputs']) == 29
        checks.append('exact29-input fixture closure includes12 native compile dependencies')
        text = (fixture / 'build.py').read_text()
        ast.parse(text)
        assert 'javac' in text and 'javap' in text
        checks.append('unchanged recovered source retains compiler and required ABI checks')
        tree = ast.parse(Path(build_candidate.__file__).read_text())
        execute = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
        text = ast.unparse(execute)
        assert text.index('forge_fixture.execute(root, command, deadline)') < text.index("command(root, recipe['coreCommand']")
        checks.append('bounded shared-deadline fixture build precedes core regression check')
    print(json.dumps({'status': 'PASS_ORIGINAL_FORGE_FIXTURE_PYTHON_SOURCE_CHECKS_ONLY', 'checks': len(checks),
                      'tests': checks, 'jvmStarted': False, 'downloadsStarted': False, 'gameLaunched': False}, indent=2))


if __name__ == '__main__':
    main()
