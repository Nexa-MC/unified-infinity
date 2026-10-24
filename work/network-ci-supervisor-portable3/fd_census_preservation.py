"""Test-only exact reverse normalization of bounded FD-census restart."""

REVIEWED_BLOCK = "def cpu_probe_fds(proc, expected, deadline):\n    # A live helper may close an enumerated descriptor before readlink. Restart\n    # the whole census, never skip an unobserved entry or renew its deadline.\n    for attempt in range(3):\n        proc.same(expected)\n        require(time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')\n        changed = False\n        with os.scandir(proc.root / str(expected['pid']) / 'fd') as entries:\n            for count, descriptor in enumerate(entries, 1):\n                require(count <= 64 and time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')\n                try:\n                    target = os.readlink(descriptor.path)\n                except FileNotFoundError as exc:\n                    if exc.errno != 2:\n                        raise\n                    proc.same(expected)\n                    changed = True\n                    break\n                require(re.fullmatch(r'socket:\\[\\d+\\]', target) is None,\n                        'CPU probe socket descriptor forbidden')\n        proc.same(expected)\n        require(time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')\n        if not changed:\n            return\n    raise ValueError('CPU probe descriptor census remained unstable')\n"
ORIGINAL_BLOCK = "def cpu_probe_fds(proc, expected, deadline):\n    proc.same(expected)\n    with os.scandir(proc.root / str(expected['pid']) / 'fd') as entries:\n        for count, descriptor in enumerate(entries, 1):\n            require(count <= 64 and time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')\n            require(re.fullmatch(r'socket:\\[\\d+\\]', os.readlink(descriptor.path)) is None,\n                    'CPU probe socket descriptor forbidden')\n    proc.same(expected)\n"
from helper_retirement_preservation import without_helper_retirement

PREDECESSOR_SHA256 = '400f9f2eb2b21d11b4fbbaa3617244435daf351868d651b6c889d836bafdda00'

def without_fd_census_restart(source):
    source = without_helper_retirement(source)
    if source.count(REVIEWED_BLOCK) != 1:
        raise ValueError("Changed or duplicate FD census restart")
    return source.replace(REVIEWED_BLOCK, ORIGINAL_BLOCK, 1)
