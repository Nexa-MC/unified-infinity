#!/usr/bin/env python3
"""Bounded compile-only recovery. Does not launch a game, modify locks or upload inputs."""
import argparse, ctypes, datetime, fcntl, hashlib, json, math, os, pathlib, selectors, signal, subprocess, time, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
API = ROOT / 'fabric-compile-recovery/api1'
SOURCE = ROOT / 'quilt-lifecycle-next-source'
JDK = API / '.toolchains/jdk-21.0.12.1+1'
LIMITS = ['-Xms16m', '-Xmx384m', '-XX:MaxMetaspaceSize=128m', '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC']
STOP = []

def require(value, message):
    if not value: raise ValueError(message)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def pin(path, **extra):
    path = pathlib.Path(path).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path), **extra}

def verify(path, sha256, size=None):
    path = pathlib.Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing/nonregular input ' + str(path))
    require(digest(path) == sha256, 'input hash mismatch ' + str(path))
    if size is not None: require(path.stat().st_size == size, 'input size mismatch ' + str(path))
    return path.resolve()

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')

def pack(path, entries):
    require(not path.exists(), 'refuse output overwrite ' + str(path))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16; z.writestr(info, data)

def adopt_owned_descendants():
    require(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'process-local child subreaper unavailable')

def group_members(group):
    result = []
    for path in pathlib.Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group:
                require(int(fields[3]) == group and path.stat().st_uid == os.geteuid(), 'owned group identity changed')
                result.append((int(path.name), fields[0]))
        except (FileNotFoundError, ProcessLookupError): continue
    return result

def cleanup_owned_group(proc):
    # Membership is limited to the fresh session/group of this exact Popen.
    # Reaping the leader is not proof that TERM-resistant descendants are gone.
    adopted = []
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        current = group_members(proc.pid)
        if any(state not in ('Z', 'X') for _, state in current):
            try: os.killpg(proc.pid, sig)
            except ProcessLookupError: pass
        until = time.monotonic() + 3
        while time.monotonic() < until:
            proc.poll()
            current = group_members(proc.pid)
            for pid, state in current:
                if pid == proc.pid or state not in ('Z', 'X'): continue
                try:
                    reaped, _ = os.waitpid(pid, os.WNOHANG)
                    if reaped: adopted.append(reaped)
                except ChildProcessError: pass
            if not group_members(proc.pid): break
            time.sleep(.03)
        if not group_members(proc.pid): break
    proc.wait(timeout=3)
    require(not group_members(proc.pid), 'owned descendants survived TERM/KILL/reap')
    return adopted

def phase(name, argv, out, deadline, cap=120):
    require(not STOP, 'owner cancelled')
    duration = min(cap, deadline - time.monotonic()); require(duration > 0, 'overall deadline expired')
    start = time.monotonic(); log = out / (name + '.log'); proc = None; selector = None
    record = {'name': name, 'argv': argv, 'timeoutSeconds': duration, 'cleanupOwnerPid': os.getpid()}
    try:
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(out), 'TMPDIR': str(out / 'tmp'), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
        proc = subprocess.Popen(argv, cwd=out, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        record.update(pid=proc.pid, pgid=os.getpgid(proc.pid), sid=os.getsid(proc.pid))
        selector = selectors.DefaultSelector(); selector.register(proc.stdout, selectors.EVENT_READ)
        total = 0
        with log.open('xb') as handle:
            while selector.get_map():
                require(not STOP, 'owner cancelled')
                require(time.monotonic() - start < duration, 'phase timeout ' + name)
                for key, _ in selector.select(.1):
                    data = os.read(key.fd, 65536)
                    if not data: selector.unregister(key.fileobj); continue
                    total += len(data); require(total <= 4 * 1024 * 1024, 'phase log bound ' + name)
                    handle.write(data)
            while proc.poll() is None:
                require(not STOP, 'owner cancelled')
                require(time.monotonic() - start < duration, 'phase timeout ' + name); time.sleep(.02)
            record['exitCode'] = proc.returncode
    finally:
        if selector: selector.close()
        if proc:
            if proc.stdout: proc.stdout.close()
            record['adoptedDescendantsReaped'] = cleanup_owned_group(proc)
            record['reaped'] = proc.poll() is not None
            try: os.killpg(proc.pid, 0); record['groupGone'] = False
            except ProcessLookupError: record['groupGone'] = True
        record['elapsedSeconds'] = round(time.monotonic() - start, 3)
        if log.exists(): record['log'] = pin(log)
        write_json(out / (name + '.process.json'), record)
    require(record.get('exitCode') == 0, 'phase failed ' + name)
    require(record.get('reaped') and record.get('groupGone'), 'process cleanup failed ' + name)
    return record

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=pathlib.Path)
    parser.add_argument('--deadline-epoch', required=True, type=float); args = parser.parse_args()
    require(math.isfinite(args.deadline_epoch) and args.deadline_epoch > time.time(), 'expired/nonfinite deadline')
    deadline = time.monotonic() + min(360, args.deadline_epoch - time.time())
    out = args.output.resolve(); require(out.parent == HERE and not out.exists(), 'fresh direct child output required')
    out.mkdir(); (out / 'tmp').mkdir(); (out / 'empty').mkdir(); (out / 'tools').mkdir()
    result = {'schema': 1, 'status': 'INCOMPLETE', 'diagnosticOnly': True, 'runtimeAcceptance': False, 'baselineAcceptance': False, 'gameLaunched': False, 'ciStarted': False, 'originalArtifactLocksChanged': False, 'phases': [], 'builder': pin(__file__), 'startedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'callerDeadlineEpoch': args.deadline_epoch, 'limits': LIMITS, 'serialJvmOnly': True}
    try:
        source_manifest = SOURCE / 'source-recovery.json'; source = json.loads(source_manifest.read_text())
        require(source['archiveSha256'] == '655c90673ce9f6d1cc0783037fe9a066dfaa774c3f347752f8ece8035c5c1762' and len(source['files']) == 9, 'historical source binding')
        archive = verify(ROOT / 'published-2109/recovery/api1/sources/accepted-v6-reconstruction-base.zip', source['archiveSha256'])
        with zipfile.ZipFile(archive) as z:
            for row in source['files']:
                require(hashlib.sha256(z.read(row['path'])).hexdigest() == row['sha256'], 'archive source mismatch ' + row['path'])
                verify(SOURCE / row['path'], row['sha256'], row['bytes'])
        result.update(sourceArchive=pin(archive), sourceManifest=pin(source_manifest), sourceFiles=source['files'], historicalBuildReport=pin(SOURCE / 'four-loader/quilt-probe/build/build-report.json', notFreshProof=True))
        jdk_manifest = verify(ROOT / 'independent-quilt-api-verification/jdk-input-verification.json', 'f01898929ae478e4bdb546eae2b056ef87e9d91232713f1568070fc53ba9de71')
        jdk_files = json.loads(jdk_manifest.read_text())['files']; require(len(jdk_files) == 249, 'JDK manifest inventory')
        for row in jdk_files: verify(JDK.parent / row['path'], row['sha256'], row['bytes'])
        result.update(jdkManifest=pin(jdk_manifest), jdkCanonicalFilesVerified=249, jdkRoot=str(JDK))
        product_lock = ROOT / 'published-2109/work/network-pair-cold-glue/product-input-lock.json'
        product = json.loads(product_lock.read_text())['artifacts']; pinned = {}
        for name in ['qsl_base-alpha5.jar', 'lifecycle_events-alpha5.jar', 'loader-0.30.1.jar']:
            row = next(x for x in product if x['path'].endswith('/' + name))
            path = HERE / 'inputs' / name
            if name.startswith('loader-'): path = ROOT / 'independent-quilt-api-verification/work/api1' / row['path']
            pinned[name] = verify(path, row['sha256'], row['bytes'])
        art = verify(API / 'ci/runtime-maven/net/neoforged/AutoRenamingTool/2.0.17/AutoRenamingTool-2.0.17-all.jar', 'e977ee4422efb51eb54cc99f939833cef769de8b4aa1043294ce5400c60f3b1f', 751270)
        mapping_owner = verify(ROOT / 'fabric-network-probe-candidate/inputs/ffloader.jar', 'dc8829a0d9b5fa19eb0c50d54c981445fb21cba2abd2a39c5ff0b58ff7d5c1e1', 3459840)
        with zipfile.ZipFile(mapping_owner) as z: mapping_bytes = z.read('mappings/mappings.tiny')
        require(hashlib.sha256(mapping_bytes).hexdigest() == 'e67166ff4c4f6380d4d04c06545d7d9548806a325a92e77b2435612a80646692', 'mapping pin')
        mapping = out / 'mappings.tiny'; mapping.write_bytes(mapping_bytes)
        server_bundle = verify(API / 'run/neoforge-native/libraries/net/minecraft/server/1.21.1/server-1.21.1.jar', 'e3bc55693e93cda0188f2e60aea28113fc647c5e85a15fa3d1b347349231b4bb', 51627615)
        embedded = []; libraries = []; original_server = None
        with zipfile.ZipFile(server_bundle) as z:
            for category in ['versions', 'libraries']:
                for line in z.read('META-INF/' + category + '.list').decode().splitlines():
                    expected, coordinate, relative = line.split('\t')
                    require('..' not in pathlib.PurePosixPath(relative).parts and not relative.startswith('/'), 'embedded path')
                    entry = 'META-INF/' + category + '/' + relative; data = z.read(entry)
                    require(hashlib.sha256(data).hexdigest() == expected, 'official embedded hash')
                    target = out / 'official-inputs' / category / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
                    embedded.append(pin(target, archiveEntry=entry, coordinate=coordinate, origin='hash-verified embedded official Mojang server bundle'))
                    if category == 'libraries': libraries.append(target)
                    else: require(original_server is None, 'multiple server entries'); original_server = target
        export = API / 'run/api1-unified-client-build/client-launch-inputs.json'
        mixin_row = next(row for row in json.loads(export.read_text())['inputs'] if '/sponge-mixin/' in row['path'])
        mixin = verify(mixin_row['path'], '1d45cfe3ae4a2eab38dc74276803748cf799088986260d6d912e50ddb35d15c5')
        annotations = next((ROOT / 'independent-quilt-api-verification/work/api1').rglob('annotations-24.1.0.jar'))
        verify(annotations, '27a770dc7ce50500918bb8c3c0660c98290630ec796b5e3cf6b90f403b3033c6', 30570)
        libraries.append(annotations)
        jsr305 = verify(API / 'ci/runtime-maven/com/google/code/findbugs/jsr305/3.0.2/jsr305-3.0.2.jar', '766ad2a0783f2687962c8ad74ceecc38a28b9f72a2d085ee438b7813e928d0c7', 19936)
        libraries.append(jsr305)
        asm = [verify(row['path'], row['sha256']) for row in json.loads(export.read_text())['inputs'] if '/org/ow2/asm/' in row['path']]
        require(len(asm) == 5, 'five original ASM dependencies')
        remap_tools = [pinned['loader-0.30.1.jar'], *asm]
        result['remapperInputs'] = [pin(p) for p in remap_tools]
        result['abiVerifierInputs'] = [pin(art)]
        library_list = out / 'remap-libraries.txt'; library_list.write_text(''.join(str(p) + '\n' for p in libraries))
        javac = [str(JDK / 'bin/javac'), *['-J' + x for x in LIMITS], '-proc:none', '--release', '21', '-encoding', 'UTF-8', '-implicit:none', '-sourcepath', str(out / 'empty')]
        java = [str(JDK / 'bin/java'), *LIMITS]
        result['phases'].append(phase('compile-tools', [*javac, '-cp', os.pathsep.join(map(str, [art, *remap_tools])), '-d', str(out / 'tools'), str(HERE / 'RemapServer.java'), str(HERE / 'AbiCheck.java')], out, deadline))
        derived = out / 'server-intermediary-derived-not-historical.jar'
        result['phases'].append(phase('derive-real-server', [*java, '-cp', os.pathsep.join(map(str, [out / 'tools', *remap_tools])), 'RemapServer', str(mapping), str(original_server), str(derived), str(library_list)], out, deadline))
        with zipfile.ZipFile(original_server) as z: original_class_count = sum(n.endswith('.class') for n in z.namelist())
        with zipfile.ZipFile(derived) as z:
            require(sum(n.endswith('.class') for n in z.namelist()) == original_class_count, 'remapped game class inventory changed')
            for name in ['net/minecraft/class_1792.class', 'net/minecraft/class_18.class', 'net/minecraft/class_7923.class', 'net/minecraft/server/MinecraftServer.class']: require(name in z.namelist(), 'missing genuine remapped game class')
        result['derivedGame'] = pin(derived, notHistorical=True, gameClassCount=original_class_count, parentServerBundle=pin(server_bundle), embeddedEntry=next(x for x in embedded if x['path'] == str(original_server)), mappingOwner=pin(mapping_owner), mappingSha256=digest(mapping), remapper=pin(pinned['loader-0.30.1.jar']), mapping=pin(mapping), resourcesIntentionallyExcluded=True, runnableGameArchive=False, provenance='Derived classes-only compile input from genuine official obfuscated server via original locked Quilt TinyRemapper and locked official-to-intermediary mapping; NOT historical Fabric remapped bytes or runnable game archive')
        closure = [pinned['loader-0.30.1.jar'], pinned['qsl_base-alpha5.jar'], pinned['lifecycle_events-alpha5.jar'], derived, mixin, *libraries]
        require(len(closure) == len(set(closure)), 'duplicate compile classpath')
        for path in closure:
            with zipfile.ZipFile(path) as z:
                if 'META-INF/MANIFEST.MF' in z.namelist(): require(not any(x.lower().startswith('class-path:') for x in z.read('META-INF/MANIFEST.MF').decode().splitlines()), 'implicit manifest classpath')
        result['compileInputs'] = [pin(p, origin='derived real game' if p == derived else 'verified original dependency') for p in closure]
        result['embeddedOfficialInputs'] = embedded
        cp = os.pathsep.join(map(str, closure)); fixture = SOURCE / 'four-loader/quilt-probe'
        sources = sorted((fixture / 'src').rglob('*.java')); require(len(sources) == 3, 'exact three original Java sources')
        for p in sources: require('net.fabricmc' not in p.read_text() and 'net.neoforged' not in p.read_text(), 'foreign API source')
        artifacts = []
        for iteration in [1, 2]:
            classes = out / ('classes-' + str(iteration)); classes.mkdir()
            result['phases'].append(phase('compile-fixture-' + str(iteration), [*javac, '-verbose', '-cp', cp, '-d', str(classes), *map(str, sources)], out, deadline))
            entries = {str(p.relative_to(classes)): p.read_bytes() for p in sorted(classes.rglob('*.class'))}
            require(len(entries) == 5, 'five fixture classes')
            for data in entries.values(): require(data[:4] == b'\xca\xfe\xba\xbe' and int.from_bytes(data[6:8], 'big') == 65 and b'net/fabricmc' not in data and b'net/neoforged' not in data, 'class version/API boundary')
            entries.update({str(p.relative_to(fixture / 'resources')): p.read_bytes() for p in sorted((fixture / 'resources').rglob('*')) if p.is_file()})
            artifact = out / ('unified-native-quilt-probe-0.1.0' + ('' if iteration == 1 else '-rebuild') + '.jar'); pack(artifact, entries); artifacts.append(artifact)
        require(digest(artifacts[0]) == digest(artifacts[1]), 'deterministic recompile mismatch')
        require('quilt.mod.json' in entries and 'fabric.mod.json' not in entries and len(entries) == 8, 'native-only descriptor/entry inventory')
        cp_list = out / 'compile-classpath.txt'; cp_list.write_text(''.join(str(p) + '\n' for p in closure))
        result['phases'].append(phase('actual-abi', [*java, '-cp', str(out / 'tools') + os.pathsep + str(art), 'AbiCheck', str(artifacts[0]), str(cp_list)], out, deadline))
        abi = (out / 'actual-abi.log').read_text(); require('ACTUAL_CLASSFILE_ABI_BINDING classes=5 ' in abi and abi.rstrip().endswith(' PASS'), 'ABI verifier completion')
        result['negativeControls'] = []
        positive = json.loads(entries['quilt.mod.json'])
        for case, dependency in [('missing-dependency', {'id': 'native_quilt_missing_dependency', 'versions': '=9.9.9'}), ('loader-version', {'id': 'quilt_loader', 'versions': '>=0.31.0'})]:
            modified = json.loads(entries['quilt.mod.json']); modified['quilt_loader']['depends'] = [d for d in modified['quilt_loader']['depends'] if d['id'] != dependency['id']] + [dependency]
            payload = {**entries, 'quilt.mod.json': (json.dumps(modified, indent=2) + '\n').encode()}
            jar = out / ('unified-native-quilt-probe-' + case + '.jar'); pack(jar, payload)
            with zipfile.ZipFile(jar) as z:
                require(z.namelist() == sorted(entries), 'negative entry inventory')
                require(all(z.read(n) == entries[n] for n in entries if n != 'quilt.mod.json'), 'negative altered class/resource')
                require(dependency in json.loads(z.read('quilt.mod.json'))['quilt_loader']['depends'], 'negative descriptor')
            result['negativeControls'].append(pin(jar, case=case, expectedDependency=dependency, runtimeRejectionNotRun=True))
        for row in result['compileInputs']: verify(row['path'], row['sha256'], row['bytes'])
        for row in source['files']: verify(SOURCE / row['path'], row['sha256'], row['bytes'])
        result.update(status='PASS_COMPILE_ABI_ONLY', artifact=pin(artifacts[0], namespace='intermediary'), deterministicRecompile=True, rebuildArtifact=pin(artifacts[1]), classFiles=[{'path': n, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(), 'majorVersion': 65} for n, b in sorted(entries.items()) if n.endswith('.class')], jarEntries=[{'path': n, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n, b in sorted(entries.items())], nativeDescriptorOnly=True, foreignLoaderApiReferences=False, abiChecks=[s for s in abi.splitlines() if s.startswith(('METHOD ', 'FIELD '))], tools=[pin(HERE / n) for n in ['RemapServer.java', 'AbiCheck.java']], historicalArtifactReproduced=False, runtimeStatus='NOT RUN; no READY/tick/Mixin/SavedData/reopen claims', finishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
    except BaseException as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        write_json(out / 'result.json', result)
    print(json.dumps({'status': result['status'], 'artifact': result['artifact'], 'result': pin(out / 'result.json')}, indent=2))

if __name__ == '__main__':
    for number in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]: signal.signal(number, lambda n, f: STOP.append(n))
    adopt_owned_descendants()
    with (HERE / 'compile-owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
