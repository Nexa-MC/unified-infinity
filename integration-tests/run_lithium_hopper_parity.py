#!/usr/bin/env python3
"""Console-only, fixed-tick hopper semantics for unchanged Lithium on two hosts.

Fresh isolated profiles; no client, probes, datapacks, RCON, or extra mods. Runs
servers sequentially and reads both console SNBT and saved Anvil/NBT inventories.
Existing profiles are never overwritten; use another --run-id for another run.
"""
from __future__ import annotations
import argparse, datetime, gzip, hashlib, io, json, os, pathlib, re, select
import shutil, signal, struct, subprocess, sys, time, zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LITHIUM = 'lithium-fabric-0.15.4+mc1.21.1.jar'
PINNED = {
    LITHIUM: '92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa',
    'fabric-api-0.116.7+1.21.1.jar': '08018cc48c97415a38016a00dbd5a2c7a460ba6b7a051690a8cb3dbb5e8482a4',
    'unified-infinity-0.1.0-dev.jar': '3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e',
    'unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar': 'c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e',
    'unified-infinity-preload-0.1.0-dev.jar': '7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99',
}
POSITIONS = {'a_source': (1,202,1), 'a_hopper': (1,201,1), 'a_sink': (1,200,1),
             'b_hopper': (5,201,1), 'b_sink': (5,200,1),
             'c_source': (9,202,1), 'c_hopper': (9,201,1), 'c_sink': (9,200,1)}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
coords = lambda p: ' '.join(map(str, p))

def inventory(entries):
    return sorted([{'slot': int(x['Slot']), 'id': x['id'], 'count': int(x['count'])}
                   for x in entries], key=lambda x: x['slot'])

def items(*stacks):
    return [{'slot': i, 'id': 'minecraft:'+name, 'count': n}
            for i, (name, n) in enumerate(stacks)]

def full_items(name):
    return [{'slot': i, 'id': 'minecraft:'+name, 'count': 64} for i in range(27)]

def snbt_items(stacks):
    return '['+','.join('{Slot:%db,id:"%s",count:%d}' % (s['slot'],s['id'],s['count']) for s in stacks)+']'

class Snbt:
    """Minimal strict parser for server-generated block entity SNBT."""
    def __init__(self, text): self.text, self.i = text, 0
    def ws(self):
        while self.i < len(self.text) and self.text[self.i].isspace(): self.i += 1
    def take(self, c):
        self.ws(); assert self.text[self.i] == c, (self.i,self.text)
        self.i += 1
    def token(self):
        self.ws()
        if self.text[self.i] in '\"\'':
            q = self.text[self.i]; self.i += 1; out = ''
            while self.text[self.i] != q:
                c = self.text[self.i]; self.i += 1
                if c == '\\': c = self.text[self.i]; self.i += 1
                out += c
            self.i += 1; return out
        start = self.i
        while self.i < len(self.text) and self.text[self.i] not in ':,{}[] \t\r\n': self.i += 1
        assert self.i > start, self.text[start:]
        return self.text[start:self.i]
    def value(self):
        self.ws(); c = self.text[self.i]
        if c == '{':
            self.i += 1; out = {}; self.ws()
            while self.text[self.i] != '}':
                k = self.token(); self.take(':'); out[k] = self.value(); self.ws()
                if self.text[self.i] != ',': break
                self.i += 1
            self.take('}'); return out
        if c == '[':
            self.i += 1; out = []; self.ws()
            if self.text[self.i:self.i+2] in ('B;','I;','L;'): self.i += 2
            while self.text[self.i] != ']':
                out.append(self.value()); self.ws()
                if self.text[self.i] != ',': break
                self.i += 1
            self.take(']'); return out
        quoted = c in '\"\''; t = self.token()
        if not quoted and re.fullmatch(r'-?\d+[bBsSlL]?', t): return int(t.rstrip('bBsSlL'))
        return t
    def parse(self):
        out = self.value(); self.ws(); assert self.i == len(self.text), self.text[self.i:]
        return out

class Nbt:
    """Read-only standard big-endian NBT decoder, no external dependencies."""
    def __init__(self, data): self.f = io.BytesIO(data)
    def read(self, n):
        b = self.f.read(n); assert len(b) == n, 'Truncated NBT'; return b
    def number(self, fmt): return struct.unpack('>'+fmt, self.read(struct.calcsize('>'+fmt)))[0]
    def string(self): return self.read(self.number('H')).decode('utf-8')
    def payload(self, kind):
        if kind in range(1,7): return self.number({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[kind])
        if kind == 7: return self.read(self.number('i'))
        if kind == 8: return self.string()
        if kind == 9:
            subtype = self.number('B'); size = self.number('i')
            assert size >= 0; return [self.payload(subtype) for _ in range(size)]
        if kind == 10:
            out = {}
            while (subtype := self.number('B')):
                name = self.string(); out[name] = self.payload(subtype)
            return out
        if kind in (11,12):
            size = self.number('i'); assert size >= 0
            return [self.number('i' if kind == 11 else 'q') for _ in range(size)]
        raise ValueError('Unsupported NBT tag: '+str(kind))
    def parse(self):
        kind = self.number('B'); name = self.string(); return self.payload(kind)

def saved_inventories(profile):
    path = profile/'world/region/r.0.0.mca'; data = path.read_bytes()
    location = int.from_bytes(data[:4], 'big'); sector, count = location >> 8, location & 255
    assert sector and count, 'Test chunk not saved'
    chunk = data[sector*4096:(sector+count)*4096]
    length = int.from_bytes(chunk[:4], 'big'); compression = chunk[4]; payload = chunk[5:4+length]
    assert compression in (1,2,3), 'Unsupported/external chunk compression'
    decoded = gzip.decompress(payload) if compression == 1 else zlib.decompress(payload) if compression == 2 else payload
    value = Nbt(decoded).parse(); entities = value['block_entities']; out = {}
    for label,p in POSITIONS.items():
        match = [x for x in entities if tuple(x.get(k) for k in ('x','y','z')) == p]
        assert len(match) == 1, (label,match)
        out[label] = inventory(match[0]['Items'])
    return {'region_sha256':sha(path),'chunk_status':value.get('Status'), 'inventories':out}

def world_manifest(profile):
    world = profile/'world'
    return {str(p.relative_to(world)):sha(p) for p in sorted(world.rglob('*')) if p.is_file()}

def prepare(which, run_id):
    profile = ROOT/'run'/f'lithium-hopper-{run_id}-{which}'
    assert not profile.exists(), 'Refusing to overwrite existing profile: '+str(profile)
    source = ROOT/'run'/('lithium-native' if which == 'native' else 'source-built-lithium-unified')
    profile.mkdir(); shutil.copytree(source/'libraries', profile/'libraries')
    shutil.copytree(source/'mods',profile/'mods'); (profile/'config').mkdir()
    shutil.copy2(source/'config/lithium.properties',profile/'config/lithium.properties')
    if which == 'native': shutil.copy2(source/'server.jar',profile/'server.jar')
    else: shutil.copy2(source/'config/connector.json',profile/'config/connector.json')
    # Parent task has explicit approval to accept this EULA for isolated tests.
    assert (source/'eula.txt').read_text().strip() == 'eula=true'
    shutil.copy2(source/'eula.txt',profile/'eula.txt')
    port = 25576 if which == 'native' else 25577
    properties = {'server-ip':'127.0.0.1','server-port':port,'online-mode':'true','enable-rcon':'false',
        'enable-query':'false','enable-status':'false','level-name':'world','level-seed':'1211',
        'level-type':'minecraft:normal','max-players':1,'view-distance':2,'simulation-distance':2,
        'spawn-protection':0,'difficulty':'peaceful','motd':'Isolated Lithium hopper semantic regression',
        'enable-command-block':'false','sync-chunk-writes':'true','max-tick-time':60000}
    (profile/'server.properties').write_text(''.join(f'{k}={v}\n' for k,v in properties.items()))
    return profile

class Server:
    def __init__(self, profile, which, tag, timeout):
        self.profile, self.which, self.tag, self.timeout = profile, which, tag, timeout
        self.started = time.monotonic(); self.lines = []; self.buffer = b''; self.counter = 0
        self.commands = []; self.steps = []; self.snapshots = []; self.ready = False; self.saved = False
        self.log = (ROOT/'logs'/(tag+'.log')).open('wb')
        self.mods = {p.name:sha(p) for p in sorted((profile/'mods').glob('*.jar'))}
        names = {LITHIUM,'fabric-api-0.116.7+1.21.1.jar'} if which == 'native' else set(PINNED)-{'fabric-api-0.116.7+1.21.1.jar'}
        assert set(self.mods) == names
        assert all(PINNED[k] == v for k,v in self.mods.items())
        flags = [x for x in (profile/'config/lithium.properties').read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
        assert not flags, 'Unexpected Lithium override flags'
        if which == 'unified': assert json.loads((profile/'config/connector.json').read_text())['enableMixinSafeguard']
        props = (profile/'server.properties').read_text().splitlines()
        for s in ('server-ip=127.0.0.1','online-mode=true','enable-rcon=false','enable-query=false'): assert s in props
        java = ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'
        args = [str(java),'-Xms512M','-Xmx2G']
        if which == 'native':
            args += ['-Dfabric.gameJarPath='+str(profile/'server.jar'),'-cp',os.pathsep.join(str(x) for x in sorted((profile/'libraries').rglob('*.jar')))+os.pathsep+str(profile/'server.jar'),'net.fabricmc.loader.impl.launch.knot.KnotServer','nogui']
        else: args += ['@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt','nogui']
        self.proc = subprocess.Popen(args,cwd=profile,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
        try:
            self.wait(lambda: any('Done (' in x and 'For help' in x for x in self.lines), 300)
        except BaseException:
            self.cleanup()
            raise
        self.ready = True
    def pump(self, duration=0.2):
        if time.monotonic()-self.started > self.timeout: raise TimeoutError('Server cycle exceeded timeout')
        r,_,_ = select.select([self.proc.stdout],[],[],duration)
        if r:
            data = os.read(self.proc.stdout.fileno(),65536)
            if data:
                self.log.write(data); self.log.flush(); self.buffer += data
                while b'\n' in self.buffer:
                    line,self.buffer = self.buffer.split(b'\n',1)
                    self.lines.append(re.sub(r'\x1b\[[0-9;]*m','',line.decode(errors='replace')))
            elif self.proc.poll() is not None: return
    def wait(self, predicate, timeout=30):
        end = time.monotonic()+timeout
        while not predicate():
            if self.proc.poll() is not None:
                self.pump(0)
                if predicate(): return
                raise RuntimeError('Server exited early: '+str(self.proc.returncode))
            if time.monotonic() > end: raise TimeoutError('Timed out waiting for server console')
            self.pump()
    def send(self, command):
        self.commands.append(command); self.proc.stdin.write((command+'\n').encode()); self.proc.stdin.flush()
    def command(self, command):
        start = len(self.lines); self.counter += 1; marker = f'HOPPER_ACK_{self.counter:05d}'
        self.send(command); self.send('say '+marker)
        self.wait(lambda: any(marker in x for x in self.lines[start:]))
        result = self.lines[start:]
        for line in result:
            assert not any(x in line for x in ('Unknown or incomplete command','Incorrect argument','Expected ','No block entity was found','That position is not loaded')), line
        return result
    def gametime(self):
        lines = self.command('time query gametime')
        matches = [re.search(r'The time is (\d+)',x) for x in lines]
        values = [int(x[1]) for x in matches if x]; assert len(values) == 1, lines
        return values[0]
    def step(self, n):
        before = self.gametime(); self.command(f'tick step {n}'); end = time.monotonic()+n/20+20
        while True:
            after = self.gametime()
            if after == before+n: break
            assert after < before+n, (before,n,after)
            if time.monotonic() > end: raise TimeoutError(f'Tick step stalled at {after-before}/{n}')
            self.pump(.2)
        self.steps.append({'requested':n,'before_gametime':before,'after_gametime':after,'exact':True})
    def snapshot(self, stage, expected):
        observed, raw, block_ids = {}, {}, {}
        for label in expected:
            lines = self.command('data get block '+coords(POSITIONS[label]))
            matches = [x.split('has the following block data:',1)[1].strip() for x in lines if 'has the following block data:' in x]
            assert len(matches) == 1, lines
            raw[label] = matches[0]; block = Snbt(matches[0]).parse()
            observed[label] = inventory(block['Items']); block_ids[label] = block['id']
        expected_ids = {}
        if stage == 'source_block_entity_replacement_invalidates_cache': expected_ids['a_source'] = 'minecraft:barrel'
        if stage == 'destination_block_entity_replacement_invalidates_cache': expected_ids['b_sink'] = 'minecraft:barrel'
        if stage.startswith('reopen_') or stage.startswith('pre_save_'):
            expected_ids.update({'a_source':'minecraft:barrel','b_sink':'minecraft:barrel'})
        kinds_match = all(block_ids[k] == v for k,v in expected_ids.items())
        result = {'stage':stage,'expected':expected,'observed':observed,'raw_snbt':raw,
            'block_entity_ids':block_ids,'expected_replaced_block_entity_ids':expected_ids,
            'passed':observed == expected and kinds_match}
        self.snapshots.append(result)
        print(f'{self.tag}: {stage}: {"PASS" if result["passed"] else "FAIL"}',flush=True)
        assert result['passed'], json.dumps(result,indent=2)
        return observed
    def stop(self):
        lines = self.command('save-all flush'); self.saved = any('Saved the game' in x for x in lines)
        assert self.saved, lines
        self.send('stop'); self.wait(lambda: self.proc.poll() is not None, 45); self.pump(0)
        self.log.close()
        assert self.proc.returncode == 0
        assert any('All dimensions are saved' in x for x in self.lines)
    def cleanup(self):
        if self.proc.poll() is None:
            try:
                self.send('stop'); self.proc.wait(timeout=15)
            except Exception:
                self.proc.terminate()
                try: self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait()
        self.log.close()
    def report(self):
        text = '\n'.join(self.lines)
        active = bool(re.search(r'Loaded configuration file for Lithium: \d+ options available, 0 override\(s\) found', text))
        recognized = bool(re.search(r'(?:- lithium 0\.15\.4\+mc1\.21\.1|Lithium 0\.15\.4[+_]mc1\.21\.1 \(lithium\))',text,re.I))
        audit = self.profile/'.cache/connector/patch_audit.txt'
        audit_text = audit.read_text() if audit.exists() else None
        safeguard = self.which == 'native' or (audit_text is not None and re.search(r'^Failed: 0$',audit_text,re.M) is not None)
        return {'tag':self.tag,'profile':self.which,'ready':self.ready,'saved':self.saved,
            'exit_code':self.proc.returncode,'duration_seconds':round(time.monotonic()-self.started,3),
            'lithium_config_executed_zero_overrides':active,'lithium_version_recognized':recognized,
            'input_mod_sha256':self.mods,'exact_tick_steps':self.steps,'snapshots':self.snapshots,
            'commands':self.commands,'safeguard_audit_zero_failed':safeguard,'safeguard_audit':audit_text,
            'passed':self.ready and self.saved and self.proc.returncode == 0 and active and recognized and safeguard and all(x['passed'] for x in self.snapshots)}

def populate(s,label,stacks):
    s.command('data merge block '+coords(POSITIONS[label])+' {Items:'+snbt_items(stacks)+'}')

def replace_slot(s,label,slot,item,count=1):
    s.command('item replace block '+coords(POSITIONS[label])+f' container.{slot} with minecraft:{item} {count}')

def first_cycle(s):
    s.command('tick freeze'); s.command('gamerule randomTickSpeed 0'); s.command('gamerule doMobSpawning false')
    s.command('gamerule doDaylightCycle false'); s.command('gamerule doWeatherCycle false')
    s.command('forceload add 0 0'); s.step(8)
    s.command('fill 0 199 0 12 205 3 minecraft:air')
    for label in ('a_sink','a_source','b_sink','c_sink','c_source'):
        s.command('setblock '+coords(POSITIONS[label])+' minecraft:chest')
    for label in ('a_hopper','b_hopper','c_hopper'):
        s.command('setblock '+coords(POSITIONS[label])+' minecraft:hopper[facing=down]')
    s.command('setblock 10 201 1 minecraft:redstone_block')
    s.step(32); s.snapshot('idle_empty_inventories',{x:[] for x in POSITIONS})
    replace_slot(s,'a_source',0,'iron_ingot',4); s.step(48)
    sink_a=items(('iron_ingot',4))
    s.snapshot('empty_source_inventory_change_wakes_transfer',{'a_source':[],'a_hopper':[],'a_sink':sink_a})
    s.step(32); replace_slot(s,'a_source',0,'gold_ingot',3); s.step(40)
    sink_a=items(('iron_ingot',4),('gold_ingot',3))
    s.snapshot('second_source_inventory_change_after_idle',{'a_source':[],'a_hopper':[],'a_sink':sink_a})
    s.command('setblock '+coords(POSITIONS['a_source'])+' minecraft:barrel')
    replace_slot(s,'a_source',0,'copper_ingot',5); s.step(64)
    sink_a=items(('iron_ingot',4),('gold_ingot',3),('copper_ingot',5))
    s.snapshot('source_block_entity_replacement_invalidates_cache',{'a_source':[],'a_hopper':[],'a_sink':sink_a})
    full_b=full_items('cobblestone'); populate(s,'b_sink',full_b); populate(s,'b_hopper',items(('iron_ingot',6)))
    s.step(40); s.snapshot('full_destination_blocks_without_item_loss',{'b_hopper':items(('iron_ingot',6)),'b_sink':full_b})
    replace_slot(s,'b_sink',0,'air'); s.step(64)
    open_b=[{'slot':0,'id':'minecraft:iron_ingot','count':6}]+full_b[1:]
    s.snapshot('destination_inventory_change_retries_failed_push',{'b_hopper':[],'b_sink':open_b})
    replace_slot(s,'b_hopper',0,'diamond',5); s.step(32)
    s.snapshot('incompatible_destination_blocks_second_item',{'b_hopper':items(('diamond',5)),'b_sink':open_b})
    s.command('setblock '+coords(POSITIONS['b_sink'])+' minecraft:barrel'); s.step(56)
    s.snapshot('destination_block_entity_replacement_invalidates_cache',{'b_hopper':[],'b_sink':items(('diamond',5))})
    replace_slot(s,'c_source',0,'emerald',4); s.step(48)
    s.snapshot('redstone_power_prevents_extraction',{'c_source':items(('emerald',4)),'c_hopper':[],'c_sink':[]})
    s.command('setblock 10 201 1 minecraft:air'); s.step(48)
    s.snapshot('redstone_unpower_resumes_transfer',{'c_source':[],'c_hopper':[],'c_sink':items(('emerald',4))})
    # Stable nonempty source and blocked hopper prove persistence, then resume in cycle 2.
    s.command('setblock 10 201 1 minecraft:redstone_block'); replace_slot(s,'c_source',0,'emerald',3)
    full_b=full_items('stone'); populate(s,'b_sink',full_b); replace_slot(s,'b_hopper',0,'diamond',2); s.step(40)
    expected={'a_source':[],'a_hopper':[],'a_sink':sink_a,'b_hopper':items(('diamond',2)),'b_sink':full_b,
              'c_source':items(('emerald',3)),'c_hopper':[],'c_sink':items(('emerald',4))}
    s.snapshot('pre_save_nonempty_blocked_and_locked_inventories',expected)
    return expected

def second_cycle(s, expected):
    s.command('tick freeze')
    # No setup or inventory writes before this observation.
    s.snapshot('reopen_exact_saved_inventory_state',expected)
    replace_slot(s,'b_sink',0,'air'); s.command('setblock 10 201 1 minecraft:air')
    replace_slot(s,'a_source',0,'gold_ingot',2); s.step(56)
    expected=dict(expected)
    expected.update({'a_sink':items(('iron_ingot',4),('gold_ingot',5),('copper_ingot',5)),
        'b_hopper':[],'b_sink':[{'slot':0,'id':'minecraft:diamond','count':2}]+full_items('stone')[1:],
        'c_source':[],'c_sink':items(('emerald',7))})
    s.snapshot('reopen_resumes_inventory_and_redstone_invalidations',expected)
    return expected

def execute(args):
    results=[]; report={'run_id':args.run_id,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'harness_sha256':sha(pathlib.Path(__file__)),
        'scope':'Fixed-tick hopper transfer, inventory invalidation, block-entity replacement, redstone control and save/reopen. No performance, players, client rendering, arbitrary mods, or exhaustive Mixin coverage.',
        'network':'Fresh loopback-only profiles 127.0.0.1:25576/25577; online-mode=true; RCON/query/status disabled; no player accounts',
        'world_seed':'1211','lithium_overrides':[],'profiles':results,'passed':False}
    destination=ROOT/'logs'/f'lithium-hopper-{args.run_id}-summary.json'
    active=None
    def interrupt(signum,frame):
        if active is not None: active.cleanup()
        raise SystemExit(128+signum)
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    try:
        for which in ('native','unified'):
            profile=prepare(which,args.run_id); entry={'profile':which,'path':str(profile.relative_to(ROOT)),'cycles':[]};results.append(entry)
            expected=None; prior_manifest=None
            for cycle in (1,2):
                before=world_manifest(profile)
                if cycle == 1: assert not before
                else: assert before == prior_manifest, 'Saved world changed between cycles'
                tag=f'lithium-hopper-{args.run_id}-{which}-{cycle}'
                active=Server(profile,which,tag,args.timeout)
                try:
                    expected=first_cycle(active) if cycle == 1 else second_cycle(active,expected)
                    active.stop(); result=active.report(); disk=saved_inventories(profile)
                    result['saved_nbt']=disk; result['saved_nbt_matches_console']=disk['inventories'] == expected
                    result['world_before']=before; prior_manifest=world_manifest(profile); result['world_after']=prior_manifest
                    result['passed']=result['passed'] and result['saved_nbt_matches_console']
                    entry['cycles'].append(result)
                    (ROOT/'logs'/(tag+'.json')).write_text(json.dumps(result,indent=2)+'\n')
                    assert result['passed'], tag+' did not satisfy all checks'
                except BaseException as exc:
                    active.cleanup(); failed=active.report(); failed['failure']=f'{type(exc).__name__}: {exc}'
                    failed['passed']=False; entry['cycles'].append(failed)
                    (ROOT/'logs'/(tag+'.json')).write_text(json.dumps(failed,indent=2)+'\n')
                    raise
                finally: active.cleanup(); active=None
            entry['passed']=all(c['passed'] for c in entry['cycles'])
            print(which+': both cycles and on-disk NBT PASS',flush=True)
        native,unified=results
        signatures=lambda x: [(s['stage'],s['observed']) for c in x['cycles'] for s in c['snapshots']]
        report['native_unified_observations_identical']=signatures(native)==signatures(unified)
        report['passed']=all(x['passed'] for x in results) and report['native_unified_observations_identical']
    except BaseException as exc:
        report['failure']=f'{type(exc).__name__}: {exc}'
        if active is not None:
            try: active.cleanup(); report['failed_cycle']=active.report()
            except Exception as cleanup_error: report['cleanup_error']=str(cleanup_error)
        raise
    finally:
        destination.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':report['passed'],'summary':str(destination),'failure':report.get('failure')}),flush=True)
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True);parser.add_argument('--timeout',type=int,default=480)
    args=parser.parse_args();assert re.fullmatch(r'[a-z0-9-]+',args.run_id)
    sys.exit(execute(args))
