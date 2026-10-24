#!/usr/bin/env python3
"""One reviewed UTC recovery round; no rolling deadline or process-wide kill.

The watchdog requests the driver's existing owned SIGTERM cleanup path. It never
changes signal handlers, kills process groups, or interrupts ordered cleanup.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
import first_step_anchor as anchor

ROUND_ID = anchor.ROUND_ID
START_UTC = anchor.START_UTC
CUTOFF_UTC = anchor.CUTOFF_UTC
CLEANUP_SECONDS = 180
MAX_WORK_SECONDS = 1980
MIN_WORK_SECONDS = 1560  # local absolute lease floor only, NOT remaining platform job time
EXPECTED = {'schema': 1, 'roundId': ROUND_ID, 'startUtc': START_UTC,
            'cutoffUtc': CUTOFF_UTC, 'cleanupReserveSeconds': CLEANUP_SECONDS,
            'maximumWorkSeconds': MAX_WORK_SECONDS, 'minimumWorkSeconds': MIN_WORK_SECONDS,
            'jobSeconds': anchor.JOB_SECONDS, 'anchorKind': 'FIRST_STEP_LOCAL_CLOCK', 'remainingJobTimeGuaranteed': False, 'platformCancellationReserveSeconds': anchor.CANCELLATION_SECONDS}


def require(value, message):
    if not value:
        raise ValueError(message)


def utc(value):
    require(type(value) is str, 'Round UTC timestamp must be text')
    try:
        result = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError('Malformed fixed round UTC timestamp') from error
    require(result.strftime('%Y-%m-%dT%H:%M:%SZ') == value, 'Round timestamp is not canonical UTC')
    return result.timestamp()


def clock_value(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Invalid round clock value')
    return value


def load():
    value = json.loads(Path(__file__).with_name('round-deadline.json').read_text())
    require(value == EXPECTED and all(type(value[k]) is type(v) for k, v in EXPECTED.items()),
            'Round metadata differs from this reviewed fixed round; never reset or reuse it')
    utc(value['startUtc']); utc(value['cutoffUtc'])
    return value


@dataclass(frozen=True)
class Window:
    deadline: float
    wall_stop: float
    admitted_wall: float
    admitted_monotonic: float
    work_seconds: int
    local_anchor: dict | None = None

    def remaining(self):
        now = clock_value(time.time())
        monotonic = clock_value(time.monotonic())
        require(monotonic >= self.admitted_monotonic, 'Round monotonic clock moved backwards')
        # A wall clock rollback cannot give back elapsed monotonic time.
        return min(self.deadline - monotonic, self.wall_stop - now)

    def owner_cutoff(self):
        return {'work_monotonic': self.deadline + 90, 'work_wall': self.wall_stop + 90,
                'cleanup_monotonic': self.deadline + CLEANUP_SECONDS,
                'cleanup_wall': self.wall_stop + CLEANUP_SECONDS}

    def receipt(self):
        return dict(EXPECTED, firstStepClockAnchor=self.local_anchor, jobStartKnown=False, remainingJobTimeGuaranteed=False, admittedUtc=datetime.fromtimestamp(self.admitted_wall, timezone.utc).isoformat(),
                    workSeconds=self.work_seconds, workDeadlineMonotonic=self.deadline,
                    workStopUtc=datetime.fromtimestamp(self.wall_stop, timezone.utc).isoformat())


def admit(round_id, work_seconds=MAX_WORK_SECONDS):
    load()
    require(round_id == ROUND_ID, 'Missing or stale recovery round identity')
    require(type(work_seconds) is int and 1 <= work_seconds <= MAX_WORK_SECONDS,
            'Round work allowance exceeds reviewed bound')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Round reruns are not authorized; freeze a new round')
    now, monotonic = clock_value(time.time()), clock_value(time.monotonic())
    require(now >= utc(START_UTC), 'Round clock precedes the fixed start')
    binding = anchor.read_anchor()
    # Anchor the local work allowance once, never at prepare/run entry. This
    # is not an estimate of actual job start or remaining platform job time.
    wall_stop = min(utc(CUTOFF_UTC) - anchor.CANCELLATION_SECONDS - CLEANUP_SECONDS,
                    binding['capturedWall'] + work_seconds)
    mono_stop = binding['capturedMonotonic'] + wall_stop - binding['capturedWall']
    allowance = min(work_seconds, math.floor(wall_stop - now), math.floor(mono_stop - monotonic))
    require(allowance >= MIN_WORK_SECONDS,
            'Round local lease expired or too short; no claim about remaining platform job time')
    return Window(monotonic + allowance, min(wall_stop, now + allowance), now, monotonic, allowance, binding)


class Watchdog:
    """One stop request; the driver retains sole ownership of process cleanup."""
    def __init__(self, window):
        self.window = window
        self.done = threading.Event()
        self.reason = None
        self.thread = threading.Thread(target=self._watch, name='fixed-round-deadline', daemon=True)

    def _watch(self):
        while not self.done.is_set():
            try:
                remaining = self.window.remaining()
            except (ValueError, OSError, OverflowError) as error:
                self.reason = str(error)
                remaining = 0
            if remaining <= 0:
                self.reason = self.reason or 'Fixed round work deadline reached; reserved cleanup begins'
                # Same-process signal, not a PID read from a receipt or proc scan.
                os.kill(os.getpid(), signal.SIGTERM)
                return
            self.done.wait(min(0.1, remaining))

    def start(self):
        require(self.window.remaining() > 0, 'Round expired before watchdog start')
        self.thread.start()

    def close(self):
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=1)
        require(not self.thread.is_alive(), 'Round watchdog failed bounded shutdown')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round-id', required=True)
    args = parser.parse_args()
    print(json.dumps(admit(args.round_id).receipt(), sort_keys=True), flush=True)
