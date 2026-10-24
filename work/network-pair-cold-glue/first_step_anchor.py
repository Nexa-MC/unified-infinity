#!/usr/bin/env python3
"""First-step LOCAL clock anchor for one absolute round; NOT job start.

No network or metadata API. The platform job began no later than this step;
first-step + job timeout + cancellation reserve must fit the round. Earlier
platform timeout can interrupt local work/cleanup. No remaining-job-time promise.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import time

REPOSITORY = 'Nexa-MC/unified-infinity'
BRANCH = 'diagnostic/network-pair-20261006-a'
ROUND_ID = 'recovery-20261024T030900Z'
START_UTC = '2026-10-24T03:09:00Z'
CUTOFF_UTC = '2026-10-24T03:54:00Z'
JOB_SECONDS = 36 * 60
CANCELLATION_SECONDS = 300
CLEANUP_SECONDS = 180
MIN_WORK_SECONDS = 1560
ANCHOR_NAME = 'unified-round-first-step-anchor.json'


def require(value, message):
    if not value:
        raise ValueError(message)


def utc(value):
    require(type(value) is str, 'UTC must be text')
    parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    require(parsed.strftime('%Y-%m-%dT%H:%M:%SZ') == value, 'Noncanonical UTC')
    return parsed.timestamp()


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Invalid clock')
    return value


def context():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == REPOSITORY and
            os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH and
            os.environ.get('GITHUB_EVENT_NAME') == 'push' and
            os.environ.get('GITHUB_JOB') == 'serial-pair' and
            os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Exact first-attempt diagnostic job required')
    run = os.environ.get('GITHUB_RUN_ID', '')
    sha = os.environ.get('GITHUB_SHA', '')
    runner = os.environ.get('RUNNER_NAME', '')
    require(re.fullmatch(r'[1-9][0-9]{0,19}', run) is not None and
            re.fullmatch(r'[0-9a-f]{40}', sha) is not None and
            1 <= len(runner) <= 128, 'Missing run, commit or runner identity')
    return {'runId': int(run), 'headSha': sha, 'runnerName': runner, 'attempt': 1}


def boot_id():
    value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None,
            'Missing host clock identity')
    return value


def anchor_path():
    path = Path(os.environ.get('RUNNER_TEMP', ''))
    require(path.is_absolute() and path.is_dir() and path.resolve() == path,
            'Canonical runner temporary directory required')
    return path / ANCHOR_NAME


def create_anchor():
    expected = context()
    wall, mono = number(time.time()), number(time.monotonic())
    require(utc(START_UTC) <= wall <= utc(CUTOFF_UTC)-JOB_SECONDS-CANCELLATION_SECONDS,
            'Stale or queue-delayed fixed round')
    anchor = dict(expected, schema=1, roundId=ROUND_ID, kind='FIRST_STEP_LOCAL_CLOCK',
                  capturedWall=wall, capturedMonotonic=mono, bootId=boot_id())
    raw = (json.dumps(anchor, sort_keys=True) + '\n').encode()
    fd = os.open(anchor_path(), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
    print(json.dumps({'status': 'FIXED_ROUND_LOCAL_CLOCK_BOUND', 'roundId': ROUND_ID,
                      'jobStartKnown': False, 'remainingJobTimeGuaranteed': False,
                      'jobSeconds': JOB_SECONDS, 'platformCancellationReserveSeconds': CANCELLATION_SECONDS}))
    return anchor


def read_anchor():
    expected = context()
    fd = os.open(anchor_path(), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600 and
                before.st_uid == os.getuid() and before.st_nlink == 1 and 0 < before.st_size <= 4096,
                'Untrusted local clock anchor file')
        raw = stream.read(4097)
        after = os.fstat(stream.fileno())
    signature = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                              info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    require(signature(before) == signature(after) and len(raw) == before.st_size, 'Local clock anchor changed during read')
    value = json.loads(raw)
    keys = {'schema', 'roundId', 'kind', 'capturedWall', 'capturedMonotonic',
            'bootId', 'runId', 'headSha', 'runnerName', 'attempt'}
    require(isinstance(value, dict) and set(value) == keys and type(value['schema']) is int and
            value['schema'] == 1 and value['roundId'] == ROUND_ID and
            value['kind'] == 'FIRST_STEP_LOCAL_CLOCK' and value['bootId'] == boot_id() and
            all(value[k] == v and type(value[k]) is type(v) for k, v in expected.items()),
            'Local clock anchor belongs to another job/host/round')
    captured, mono = number(value['capturedWall']), number(value['capturedMonotonic'])
    require(utc(START_UTC) <= captured <= utc(CUTOFF_UTC)-JOB_SECONDS-CANCELLATION_SECONDS,
            'First-step local anchor envelope invalid')
    require(number(time.time()) >= captured and number(time.monotonic()) >= mono,
            'Local clock anchor clock moved backwards')
    return value


if __name__ == '__main__':
    create_anchor()
