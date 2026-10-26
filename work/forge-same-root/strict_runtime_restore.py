"""Same immutable runtime locks, stricter serial transport/error semantics.

No baseline source or input lock is rewritten. HTTP denial, malformed transport,
wrong bytes, timeout and deadline stop immediately; only404/410 permits the next
URL already present in that individual immutable record.
"""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time

_spec = importlib.util.spec_from_file_location('strict_runtime_exact_transport',
                                              Path(__file__).with_name('restore_core_inputs.py'))
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)


@contextmanager
def bounded(deadline):
    """Own the main-thread alarm; never silently replace a caller's timer."""
    transport.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'Existing deadline timer')
    left = transport.remaining(deadline)
    def expired(_sig, _frame):
        raise TimeoutError('Strict runtime restoration deadline expired')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, left)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def canonical(root):
    root = Path(root).absolute()
    transport.require(root.is_dir() and root.resolve() == root and
                      not any(p.is_symlink() for p in [root, *root.parents]), 'Canonical existing root required')
    return root


def artifact(root, row, hosts, deadline):
    transport.remaining(deadline)
    target = transport.local(root, row['path'])
    transport.require(type(row['bytes']) is int and row['bytes'] > 0, 'Original bounded byte count required')
    if target.exists():
        return {'method': 'existing-exact', **transport.checked(target, row)}
    return transport.download(row, target, hosts, deadline)


def alias(root, source, name, row, deadline):
    transport.remaining(deadline)
    target = transport.local(root, name)
    if target.exists():
        return transport.checked(target, row)
    transport.checked(source, row)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.restore-', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as src:
            shutil.copyfileobj(src, out, 65536)
        transport.checked(temp, row)
        os.link(temp, target)
        return transport.checked(target, row)
    finally:
        temp.unlink(missing_ok=True)


def restore(api, runtime_module, deadline):
    """Verify unchanged preparation, restore originals, cache and final closure."""
    api = canonical(api)
    with bounded(deadline):
        runtime_module.verify_preparation(api)
        support = api / 'ci/runtime-restore'
        lock = json.loads((support / 'input-lock.json').read_text())
        transport.require(not lock['missingOfficialInputs'], 'Missing original official pins')
        records = []
        for index, row in enumerate(lock['artifacts'], 1):
            record = artifact(api, row, set(lock['allowedHosts']), deadline)
            record['aliases'] = [alias(api, transport.local(api, row['path']), name, row, deadline)
                                 for name in row.get('also_seed', [])]
            records.append(record)
            if index % 64 == 0 or index == len(lock['artifacts']):
                print('STRICT_OFFICIAL_RUNTIME_INPUTS_VERIFIED: '+str(index)+'/'+str(len(lock['artifacts'])), flush=True)
        runtime_module.verify_preparation(api)
        runtime_module.prepare_offline_installer_cache(api)
        result = runtime_module.verify_inputs(api)
        result['restoredArtifacts'] = len(records)
        result['transportPolicy'] = 'SERIAL_EXACT_PINS_DENIAL_STOP_ONLY_404_410_ALTERNATE'
        runtime_module.save(support / 'restore-result.json', result)
        return result


def restore_forge(consumer, records, deadline):
    """Same strict transport for original four Forge inputs, no retry wrapper."""
    consumer = canonical(consumer)
    with bounded(deadline):
        transport.require(len(records) == 4, 'Four original Forge records required')
        return [artifact(consumer, row, {'maven.minecraftforge.net'}, deadline) for row in records]
