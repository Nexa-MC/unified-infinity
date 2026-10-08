"""Shared read-only checks for the recovered, isolated API1 server controls."""
import datetime
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AREA = Path(__file__).resolve().parent
PROBE = 'four-loader/forge-api-probe/build/unified-forge-api-probe-0.1.0.jar'
PROBE_SHA = '71985bf644262c6c411332f741e25d95b64d5f51800a27c697f4d928470b22c3'
REQUIRED_BYTES = (1280 + 512) * 1024 * 1024
STAGES = ['before_binding', 'after_binding', 'common_setup', 'queued_supplier', 'ready']
SAFETY_PROPERTIES = {'server-ip': '127.0.0.1', 'online-mode': 'true',
    'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
    'white-list': 'true', 'enforce-whitelist': 'true', 'enforce-secure-profile': 'true',
    'level-name': 'world', 'max-players': '1'}

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def local(relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Expected a project-relative path: ' + str(p))
    p = ROOT / p
    if p.is_symlink() or not p.resolve().is_relative_to(ROOT):
        raise ValueError('Redirected path: ' + str(p))
    return p

def checked(relative, digest):
    p = local(relative)
    if not p.is_file() or sha(p) != digest:
        raise ValueError('Missing or changed pinned input: ' + relative)
    return p

def save_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, local(relative))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

environment = load_module('api1_game_environment', 'four-loader/launch-support/game_environment.py')

def memory_gate():
    cg = Path('/sys/fs/cgroup')
    maximum = (cg / 'memory.max').read_text().strip()
    if maximum == 'max':
        raise ValueError('Actual bounded native cgroup is required')
    current = int((cg / 'memory.current').read_text())
    stats = dict(line.split() for line in (cg / 'memory.stat').read_text().splitlines())
    immediate = max(0, int(maximum) - current)
    inactive = max(0, int(stats.get('inactive_file', 0)) - int(stats.get('file_dirty', 0)) - int(stats.get('file_writeback', 0)))
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            name = (proc / 'comm').read_text().strip()
            status = (proc / 'stat').read_text()
            state = status[status.rfind(')') + 2:].split()[0]
            if name in ('java', 'javac') and state != 'Z':
                live.append({'pid': int(proc.name), 'name': name, 'state': state})
        except (OSError, ValueError, IndexError):
            continue
    return {'utc': utc(), 'cgroup': Path('/proc/self/cgroup').read_text(),
        'maximumBytes': int(maximum), 'currentBytes': current, 'immediateBytes': immediate,
        'cleanInactiveFileCreditBytes': inactive, 'eligibleBytes': immediate + inactive,
        'requiredBytes': REQUIRED_BYTES, 'liveJvms': live,
        'passed': immediate + inactive >= REQUIRED_BYTES and not live,
        'memoryEvents': (cg / 'memory.events').read_text()}

def tree(path):
    if not path.exists():
        return {}
    result = {}
    for p in sorted(path.rglob('*')):
        if p.is_symlink():
            raise ValueError('Redirected world/runtime file: ' + str(p))
        if p.is_file():
            result[str(p.relative_to(path))] = sha(p)
    return result

def properties(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line and not line.startswith(('#', '!')) and '=' in line)

def lan_disabled(config, loader):
    values = config.get('server', {}) if loader == 'native-forge' else config
    return values.get('advertiseDedicatedServerToLan') is False

def summarize(raw, port):
    lines = raw.decode(errors='replace').splitlines()
    stages = [m.group(1) for line in lines if
              (m := re.search(r'UNIFIED_FORGE_API_PROBE PASS stage=([a-z_]+)(?:\s|$)', line))]
    failures = [line for line in lines if any(s in line for s in (
        'UNIFIED_FORGE_API_PROBE FAIL', 'Failed to start the minecraft server',
        'Failed to load mods', 'ModLoadingException', 'MixinApplyError', 'Exception in thread'))]
    bindings = [line for line in lines if 'Starting Minecraft server on ' in line]
    return {'stages': stages, 'stagesExactAndOrdered': stages == STAGES,
        'stageCounts': {stage: stages.count(stage) for stage in STAGES},
        'failures': failures,
        'serverReady': any('Done (' in line and 'For help' in line for line in lines),
        'loopbackBinding': len(bindings) == 1 and f'Starting Minecraft server on 127.0.0.1:{port}' in bindings[0],
        'bindingLines': bindings,
        'saved': any('Saved the game' in line or 'Saved the world' in line for line in lines),
        'allDimensionsSaved': any('All dimensions are saved' in line for line in lines)}
