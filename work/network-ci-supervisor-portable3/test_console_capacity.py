"""Exact observed log replay and finite console-envelope refusal regressions.

No Java, game, external dependency, network, or CI is executed. The real pipe
fixture exercises kernel read fragmentation without starting any subprocess.
"""
import ast
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervisor as s
from console_capacity_preservation import (
    CAPACITY_BLOCK, ORIGINAL_CAPACITY, PREDECESSOR_SUPERVISOR_SHA256,
    without_console_capacity,
)

HERE = Path(__file__).resolve().parent
FIXTURES = {
    'native': (12715, '9a0f2261e8183fcfb11c93b92feb79f08b29a621b8e4122400db866234aa189e'),
    'unified': (20073, '62116773a147a06ab44cb4e7f9de3cd2cd3db997372d319d75b7875a6f0ac44c'),
}


def fixture(name='unified'):
    raw = (HERE / 'fixtures' / ('jna-' + name + '-classpath.log')).read_bytes()
    size, expected = FIXTURES[name]
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Changed observed JNA diagnostic fixture')
    return raw


@contextmanager
def captured():
    with tempfile.TemporaryDirectory() as root:
        capture = s.Capture(Path(root) / 'console.log')
        try:
            yield capture, Path(root) / 'console.log'
        finally:
            capture.close()


class ConsoleCapacity(unittest.TestCase):
    def test_only_line_capacity_changes_resource_constants(self):
        self.assertEqual((s.MAX_LINE, s.MAX_LOG, s.MAX_JSON), (32768, 2097152, 2048))
        self.assertLess(s.MAX_LINE, s.MAX_LOG)

    def test_observed_both_95_entry_diagnostics_are_hash_pinned(self):
        for name, expected_line_bytes in (('native', 12714), ('unified', 20072)):
            with self.subTest(name=name):
                raw = fixture(name)
                self.assertEqual(raw.count(b'\n'), 1)
                self.assertEqual(len(raw[:-1]), expected_line_bytes)
                self.assertTrue(raw.startswith(b'\tSuppressed: java.io.IOException: Native library (linux-x86-64/libflite.so)'))
                classpath = raw.split(b' resource path (', 1)[1][:-2]
                self.assertEqual(len(classpath.split(b':')), 95)
                self.assertEqual(len(classpath), 12609 if name == 'native' else 19967)

    def test_old_16k_bound_reproduces_only_unified_capture_failure(self):
        with patch.object(s, 'MAX_LINE', 16384):
            with captured() as (capture, _):
                capture.feed(fixture('native'))
                capture.finish()
                self.assertEqual(len(capture.lines), 1)
            for chunks in ((fixture(),), (fixture()[:16385], fixture()[16385:])):
                with self.subTest(parts=len(chunks)), captured() as (capture, _):
                    with self.assertRaisesRegex(ValueError, 'line bound exceeded'):
                        for data in chunks:
                            capture.feed(data)

    def test_actual_diagnostic_retains_every_byte_under_read_fragmentation(self):
        raw = fixture()
        event = b'NETWORK_CONTROL_READY {"schema":1,"role":"server"}\n'
        for size in (1, 31, 4096, 16384, 65536):
            with self.subTest(chunk_bytes=size), captured() as (capture, path):
                for start in range(0, len(raw), size):
                    capture.feed(raw[start:start + size])
                capture.feed(event)
                capture.finish()
                self.assertEqual(bytes(capture.raw), raw + event)
                self.assertEqual(path.read_bytes(), raw + event)
                self.assertEqual(capture.lines, [raw[:-1].decode(), event[:-1].decode()])
                self.assertEqual(len(capture.line_observed_monotonic), 2)
                self.assertEqual(capture.events, {'NETWORK_CONTROL_READY': {'schema': 1, 'role': 'server'}})

    def test_real_pipe_preserves_split_observed_line_and_later_event(self):
        raw = fixture()
        readfd, writefd = os.pipe()
        try:
            with captured() as (capture, path):
                reads = 0
                for start in range(0, len(raw) - 1, 4093):
                    part = raw[:-1][start:start + 4093]
                    self.assertEqual(os.write(writefd, part), len(part))
                    data = os.read(readfd, 65536)
                    reads += 1
                    capture.feed(data)
                    self.assertEqual(capture.lines, [])
                    self.assertEqual(capture.events, {})
                event = b'NETWORK_CONTROL_READY {"schema":1,"role":"server"}\n'
                self.assertEqual(os.write(writefd, b'\n' + event), len(event) + 1)
                capture.feed(os.read(readfd, 65536))
                os.close(writefd)
                writefd = None
                self.assertEqual(os.read(readfd, 65536), b'')
                capture.finish()
                self.assertGreater(reads, 1)
                self.assertEqual(path.read_bytes(), raw + event)
                self.assertEqual(capture.lines[0], raw[:-1].decode())
                self.assertIn('NETWORK_CONTROL_READY', capture.events)
        finally:
            os.close(readfd)
            if writefd is not None:
                os.close(writefd)

    def test_exact_line_boundary_terminated_and_split_newline(self):
        raw = b'x' * s.MAX_LINE
        for chunks in ((raw + b'\n',), (raw, b'\n'), (raw[:16384], raw[16384:], b'\n')):
            with self.subTest(parts=len(chunks)), captured() as (capture, path):
                for data in chunks:
                    capture.feed(data)
                capture.finish()
                self.assertEqual(path.read_bytes(), raw + b'\n')
                self.assertEqual(capture.lines, [raw.decode()])

    def test_plus_one_rejected_complete_or_split_with_or_without_newline(self):
        raw = b'x' * (s.MAX_LINE + 1)
        for suffix in (b'', b'\n'):
            for chunks in ((raw + suffix,), (raw[:s.MAX_LINE], raw[s.MAX_LINE:] + suffix)):
                with self.subTest(newline=bool(suffix), parts=len(chunks)), captured() as (capture, _):
                    with self.assertRaisesRegex(ValueError, 'line bound exceeded'):
                        for data in chunks:
                            capture.feed(data)
                    self.assertEqual(capture.events, {})

    def test_crlf_counts_carriage_return_inside_exact_byte_limit(self):
        with captured() as (capture, _):
            capture.feed(b'x' * (s.MAX_LINE - 1) + b'\r')
            capture.feed(b'\n')
            capture.finish()
            self.assertEqual(capture.lines, ['x' * (s.MAX_LINE - 1)])
        with captured() as (capture, _):
            with self.assertRaisesRegex(ValueError, 'line bound exceeded'):
                capture.feed(b'x' * s.MAX_LINE + b'\r\n')

    def test_utf8_limit_is_bytes_and_split_codepoint_is_not_truncated(self):
        raw = ('é' * (s.MAX_LINE // 2)).encode()
        with captured() as (capture, path):
            capture.feed(raw[:1])
            capture.feed(raw[1:] + b'\n')
            capture.finish()
            self.assertEqual(path.read_bytes(), raw + b'\n')
            self.assertEqual(capture.lines, [raw.decode()])
        with captured() as (capture, _):
            with self.assertRaisesRegex(ValueError, 'line bound exceeded'):
                capture.feed(raw + b'x\n')

    def test_invalid_utf8_beyond_old_boundary_remains_rejected(self):
        with captured() as (capture, _):
            capture.feed(b'x' * 17000)
            with self.assertRaises(UnicodeDecodeError):
                capture.feed(b'\xff\n')

    def test_eof_rejects_nonempty_unterminated_line_at_exact_capacity(self):
        for raw in (b'x', fixture()[:-1], b'x' * s.MAX_LINE):
            with self.subTest(bytes=len(raw)), captured() as (capture, _):
                capture.feed(raw)
                with self.assertRaisesRegex(ValueError, 'Truncated console line'):
                    capture.finish()
                self.assertEqual(capture.events, {})

    def test_complete_lines_plus_nonempty_eof_suffix_are_not_accepted(self):
        with captured() as (capture, _):
            capture.feed(fixture() + b'unfinished')
            self.assertEqual(len(capture.lines), 1)
            with self.assertRaisesRegex(ValueError, 'Truncated console line'):
                capture.finish()

    def test_total_process_log_exact_limit_then_plus_one_refused_before_write(self):
        raw = (b'x' * 1023 + b'\n') * 2048
        self.assertEqual(len(raw), s.MAX_LOG)
        with captured() as (capture, path):
            for start in range(0, len(raw), 65536):
                capture.feed(raw[start:start + 65536])
            capture.finish()
            self.assertEqual(len(capture.lines), 2048)
            self.assertEqual(path.read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, 'Console byte bound exceeded'):
                capture.feed(b'\n')
            self.assertEqual(bytes(capture.raw), raw)
            self.assertEqual(path.read_bytes(), raw)

    def test_huge_single_feed_is_refused_before_any_log_write(self):
        with captured() as (capture, path):
            with self.assertRaisesRegex(ValueError, 'Console byte bound exceeded'):
                capture.feed(b'x' * (s.MAX_LOG + 1))
            self.assertEqual(path.read_bytes(), b'')
            self.assertEqual(capture.raw, b'')

    def test_all_fatal_markers_beyond_16k_and_split_across_reads_still_fail(self):
        for marker in s.FAIL_MARKERS:
            raw = b'x' * 17000 + marker.encode() + b'\n'
            split = 17000 + len(marker) // 2
            for chunks in ((raw,), (raw[:split], raw[split:])):
                with self.subTest(marker=marker, parts=len(chunks)), captured() as (capture, _):
                    with self.assertRaisesRegex(ValueError, 'Game/probe failure marker'):
                        for data in chunks:
                            capture.feed(data)
                    self.assertEqual(capture.events, {})

    def test_prefixed_probe_markers_beyond_16k_and_across_reads_still_fail(self):
        for marker in ('NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_READY', 'NETWORK_CONTROL_DISCONNECTED'):
            raw = b'x' * 17000 + marker.encode() + b' {}\n'
            split = 17000 + len(marker) // 2
            with self.subTest(marker=marker), captured() as (capture, _):
                capture.feed(raw[:split])
                with self.assertRaisesRegex(ValueError, 'exact stdout prefix'):
                    capture.feed(raw[split:])
                self.assertEqual(capture.events, {})

    def test_protocol_json_bound_is_still_2048_not_the_console_bound(self):
        for marker in ('NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_READY', 'NETWORK_CONTROL_DISCONNECTED'):
            with self.subTest(marker=marker), captured() as (capture, _):
                payload = b'{}' + b' ' * (s.MAX_JSON - 2)
                capture.feed(marker.encode() + b' ' + payload + b'\n')
                self.assertEqual(capture.events, {marker: {}})
            for size in (s.MAX_JSON + 1, 20000):
                with self.subTest(marker=marker, size=size), captured() as (capture, _):
                    payload = b'{}' + b' ' * (size - 2)
                    with self.assertRaisesRegex(ValueError, 'JSON byte bound exceeded'):
                        capture.feed(marker.encode() + b' ' + payload + b'\n')
                    self.assertEqual(capture.events, {})

    def test_malformed_nonfinite_duplicate_fail_and_nonobject_events_rejected(self):
        for payload in (b'{', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1,"x":2}',
                        b'{"status":"FAIL"}', b'[]', b'null'):
            with self.subTest(payload=payload), captured() as (capture, _):
                capture.feed(fixture())
                with self.assertRaises(ValueError):
                    capture.feed(b'NETWORK_CONTROL_JSON ' + payload + b'\n')
                self.assertEqual(capture.events, {})

    def test_duplicate_event_after_long_diagnostic_still_rejected(self):
        event = b'NETWORK_CONTROL_JSON {"status":"PASS"}\n'
        with captured() as (capture, _):
            capture.feed(event + fixture())
            with self.assertRaisesRegex(ValueError, 'Duplicate probe event'):
                capture.feed(event)

    def test_fatal_line_never_allows_following_event_in_same_read(self):
        raw = b'x' * 17000 + b'OutOfMemoryError\nNETWORK_CONTROL_JSON {"status":"PASS"}\n'
        with captured() as (capture, _):
            with self.assertRaisesRegex(ValueError, 'Game/probe failure marker'):
                capture.feed(raw)
            self.assertEqual(capture.events, {})


class ExactPredecessorPreservation(unittest.TestCase):
    def source(self):
        return Path(s.__file__).read_text()

    def test_only_exact_capacity_comment_and_constant_differs(self):
        normalized = without_console_capacity(self.source())
        self.assertEqual(hashlib.sha256(normalized.encode()).hexdigest(), PREDECESSOR_SUPERVISOR_SHA256)

    def test_capture_class_is_byte_identical_to_0409(self):
        source = self.source()
        node = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.ClassDef) and node.name == 'Capture')
        block = ''.join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
        self.assertEqual(hashlib.sha256(block.encode()).hexdigest(),
                         'a25dff0382ef4c0f9d0d5147562160b589c4306a919da51169a62aeb3e28f1f0')

    def test_missing_duplicate_or_changed_capacity_block_cannot_normalize(self):
        source = self.source()
        cases = (source.replace(CAPACITY_BLOCK, ORIGINAL_CAPACITY),
                 source + '\n' + CAPACITY_BLOCK,
                 source.replace('MAX_LINE = 32 * 1024', 'MAX_LINE = 64 * 1024'),
                 source.replace('20,072-byte', '20,073-byte'),
                 source + '\nMAX_LINE = 1\n')
        for changed in cases:
            with self.subTest(tail=changed[-40:]), self.assertRaises(ValueError):
                without_console_capacity(changed)

    def test_other_bounds_parsers_and_acceptance_changes_remain_detectable(self):
        source = self.source()
        for needle in ('MAX_LOG = 2 * MIB', 'MAX_JSON = 2048',
                       'os.read(key.fileobj.fileno(), 65536)',
                       "line.decode('utf-8', 'strict')", "'Game/probe failure marker'",
                       "'Probe marker must be exact stdout prefix'", "'Duplicate probe event'",
                       "'Truncated console line'", "'Both owned clean exits required'",
                       "'Completed EMI reload and two-second dwell required'"):
            with self.subTest(needle=needle):
                self.assertEqual(source.count(needle), 1)
                normalized = without_console_capacity(source.replace(needle, 'UNREVIEWED_CHANGE', 1))
                self.assertNotEqual(hashlib.sha256(normalized.encode()).hexdigest(), PREDECESSOR_SUPERVISOR_SHA256)


if __name__ == '__main__':
    unittest.main(verbosity=2)
