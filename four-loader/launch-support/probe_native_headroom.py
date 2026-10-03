#!/usr/bin/env python3
"""Read-only desktop cgroup gate probe; never starts or stops a game/process."""
import datetime
import json
from pathlib import Path
import sys

destination = Path(sys.argv[1])
root = Path('/sys/fs/cgroup')
resources = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'procSelfCgroup': Path('/proc/self/cgroup').read_text()}
for name in ('memory.max', 'memory.high', 'memory.current', 'memory.events',
             'memory.events.local', 'memory.stat'):
    path = root / name
    resources[name] = path.read_text() if path.is_file() else None
required = 2048 * 1024 * 1024
result = {'result': 'UNAVAILABLE', 'requiredBytes': required, 'resources': resources,
          'basis': '1536 MiB heap plus 512 MiB native; only clean inactive-file credit',
          'javaProcesses': [], 'largestResidentProcesses': []}
resident = []
for directory in Path('/proc').iterdir():
    if directory.name.isdigit():
        try:
            name = (directory / 'comm').read_text().strip()
            fields = dict(line.split(':', 1) for line in (directory / 'status').read_text().splitlines() if ':' in line)
            entry = {'pid': int(directory.name), 'name': name,
                     'state': fields.get('State', '').strip(),
                     'rssKiB': int(fields.get('VmRSS', '0 kB').split()[0])}
            resident.append(entry)
            if name in ('java', 'javac'):
                result['javaProcesses'].append(entry)
        except (OSError, ProcessLookupError):
            pass
result['largestResidentProcesses'] = sorted(resident, key=lambda item: item['rssKiB'], reverse=True)[:20]
if resources['memory.max'] not in (None, 'max\n') and resources['memory.current'] is not None:
    stats = {key: int(value) for key, value in
             (line.split() for line in resources['memory.stat'].splitlines())}
    immediate = max(0, int(resources['memory.max']) - int(resources['memory.current']))
    credit = max(0, stats.get('inactive_file', 0) - stats.get('file_dirty', 0)
                 - stats.get('file_writeback', 0))
    result.update(immediateHeadroomBytes=immediate, cleanInactiveFileCreditBytes=credit,
                  eligibleHeadroomBytes=immediate + credit,
                  result='PASS' if immediate + credit >= required else 'BLOCKED')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items() if key != 'resources'}, indent=2))
