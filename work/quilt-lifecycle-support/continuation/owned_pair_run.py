"""Reviewed-source candidate: exact Pair.run with two explicit continuation checks.

Not a standalone launcher. All globals are supplied from the exact pinned base.
"""
def run(self, seal_sha, seal_path):
    nonce = secrets.randbelow(2**63-1) + 1
    self.report['spec_sha256'] = seal_sha
    self.report['nonce'] = nonce
    lock = None
    try:
        lock_path = clean_path(self.spec['pair_lock'])
        lock = os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'r+')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_pair_seal(seal_path, seal_sha, self.spec)
        server_properties_before = capture_server_properties(self.spec)
        require(not any(p['ppid'] == os.getpid() for p in self.proc.all_identities()), 'CI supervisor requires no preexisting child processes')
        become_subreaper()
        for role in ('server', 'client'):
            profile = Path(self.spec[role]['cwd'])
            self.verify_profile_world(role, profile)
            for name in PROBE_FILES:
                require(not (profile / name).exists(), 'Stale probe input/result/release file')
                require(not (profile / (name + '.tmp')).exists() and
                        not (profile / (name + '.supervisor-tmp')).exists(), 'Stale probe temporary file')
        graphics = verify_graphics(self.spec, self.proc)
        self.report['graphics'] = graphics
        self.report['initial_memory_gate'] = memory_gate(self.proc, graphics)
        write_new(Path(self.spec['client']['cwd']) / PROBE_FILES[0],
                  {'schema': 1, 'nonce': nonce, 'sequence': 1, 'port': self.spec['port']})
        self.report['phase'] = 'server_start'
        self.revalidate_continuation()
        self.spawn('server')
        self.wait(lambda: 'NETWORK_CONTROL_READY' in self.logs['server'].events and
                  any('Done (' in line and 'For help' in line for line in self.logs['server'].lines),
                  300, 'Dedicated server readiness', ('server',))
        validate_ready(self.logs['server'].events['NETWORK_CONTROL_READY'], self.identities['server'], self.spec['port'])
        self.observe('before_client')
        graphics = verify_graphics(self.spec, self.proc)
        self.report['client_memory_gate'] = memory_gate(self.proc, graphics, self.identities['server'])
        verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-before-client.json')
        self.report['phase'] = 'actual_client_join_and_payload'
        self.spawn('client')
        self.wait(lambda: all('NETWORK_CONTROL_JSON' in self.logs[r].events for r in ('server', 'client')),
                  180, 'Actual join and nonce round trip', ('server', 'client'))
        self.report['probe'] = self.probe_results(nonce)
        self.observe('after_matching_reply', connected=True)
        completed_gate = self.wait_for_completed_reload()
        self.report['phase'] = 'client_disconnect'
        completed_gate.before_release(time.monotonic(), all(self.children[r].poll() is None for r in ('server', 'client')))
        publish_release(Path(self.spec['client']['cwd']) / PROBE_FILES[1], {'schema': 1, 'nonce': nonce, 'sequence': 1})
        completed_gate.after_release(time.monotonic())
        self.wait(lambda: self.children['client'].poll() == 0 and
                  'NETWORK_CONTROL_DISCONNECTED' in self.logs['client'].events,
                  30, 'Clean client disconnect and exit', ('server',))
        validate_disconnect(self.logs['client'].events['NETWORK_CONTROL_DISCONNECTED'], self.identities['client'], nonce)
        self.observe('after_client_exit')
        self.report['phase'] = 'save_and_stop'
        self.drain()
        offset = len(self.logs['server'].lines)
        self.send(b'save-all flush\n')
        self.report['save_requested_after_line'] = offset
        def saved():
            lines = self.logs['server'].lines[offset:]
            started = next((i for i, line in enumerate(lines) if 'Saving the game' in line), None)
            return started is not None and any('Saved the game' in line or 'Saved the world' in line for line in lines[started+1:])
        self.wait(saved, 45, 'Save-all flush acknowledgment after command', ('server',))
        self.report['save_acknowledged_after_command'] = True
        self.send(b'stop\n')
        self.report['stop_requested'] = True
        self.wait(lambda: self.children['server'].poll() == 0, 30, 'Server stop')
        self.drain()
        require(any('All dimensions are saved' in line for line in self.logs['server'].lines[offset:]), 'Missing final all-dimensions save')
        self.probe_results(nonce)
        verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-after-stop.json')
        no_new_oom_events(self.report['initial_memory_gate'])
        verify_pair_seal(seal_path, seal_sha, self.spec)
        self.report['pair_spec_unchanged'] = True
        world = clean_path(str(Path(self.spec['server']['cwd']) / 'world/level.dat'))
        require(world.is_file() and 0 < world.stat().st_size <= 2*MIB, 'Saved world metadata missing or unbounded')
        self.report['saved_world_level_dat_sha256'] = digest(world)
        self.report['immutable_inputs_unchanged'] = True
        for capture in self.logs.values():
            capture.finish()
        require(set(self.logs['server'].events) == {'NETWORK_CONTROL_READY', 'NETWORK_CONTROL_JSON'} and
                set(self.logs['client'].events) == {'NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_DISCONNECTED'},
                'Unexpected role/event combination')
        # A wait predicate may reap after pump; console drain need not pump again.
        # Read the retained owned children, never infer success from cached exits.
        for role, child in self.children.items():
            require(role in self.identities and child.pid == self.identities[role]['pid'],
                    'Owned child identity mismatch at final exit reconciliation')
            self.report['exits'][role] = child.poll()
        require(set(self.children) == {'server', 'client'} and self.report['exits'] == {'server': 0, 'client': 0}, 'Both owned clean exits required')
        require(not any(p['pgrp'] in {i['pgrp'] for i in self.identities.values()} and p['state'] != 'Z'
                        for p in self.proc.all_identities()), 'Game process group survived')
        require(not any(p['ppid'] == os.getpid() for p in self.proc.all_identities()), 'Adopted game helper survived or requires reaping')
        self.report.update(passed=True, status='PASS', phase='complete')
    except (Exception, KeyboardInterrupt) as error:
        self.report.update(passed=False, status='INCONCLUSIVE')
        self.report['failure'] = type(error).__name__ + ': ' + str(error)
    finally:
        # A one-shot deadline or repeated CI cancellation must not interrupt
        # the bounded, identity-checked cleanup and evidence write.
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig in HANDLED_SIGNALS:
            signal.signal(sig, signal.SIG_IGN)
        if not self.report['passed']:
            self.cleanup()
        self.cpu_helpers.close(self)
        self.selector.close()
        for role, capture in self.logs.items():
            capture.close()
            self.report.setdefault('log_sha256', {})[role] = digest(self.destination / (role + '.log'))
        for child in self.children.values():
            for pipe in (child.stdin, child.stdout):
                if pipe is not None:
                    pipe.close()
        if lock is not None:
            lock.close()
        write_new(self.destination / 'result.json', self.report)
    return self.report
