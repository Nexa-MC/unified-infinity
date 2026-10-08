"""Synthetic fixtures only. No JVM, Xvfb, socket, subprocess, or game is launched."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import supervisor as s

_forbid_launch = patch('supervisor.subprocess.Popen', side_effect=AssertionError('Synthetic tests must never launch a subprocess'))
_forbid_signal = patch('supervisor.os.killpg', side_effect=AssertionError('Synthetic tests must never signal a real process'))


def setUpModule():
    _forbid_launch.start()
    _forbid_signal.start()


def tearDownModule():
    _forbid_signal.stop()
    _forbid_launch.stop()


def table(local='0100007F:641F', remote='00000000:0000', inode='42', state='0A'):
    return 'header\n0: ' + local + ' ' + remote + ' ' + state + ' 0:0 0:0 0 0 0 ' + inode + '\n'


def tables(**values):
    return dict(dict.fromkeys(s.TABLES, 'header\n'), **values)


def stat_text(pid, start, group=None, state='S'):
    fields = [state, '1', str(group or pid), str(group or pid)] + ['0'] * 15
    fields += [str(start), '0', '100']
    return str(pid) + ' (synthetic process) ' + ' '.join(fields)


def pass_row(role, pid, start, nonce=17, port=25631):
    return {'schema': 1, 'role': role, 'status': 'PASS', 'nonce': nonce, 'sequence': 1,
            'counter_before': 0, 'counter_after': 1, 'player_uuid': s.IDENTITY,
            'player_name': s.NAME, 'port': port, 'pid': pid, 'start_ticks': start,
            'main_thread': True, 'loopback': True, 'memory_connection': False,
            'dedicated_server': role == 'server', 'remote_join': role == 'client',
            'phase': 'PLAY', 'flow': 'SERVERBOUND' if role == 'server' else 'CLIENTBOUND', 'code': 'ok'}


class SyntheticProc(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'net').mkdir()
        self.proc = s.Proc(self.root)
        self.server = self.make_process(101, 1000, ['42', '43'])
        self.client = self.make_process(202, 2000, ['44'])
        self.set_tables(tables(tcp=table() + table(local='0100007F:641F', remote='0100007F:C001', inode='43', state='01').split('\n', 1)[1] +
                              table(local='0100007F:C001', remote='0100007F:641F', inode='44', state='01').split('\n', 1)[1]))

    def tearDown(self):
        self.temp.cleanup()

    def make_process(self, pid, start, inodes):
        path = self.root / str(pid)
        (path / 'fd').mkdir(parents=True)
        (path / 'stat').write_text(stat_text(pid, start))
        (path / 'comm').write_text('java\n')
        (path / 'cmdline').write_bytes(b'/synthetic/java\0-Xmx1280m\0')
        for index, inode in enumerate(inodes):
            (path / 'fd' / str(index)).symlink_to('socket:[' + inode + ']')
        return self.proc.identity(pid)

    def set_tables(self, values):
        for name, text in values.items():
            (self.root / 'net' / name).write_text(text)

    def test_actual_fixture_identity_and_socket_pair(self):
        self.assertEqual(self.server['start_ticks'], 1000)
        self.assertEqual(self.server['pgrp'], 101)
        self.assertEqual(self.proc.inodes(self.server), {'42', '43'})
        self.assertTrue(self.proc.sockets(self.server, 25631, self.client)['connected'])

    def test_pid_reuse_rejected(self):
        (self.root / '101/stat').write_text(stat_text(101, 9999))
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.proc.sockets(self.server, 25631)

    def test_group_identity_change_rejected(self):
        (self.root / '101/stat').write_text(stat_text(101, 1000, group=999))
        with self.assertRaises(ValueError):
            self.proc.same(self.server)

    def test_live_socket_not_just_matching_log(self):
        self.set_tables(tables(tcp=table()))
        with self.assertRaisesRegex(ValueError, 'established loopback peer'):
            self.proc.sockets(self.server, 25631, self.client)

    def test_unowned_listener_rejected(self):
        self.set_tables(tables(tcp=table(inode='99')))
        with self.assertRaises(ValueError):
            self.proc.sockets(self.server, 25631)

    def test_client_listener_cannot_impersonate_server(self):
        self.set_tables(tables(tcp=table(inode='44')))
        with self.assertRaisesRegex(ValueError, 'not owned by server'):
            self.proc.sockets(self.server, 25631, self.client)

    def test_missing_table_rejected(self):
        (self.root / 'net/udp6').unlink()
        with self.assertRaises(FileNotFoundError):
            self.proc.sockets(self.server, 25631)

    def test_additional_ipv6_and_udp_binding_rejected(self):
        for protocol, row in [('tcp', table(local='00000000:641F')),
                              ('tcp6', table(local='0'*32 + ':641F')),
                              ('udp', table(local='0100007F:6543', inode='44', state='07')),
                              ('udp6', table(local='0'*32 + ':6543', inode='44', state='07'))]:
            with self.subTest(protocol=protocol):
                self.set_tables(tables(tcp=table(), **({protocol: row} if protocol != 'tcp' else {})))
                if protocol == 'tcp':
                    self.set_tables(tables(tcp=row))
                with self.assertRaises(ValueError):
                    self.proc.sockets(self.server, 25631, self.client)

    def test_connection_must_be_complementary(self):
        value = (self.root / 'net/tcp').read_text().replace('0100007F:C001 0100007F:641F', '0100007F:C002 0100007F:641F')
        (self.root / 'net/tcp').write_text(value)
        with self.assertRaisesRegex(ValueError, 'client-owned established'):
            self.proc.sockets(self.server, 25631, self.client)

    def test_cleanup_refuses_recycled_pid(self):
        pair = s.Pair({'target': 'native-neoforge'}, self.root, self.proc)
        pair.identities = {'server': self.server}
        pair.group_members = {'server': [self.server]}
        (self.root / '101/stat').write_text(stat_text(101, 9999))
        with patch('supervisor.os.killpg') as kill:
            pair.cleanup()
            kill.assert_not_called()
        pair.selector.close()

    def test_cleanup_targets_only_its_recorded_group(self):
        pair = s.Pair({'target': 'native-neoforge'}, self.root, self.proc)
        pair.identities = {'server': self.server}
        pair.group_members = {'server': [self.server]}
        with patch('supervisor.os.killpg') as kill:
            pair.cleanup()
            self.assertTrue(kill.called)
            self.assertEqual({call.args[0] for call in kill.call_args_list}, {101})
        pair.selector.close()

    def test_cleanup_can_find_owned_descendant_after_leader_exit(self):
        self.make_process(303, 3000, [])
        text = stat_text(303, 3000, group=101).replace(') S 1 ', ') S 101 ')
        (self.root / '303/stat').write_text(text)
        (self.root / '101/stat').write_text(stat_text(101, 1000, state='Z'))
        pair = s.Pair({'target': 'native-neoforge'}, self.root, self.proc)
        pair.identities = {'server': self.server}
        pair.group_members = {'server': [self.server]}
        with patch('supervisor.os.killpg') as kill:
            pair.cleanup()
            self.assertEqual({call.args[0] for call in kill.call_args_list}, {101})
        self.assertTrue(pair.report['cleanup_incomplete'])  # Mock signals do not remove fixture processes.
        pair.selector.close()

    def test_unreaped_direct_child_cleanup_when_proc_identity_failed(self):
        pair = s.Pair({'target': 'native-neoforge'}, self.root, self.proc)
        pair.children = {'server': SimpleNamespace(pid=777, poll=lambda: None)}
        with patch('supervisor.os.killpg') as kill, patch('supervisor.time.monotonic', side_effect=range(0, 200, 10)):
            pair.cleanup()
            self.assertEqual({call.args[0] for call in kill.call_args_list}, {777})
        self.assertTrue(pair.report['cleanup_incomplete'])
        pair.selector.close()

    def test_actual_fixture_xvfb_executable_and_socket_owner(self):
        executable = self.root / 'graphics/Xvfb'
        executable.parent.mkdir()
        executable.write_bytes(b'SYNTHETIC ONLY')
        identity = self.make_process(404, 4000, ['77'])
        (self.root / '404/exe').symlink_to(executable)
        (self.root / '404/cmdline').write_bytes(str(executable).encode() + b'\0:77\0-nolisten\0tcp\0')
        (self.root / 'net/unix').write_text('header\n0: 00000002 00000000 00010000 0001 01 77 /tmp/.X11-unix/X77\n')
        receipt = self.root / 'graphics/preflight.json'
        receipt.write_text(json.dumps({'schema': 1, 'display': ':77', 'xvfb_pid': 404, 'xvfb_start_ticks': 4000,
                          'renderer': 'llvmpipe (synthetic fixture)', 'direct_rendering': True, 'glx_capable': True,
                          'gl_probe_peak_rss_bytes': 1024, 'measured_headroom_bytes': 256*s.MIB,
                          'input_sha256': {str(executable): s.digest(executable)}}))
        spec = {'graphics': {'display': ':77', 'pid': 404, 'start_ticks': 4000, 'executable': str(executable),
                            'preflight': str(receipt), 'reserve_bytes': 256*s.MIB},
                'inputs': [{'path': str(path), 'sha256': s.digest(path)} for path in (executable, receipt)]}
        self.assertEqual(s.verify_graphics(spec, self.proc)['identity'], identity)
        (self.root / 'net/unix').write_text('header\n0: 00000002 00000000 00010000 0001 01 99 /tmp/.X11-unix/X77\n')
        with self.assertRaisesRegex(ValueError, 'not owned'):
            s.verify_graphics(spec, self.proc)


class ProtocolTests(unittest.TestCase):
    def test_strict_positive_nonce_process_and_counter(self):
        identity = {'pid': 101, 'start_ticks': 1000}
        valid = pass_row('server', 101, 1000)
        s.validate_probe(valid, 'server', identity, 17, 25631)
        for key, value in [('nonce', 18), ('sequence', 2), ('counter_before', 1), ('counter_after', 0),
                           ('pid', 102), ('start_ticks', 999), ('port', 25632), ('player_uuid', 'other'),
                           ('main_thread', False), ('main_thread', 1), ('memory_connection', True),
                           ('dedicated_server', False), ('remote_join', True), ('schema', True),
                           ('phase', 'CONFIGURATION'), ('flow', 'CLIENTBOUND')]:
            altered = dict(valid, **{key: value})
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    s.validate_probe(altered, 'server', identity, 17, 25631)
        for nonce in (0, -1, 2**63, True):
            with self.assertRaises(ValueError):
                s.validate_probe(pass_row('server', 101, 1000, nonce), 'server', identity, nonce, 25631)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"x":NaN}', b' ' * (s.MAX_JSON + 1)):
            with self.assertRaises(ValueError):
                s.decode_json(raw)

    def test_capture_strict_once_bounded_and_sticky_failure(self):
        with tempfile.TemporaryDirectory() as root:
            capture = s.Capture(Path(root) / 'log')
            payload = ('NETWORK_CONTROL_JSON ' + json.dumps(pass_row('client', 202, 2000)) + '\n').encode()
            capture.feed(payload[:19])
            capture.feed(payload[19:])
            self.assertEqual(capture.events['NETWORK_CONTROL_JSON']['nonce'], 17)
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                capture.feed(payload)
            capture.close()

    def test_fail_result_and_prefixed_marker_rejected(self):
        for line in (b'NETWORK_CONTROL_JSON {"status":"FAIL"}\n', b'fake NETWORK_CONTROL_JSON {}\n'):
            with tempfile.TemporaryDirectory() as root:
                capture = s.Capture(Path(root) / 'log')
                with self.assertRaises(ValueError):
                    capture.feed(line)
                capture.close()

    def test_capture_byte_and_unterminated_line_bounds(self):
        with tempfile.TemporaryDirectory() as root:
            capture = s.Capture(Path(root) / 'log')
            with self.assertRaisesRegex(ValueError, 'byte bound'):
                capture.feed(b'x' * (s.MAX_LOG + 1))
            self.assertEqual((Path(root) / 'log').stat().st_size, 0)
            with self.assertRaisesRegex(ValueError, 'line bound'):
                capture.feed(b'x' * (s.MAX_LINE + 1))
            capture.close()

    def test_canonical_probe_input_order_and_exclusive_write(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'input'
            row = {'schema': 1, 'nonce': 17, 'sequence': 1, 'port': 25631}
            s.write_new(path, row)
            self.assertEqual(path.read_bytes(), b'{"schema":1,"nonce":17,"sequence":1,"port":25631}\n')
            with self.assertRaises(FileExistsError):
                s.write_new(path, row)

    def test_release_is_atomic_complete_and_cannot_replace(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'network-control-release.json'
            row = {'schema': 1, 'nonce': 17, 'sequence': 1}
            s.publish_release(path, row)
            self.assertEqual(path.read_bytes(), b'{"schema":1,"nonce":17,"sequence":1}\n')
            self.assertFalse(path.with_name(path.name + '.supervisor-tmp').exists())
            with self.assertRaises(FileExistsError):
                s.publish_release(path, dict(row, nonce=18))
            self.assertEqual(s.decode_json(path.read_bytes()), row)


class SealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_readonly_hash_size_and_symlink_enforcement(self):
        path = self.root / 'input'
        path.write_bytes(b'synthetic only')
        pin = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': s.digest(path)}
        with self.assertRaisesRegex(ValueError, 'read-only'):
            s.file_pin(pin)
        path.chmod(0o444)
        self.assertEqual(s.file_pin(pin), path)
        with self.assertRaises(ValueError):
            s.file_pin(dict(pin, sha256='0'*64))
        redirect = self.root / 'redirect'
        redirect.symlink_to(path)
        with self.assertRaises(ValueError):
            s.file_pin(dict(pin, path=str(redirect)))

    def test_closed_environment_ignores_ambient_secrets(self):
        profile = self.root / 'client'
        command = [str(self.root / 'jdk/bin/java')]
        env = {k: str(profile / v) for k, v in s.PRIVATE.items()}
        env.update(JAVA_HOME=str(self.root / 'jdk'), PATH=str(self.root / 'jdk') + '/bin:/usr/bin:/bin',
                   LANG='C.UTF-8', TZ='UTC', DISPLAY=':77', LIBGL_ALWAYS_SOFTWARE='true', GALLIUM_DRIVER='llvmpipe')
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'synthetic-test-only', 'JAVA_TOOL_OPTIONS': '-x', 'HTTPS_PROXY': 'synthetic'}):
            self.assertEqual(s.verify_environment(env, profile, command, ':77'), env)
        for key in ('GITHUB_TOKEN', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'HTTPS_PROXY', 'LD_PRELOAD', 'MESA_GL_VERSION_OVERRIDE'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    s.verify_environment(dict(env, **{key: 'synthetic'}), profile, command, ':77')

    def test_current_listener_validator_semantics_are_unchanged(self):
        source = Path(__file__).resolve().parents[1] / 'api1/four-loader/api-contract-controls/prepare_network_profiles.py'
        self.assertEqual(s.digest(source), s.PREPARATION_SHA256)
        upstream = ast.parse(source.read_text())
        ours = ast.parse(Path(s.__file__).read_text())
        def body(tree):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_listeners')
            node.body = node.body[1:]  # Ignore documentation; all executable AST must match.
            return ast.dump(node, include_attributes=False)
        self.assertEqual(body(upstream), body(ours))

    def test_memory_gate_is_aggregate_and_graphics_additive(self):
        procroot = self.root / 'proc'
        cg = self.root / 'cgroup'
        (procroot / 'self').mkdir(parents=True)
        cg.mkdir()
        (procroot / 'self/cgroup').write_text('0::/\n')
        (procroot / 'self/mountinfo').write_text('1 2 0:1 / ' + str(cg) + ' rw - cgroup2 cgroup rw\n')
        (procroot / 'meminfo').write_text('MemAvailable: 8388608 kB\n')
        (cg / 'memory.max').write_text(str(s.PAIR_BYTES + 256*s.MIB))
        (cg / 'memory.current').write_text('0')
        (cg / 'memory.stat').write_text('inactive_file 0\nfile_dirty 0\nfile_writeback 0\n')
        (cg / 'memory.events').write_text('oom 0\noom_kill 0\n')
        proc = s.Proc(procroot)
        result = s.memory_gate(proc, {'reserve_bytes': 256*s.MIB})
        self.assertEqual(result['pair_bytes'], 3758096384)
        self.assertEqual(result['required_bytes'], s.PAIR_BYTES + 256*s.MIB)
        (cg / 'memory.max').write_text(str(s.PAIR_BYTES))
        with self.assertRaisesRegex(ValueError, 'Aggregate memory'):
            s.memory_gate(proc, {'reserve_bytes': 256*s.MIB})

    def test_runtime_fifo_and_symlink_never_block(self):
        fifo = self.root / 'synthetic-fifo'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular evidence'):
            s.read_bounded(fifo, 10)
        link = self.root / 'link'
        link.symlink_to(fifo)
        with self.assertRaises(OSError):
            s.read_bounded(link, 10)

    def test_ancestor_limit_and_real_root_without_memory_max(self):
        procroot, mount = self.root / 'proc', self.root / 'cgroup'
        cg = mount / 'parent' / 'leaf'
        (procroot / 'self').mkdir(parents=True)
        cg.mkdir(parents=True)
        (procroot / 'self/cgroup').write_text('0::/parent/leaf\n')
        (procroot / 'self/mountinfo').write_text('1 2 0:1 / ' + str(mount) + ' rw - cgroup2 cgroup rw\n')
        (procroot / 'meminfo').write_text('MemAvailable: 8388608 kB\n')
        for directory, maximum in ((cg, 8*1024*s.MIB), (cg.parent, 3*1024*s.MIB)):
            (directory / 'memory.max').write_text(str(maximum))
            (directory / 'memory.current').write_text('0')
            (directory / 'memory.stat').write_text('inactive_file 0\nfile_dirty 0\nfile_writeback 0\n')
            (directory / 'memory.events').write_text('oom 0\noom_kill 0\n')
        proc = s.Proc(procroot)
        with self.assertRaisesRegex(ValueError, 'Aggregate memory'):
            s.memory_gate(proc, {'reserve_bytes': 256*s.MIB})
        (cg.parent / 'memory.max').write_text(str(6*1024*s.MIB))
        result = s.memory_gate(proc, {'reserve_bytes': 256*s.MIB})
        self.assertEqual(result['eligible_bytes'], 6*1024*s.MIB)
        self.assertEqual(len(result['effective_cgroup_limits']), 2)

    def test_no_new_oom_event(self):
        (self.root / 'memory.events').write_text('oom 0\noom_kill 1\n')
        with self.assertRaisesRegex(ValueError, 'OOM'):
            s.no_new_oom_events({'effective_cgroup_limits': [{'path': str(self.root), 'memory_events': 'oom 0\noom_kill 0\n'}]})

    def test_probe_schema_key_sets_match(self):
        path = Path(__file__).resolve().parents[1] / 'network-ci-native-probe/protocol-schema.json'
        definitions = json.loads(path.read_text())['$defs']
        self.assertEqual(set(definitions['pass']['required']), set(pass_row('server', 101, 1000)))
        self.assertEqual(definitions['input']['properties']['nonce']['maximum'], 2**63-1)

    def make_synthetic_spec(self):
        # This temporary toy closure is test data, never an official seal or JAR.
        pins, trees = [], []
        def file(relative, content=b'synthetic-only'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o444)
            pins.append({'path': str(path), 'bytes': len(content), 'sha256': s.digest(path)})
            return str(path)
        java = file('jdk/bin/java')
        trees.append(str(self.root / 'jdk'))
        probe = file('probe/network-control.jar')
        source_paths = [file('probe/source/protocol-schema.json', b'{}'), file('probe/source/build.gradle')]
        source_rows = [dict(row, path=Path(row['path']).name) for row in pins if row['path'] in source_paths]
        manifest = file('probe/source/source-manifest.json', json.dumps({'schema': 1, 'status': 'SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE', 'files': source_rows}).encode())
        probe_pin = next(row for row in pins if row['path'] == probe)
        build = file('probe/build-receipt.json', json.dumps({'schema': 1, 'status': 'BUILT', 'source_manifest_sha256': s.digest(manifest),
                     'artifact_path': probe, 'artifact_sha256': probe_pin['sha256'], 'artifact_bytes': probe_pin['bytes']}).encode())
        xvfb = file('graphics/Xvfb')
        preflight = file('graphics/preflight.json', b'{"synthetic":true}')
        receipts = [file('receipt1.json', b'{}'), file('receipt2.json', b'{}')]
        file('assets/indexes/17.json', b'{}')
        trees.append(str(self.root / 'assets'))
        spec = {'schema': 'network-ci-pair-v1', 'target': 'native-neoforge', 'port': 25631,
                'authorization': {'offline_identity_reference': 'SYNTHETIC TEST ONLY', 'eula_reference': 'SYNTHETIC TEST ONLY',
                                  'ci_pair_review_reference': 'SYNTHETIC TEST ONLY'},
                'inputs': pins, 'immutable_trees': trees, 'probe_path': probe,
                'probe_source_manifest': manifest, 'probe_build_receipt': build,
                'source_receipts': receipts, 'pair_lock': str(self.root / 'pair.lock'),
                'graphics': {'display': ':77', 'pid': 99, 'start_ticks': 123, 'executable': xvfb,
                             'preflight': preflight, 'reserve_bytes': 256*s.MIB}}
        for role in ('server', 'client'):
            profile = self.root / role
            mods = [file(role + '/mods/' + name + '.jar') for name in ('a', 'b', 'c')]
            file(role + '/mods/network-control.jar')
            for kind in ('config', 'defaultconfigs'):
                file(role + '/' + kind + '/neoforge-server.toml', b'advertiseDedicatedServerToLan=false\n')
                trees.append(str(profile / kind))
            trees.append(str(profile / 'mods'))
            command = [java, '-Xmx1280m', '-XX:ActiveProcessorCount=2', '-cp', probe, 'synthetic.Main']
            env = {k: str(profile / v) for k, v in s.PRIVATE.items()}
            env.update(JAVA_HOME=str(self.root / 'jdk'), PATH=str(self.root / 'jdk') + '/bin:/usr/bin:/bin',
                       LANG='C.UTF-8', TZ='UTC', DISPLAY=':77', LIBGL_ALWAYS_SOFTWARE='true', GALLIUM_DRIVER='llvmpipe')
            if role == 'client':
                command += ['--username', s.NAME, '--uuid', s.IDENTITY, '--quickPlayMultiplayer', '127.0.0.1:25631',
                            '--accessToken', '0', '--gameDir', str(profile), '--assetsDir', str(self.root / 'assets'), '--assetIndex', '17']
            else:
                command += ['nogui']
                props = {'server-ip': '127.0.0.1', 'server-port': '25631', 'online-mode': 'false',
                         'enforce-secure-profile': 'false', 'white-list': 'true', 'enforce-whitelist': 'true',
                         'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
                         'max-players': '1', 'level-name': 'world'}
                file('server/server.properties', ''.join(k+'='+v+'\n' for k,v in props.items()).encode())
                file('server/whitelist.json', json.dumps([{'uuid': s.IDENTITY, 'name': s.NAME}]).encode())
                file('server/ops.json', b'[]')
                file('server/eula.txt', b'eula=true\n')
            spec[role] = {'cwd': str(profile), 'command': command, 'environment': env, 'original_mods': mods, 'managed_mods': []}
        return spec

    def test_exact_pair_seal_checks_synthetic_closure(self):
        spec = self.make_synthetic_spec()
        synthetic_sha = hashlib.sha256(b'synthetic-only').hexdigest()
        with patch.object(s, 'ORIGINAL_MODS', {'a.jar': synthetic_sha, 'b.jar': synthetic_sha}), \
                patch.object(s, 'EMI_MODS', {'native-neoforge': ('c.jar', synthetic_sha)}):
            s.verify_spec(spec)
            changed = copy.deepcopy(spec)
            changed['client']['command'][1] = '-Xmx1024m'
            with self.assertRaisesRegex(ValueError, '1280'):
                s.verify_spec(changed)
            changed = copy.deepcopy(spec)
            changed['client']['environment']['JAVA_TOOL_OPTIONS'] = 'synthetic'
            with self.assertRaisesRegex(ValueError, 'closed'):
                s.verify_spec(changed)
            changed = copy.deepcopy(spec)
            changed['client']['command'] += ['-XX:MaxHeapSize=512m']
            with self.assertRaisesRegex(ValueError, 'heap override'):
                s.verify_spec(changed)
            extra = self.root / 'client/mods/extra.jar'
            extra.write_bytes(b'not in closure')
            with self.assertRaisesRegex(ValueError, 'Unsealed file'):
                s.verify_spec(spec)


if __name__ == '__main__':
    unittest.main()
