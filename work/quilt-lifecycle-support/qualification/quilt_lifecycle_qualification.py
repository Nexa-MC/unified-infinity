"""Read-only, fail-closed Quilt/QSL lifecycle evidence checks.

This module never launches or admits a game. A reviewed actual compile is an
external prerequisite, not something a self-declared report can establish.
The original supervisor rejects an existing world: an independently reviewed
continuation runner is required for a real reopen. See CONTRACT.md.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import stat
import struct
import types
import zlib

SUPERVISOR_SHA256 = '2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'
MARKER = 'native_quilt_qsl_alpha5_v1'
ARTIFACT_NAME = 'unified-native-quilt-probe-0.1.0.jar'
ROLES = ('server', 'client')
MAX_JSON = 8 * 1024 * 1024
MAX_LOG = 2 * 1024 * 1024
MAX_LINE = 32 * 1024
MAX_NBT = 64 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
SOURCE_HASHES = {
 'resources/infinity_native_quilt_probe.mixins.json': '96f9e6307d03383409137a93d2404cd3a4ebc0238432df37daa1ca0fbbccd4b9',
 'resources/native-quilt-proof.txt': '34bcc75c0355a9c1e8a15cd6ddd852b51c6f65b351e0456d9bc269f5eb343657',
 'resources/quilt.mod.json': '8f5c209e656228a23a994f4511c830c249942136f16e358d2ca0e2e12e925adf',
 'src/dev/infinity/quiltprobe/ClientProbe.java': '60fd1b6f920d0edcffea2dded0654b7f3396206948cdd8a1f5eb67ad5263234f',
 'src/dev/infinity/quiltprobe/QuiltProbe.java': 'd794d5291aff5e095d33dd54f7795ae3addaaca785eb2da337fb42c3b3bed82f',
 'src/dev/infinity/quiltprobe/mixin/TickMixin.java': '632dc968592cf2a4a3388e35fb78e70ed1798073218791e899025b5187512916',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(row, keys, label):
    require(type(row) is dict and set(row) == set(keys), 'Invalid ' + label)


def integer(value, low=0, high=2**63-1):
    return type(value) is int and low <= value <= high


def sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def decode(payload):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('Nonfinite JSON')
    try:
        result = json.loads(payload.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise ValueError('Malformed or duplicate JSON') from None
    require(type(result) is dict, 'JSON object required')
    return result


def canonical_path(value, root=None):
    require(isinstance(value, (str, Path)), 'Invalid path type')
    raw = str(value)
    require(raw.startswith('/') and os.path.normpath(raw) == raw and '\\' not in raw
            and '\x00' not in raw and '\n' not in raw and '\r' not in raw,
            'Noncanonical input path')
    path = Path(raw)
    require(str(path) == raw and (root is None or path.is_relative_to(root)), 'Path leaves evidence root')
    return path


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_regular(path):
    """Walk every ancestor with openat/O_NOFOLLOW, not just the final file."""
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=directory)
            os.close(directory)
            directory = nxt
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        return descriptor
    finally:
        os.close(directory)


def stable_read(path, maximum):
    path = canonical_path(path)
    descriptor = None
    try:
        descriptor = _open_regular(path)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and 1 <= before.st_size <= maximum,
                'Nonregular, empty or oversized evidence input')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            payload = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        check = _open_regular(path)
        try:
            current = os.fstat(check)
        finally:
            os.close(check)
        require(_signature(before) == _signature(after) == _signature(current)
                and len(payload) == before.st_size, 'Evidence input changed while reading')
        return payload, {'path': str(path), 'bytes': len(payload), 'sha256': digest(payload)}
    except OSError:
        raise ValueError('Evidence unavailable or symlink refused') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def pin(path, maximum=MAX_JSON):
    return stable_read(path, maximum)[1]


class Evidence:
    def __init__(self, root):
        self.root = canonical_path(root)
        require(self.root.is_dir() and self.root.resolve() == self.root, 'Canonical evidence root required')
        self.seen = {}
        self.final_checks = []

    def read(self, row, maximum=MAX_JSON):
        exact(row, ('path', 'bytes', 'sha256'), 'file pin')
        require(integer(row['bytes'], 1, maximum) and sha(row['sha256']), 'Invalid bounded file pin')
        path = canonical_path(row['path'], self.root)
        data, current = stable_read(path, maximum)
        require(current == row, 'Evidence differs from pinned bytes')
        previous = self.seen.get(str(path))
        require(previous is None or previous[0] == row, 'Conflicting pins for same evidence')
        self.seen[str(path)] = (dict(row), maximum)
        return data

    def json(self, row, maximum=MAX_JSON):
        return decode(self.read(row, maximum))

    def capture(self, path, maximum=MAX_JSON, expected_sha=None):
        path = canonical_path(path, self.root)
        data, row = stable_read(path, maximum)
        require(expected_sha is None or row['sha256'] == expected_sha, 'Evidence terminal hash mismatch')
        self.read(row, maximum)
        return data, row

    def finish(self):
        for check in self.final_checks:
            check()
        for row, maximum in self.seen.values():
            require(stable_read(row['path'], maximum)[1] == row,
                    'Evidence changed between validation checks')
        for check in self.final_checks:
            check()
        return [row for row, _ in self.seen.values()]


class NBT:
    """Small bounded big-endian NBT reader; no unbounded gzip helper/library."""
    def __init__(self, data):
        self.data, self.offset, self.nodes = data, 0, 0

    def take(self, size):
        require(integer(size, 0, MAX_NBT) and self.offset + size <= len(self.data), 'Truncated or oversized NBT')
        result = self.data[self.offset:self.offset + size]
        self.offset += size
        return result

    def number(self, fmt):
        return struct.unpack('>' + fmt, self.take(struct.calcsize('>' + fmt)))[0]

    def string(self):
        size = self.number('H')
        require(size <= 4096, 'Oversized NBT string')
        try:
            return self.take(size).decode('utf-8', 'strict')
        except UnicodeError:
            raise ValueError('Malformed NBT string') from None

    def value(self, kind, depth=0):
        self.nodes += 1
        require(depth <= 16 and self.nodes <= 4096, 'NBT nesting/node bound')
        if kind in (1, 2, 3, 4, 5, 6):
            return self.number({1:'b', 2:'h', 3:'i', 4:'q', 5:'f', 6:'d'}[kind])
        if kind == 8:
            return self.string()
        if kind in (7, 11, 12):
            size = self.number('i')
            require(integer(size, 0, 8192), 'NBT array bound')
            return self.take(size * {7:1, 11:4, 12:8}[kind])
        if kind == 9:
            subtype, size = self.number('B'), self.number('i')
            require(integer(size, 0, 4096) and 0 <= subtype <= 12 and (subtype != 0 or size == 0), 'NBT list bound/type')
            return [self.value(subtype, depth+1) for _ in range(size)]
        if kind == 10:
            result = {}
            while True:
                subtype = self.number('B')
                if subtype == 0:
                    return result
                name = self.string()
                require(name not in result, 'Duplicate NBT compound key')
                result[name] = self.value(subtype, depth+1)
        raise ValueError('Unsupported or invalid NBT tag')


def saved_data(payload):
    require(type(payload) is bytes and 1 <= len(payload) <= MAX_NBT, 'Compressed NBT bound')
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = decoder.decompress(payload, MAX_NBT + 1)
        require(len(data) <= MAX_NBT and decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail, 'Truncated, concatenated or oversized gzip NBT')
    except zlib.error:
        raise ValueError('Corrupt gzip NBT') from None
    reader = NBT(data)
    require(reader.number('B') == 10 and reader.string() == '', 'NBT unnamed root compound required')
    root = reader.value(10)
    require(reader.offset == len(data), 'Trailing NBT payload')
    exact(root, ('data', 'DataVersion'), 'SavedData root')
    require(integer(root['DataVersion'], 1, 2**31-1), 'Invalid SavedData DataVersion')
    exact(root['data'], ('marker',), 'SavedData payload')
    require(type(root['data']['marker']) is str and root['data']['marker'] == MARKER,
            'SavedData marker mismatch')
    return {'marker': MARKER, 'data_version': root['DataVersion'], 'uncompressed_bytes': len(data)}


def reject_acceptance_claims(value):
    if type(value) is dict:
        for key, item in value.items():
            normalized = re.sub(r'[_:-]', '', key).lower()
            if normalized in ('baselineacceptance', 'originalacceptance', 'runtimeacceptance',
                              'runtimeadmission', 'qslnetworkingacceptance', 'qslnetworkacceptance',
                              'qslforgefacadewireacceptance', 'qslforgefacadeacceptance', 'fullapicompatibility'):
                require(item is False, 'Forged acceptance claim refused')
            reject_acceptance_claims(item)
    elif type(value) is list:
        for item in value:
            reject_acceptance_claims(item)


def load_supervisor(path):
    payload, row = stable_read(path, 1024 * 1024)
    require(row['sha256'] == SUPERVISOR_SHA256, 'Unchanged original supervisor source required')
    module = types.ModuleType('qsl_original_supervisor_validation')
    module.__file__ = str(path)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    require(pin(path, 1024 * 1024) == row, 'Supervisor changed during checked import')
    return module, row


# This is a typed exception for the existing graphics producer, not a second
# general evidence root. No live process/display observation happens here.
GRAPHICS_ROOT_RELATIVE = 'work/network-pair-cold-glue/graphics-production'
GRAPHICS_READY_MAX = 1024 * 1024
GRAPHICS_PREFLIGHT_MAX = 32 * 1024
GRAPHICS_FILE_MAX = 512 * 1024 * 1024
GRAPHICS_TOTAL_MAX = 2 * 1024 * 1024 * 1024


def _graphics_inputs_contract(root, spec):
    """Check retained local provenance only; NOT root ownership/live acceptance.

    Kept separate solely so structural tests can state exactly what they prove
    on environments whose existing host files are not owned by UID 0. Production
    callers must use classify_graphics_inputs, never this parser as admission.
    """
    evidence = Evidence(root)
    require(type(spec) is dict and type(spec.get('inputs')) is list
            and 1 <= len(spec['inputs']) <= 100000, 'Bounded graphics source spec inputs required')
    pins = {}
    for row in spec['inputs']:
        exact(row, ('path','bytes','sha256'), 'graphics source input pin')
        require(type(row['path']) is str and integer(row['bytes'],1) and sha(row['sha256']),
                'Invalid graphics source input pin')
        canonical_path(row['path'])
        require(row['path'] not in pins, 'Duplicate graphics source input pin')
        pins[row['path']] = row
    producer = evidence.root/GRAPHICS_ROOT_RELATIVE
    ready_path = str(producer/'actual-preflight/ready.json')
    preflight_path = str(producer/'actual-preflight/graphics-preflight.json')
    provenance_path = str(producer/'installed-provenance.json')
    receipts = spec.get('source_receipts')
    require(type(receipts) is list and all(type(value) is str for value in receipts)
            and receipts.count(ready_path) == 1 and ready_path in pins,
            'Unique fixed graphics ready source receipt and sealed pin required')
    ready = evidence.json(pins[ready_path], GRAPHICS_READY_MAX)
    exact(ready, ('schema','status','pair_acceptance','graphics','inputs','collector_pid',
                  'maximum_lifetime_seconds','owner_cutoff'), 'original graphics ready receipt')
    require(type(ready['schema']) is int and ready['schema'] == 1
            and ready['status'] == 'GRAPHICS_PREFLIGHT_READY' and ready['pair_acceptance'] is False
            and integer(ready['collector_pid'],1,2**31-1)
            and integer(ready['maximum_lifetime_seconds'],2520,2520), 'Graphics ready identity/status mismatch')
    cutoff = ready['owner_cutoff']
    exact(cutoff, ('work_monotonic','work_wall','cleanup_monotonic','cleanup_wall'), 'retained graphics owner cutoff')
    require(all(type(value) in (int,float) and math.isfinite(value) and value > 0 for value in cutoff.values()),
            'Invalid retained graphics cutoff value')
    for kind in ('monotonic','wall'):
        work, cleanup = cutoff['work_'+kind], cutoff['cleanup_'+kind]
        require(math.isclose(cleanup-work,90,rel_tol=0,
                    abs_tol=min(1e-6,2*max(math.ulp(work),math.ulp(cleanup)))),
                'Retained graphics cleanup reserve changed')
    graphics = ready['graphics']
    exact(graphics, ('display','pid','start_ticks','executable','preflight','reserve_bytes'), 'retained graphics identity')
    require(type(graphics['display']) is str and re.fullmatch(r':\d{1,5}',graphics['display'])
            and integer(graphics['pid'],1,2**31-1) and integer(graphics['start_ticks'],1)
            and graphics['pid'] != ready['collector_pid']
            and integer(graphics['reserve_bytes'],256*1024*1024)
            and graphics['preflight'] == preflight_path, 'Invalid fixed graphics identity/preflight path')
    canonical_path(graphics['executable'])
    # Explicit types above avoid bool/int equivalence inside a dict comparison.
    require(type(spec.get('graphics')) is dict and spec['graphics'] == graphics
            and all(type(spec['graphics'].get(key)) is type(value) for key,value in graphics.items()),
            'Graphics ready identity differs from current sealed spec')
    require(type(ready['inputs']) is list and 4 <= len(ready['inputs']) <= 129,
            'Bounded original graphics ready input roster required')
    ready_pins = {}
    total = 0
    for row in ready['inputs']:
        exact(row, ('path','bytes','sha256'), 'graphics ready input pin')
        require(type(row['path']) is str and integer(row['bytes'],1,GRAPHICS_FILE_MAX) and sha(row['sha256']),
                'Invalid bounded graphics ready input')
        canonical_path(row['path'])
        require(row['path'] not in ready_pins, 'Duplicate graphics ready input pin')
        require(pins.get(row['path']) == row, 'Graphics ready input missing/replaced in sealed spec')
        ready_pins[row['path']] = row
        total += row['bytes']
    require(total <= GRAPHICS_TOTAL_MAX, 'Graphics retained input byte bound exceeded')
    local_paths = {path for path in ready_pins if Path(path).is_relative_to(evidence.root)}
    require(local_paths == {preflight_path,provenance_path},
            'Only fixed local graphics preflight/provenance receipts may classify host inputs')
    require(graphics['executable'] in ready_pins and graphics['executable'] not in local_paths,
            'Current graphics executable missing from exact host roster')
    preflight = evidence.json(ready_pins[preflight_path], GRAPHICS_PREFLIGHT_MAX)
    exact(preflight, ('schema','display','xvfb_pid','xvfb_start_ticks','renderer','direct_rendering',
                      'glx_capable','gl_probe_peak_rss_bytes','measured_headroom_bytes','input_sha256'),
          'original retained graphics preflight')
    require(type(preflight['schema']) is int and preflight['schema'] == 1
            and type(preflight['display']) is str and preflight['display'] == graphics['display']
            and integer(preflight['xvfb_pid'],1,2**31-1) and preflight['xvfb_pid'] == graphics['pid']
            and integer(preflight['xvfb_start_ticks'],1) and preflight['xvfb_start_ticks'] == graphics['start_ticks']
            and preflight['glx_capable'] is True and preflight['direct_rendering'] is True
            and type(preflight['renderer']) is str and 'llvmpipe' in preflight['renderer'].lower()
            and integer(preflight['gl_probe_peak_rss_bytes'],1)
            and integer(preflight['measured_headroom_bytes'],256*1024*1024)
            and preflight['measured_headroom_bytes'] == graphics['reserve_bytes'],
            'Retained graphics preflight identity/measurement mismatch')
    expected_roster = {path:row['sha256'] for path,row in ready_pins.items() if path != preflight_path}
    require(type(preflight['input_sha256']) is dict and preflight['input_sha256'] == expected_roster,
            'Graphics preflight hash roster differs from exact ready input closure')
    provenance = evidence.json(ready_pins[provenance_path], GRAPHICS_READY_MAX)
    # The current fixed installed producer emits this schema. No arbitrary
    # external receipt, alternate snapshot producer or guessed path is selected.
    exact(provenance, ('schema','status','observation_reference','distribution','runner',
                       'packages','file_packages','generated_config','file_sha256'),
          'fixed installed graphics provenance')
    require(type(provenance['schema']) is int and provenance['schema'] == 2
            and provenance['status'] == 'OBSERVED_INSTALLED_PACKAGES'
            and provenance['distribution'] == {'id':'ubuntu','version_id':'24.04'},
            'Original installed graphics provenance required')
    require(type(provenance['observation_reference']) is str
            and 1 <= len(provenance['observation_reference']) <= 512,
            'Bounded original package observation reference required')
    image = provenance['runner']
    exact(image, ('ImageOS','ImageVersion','machine'), 'installed graphics runner')
    require(image['ImageOS'] == 'ubuntu24' and image['machine'] == 'x86_64'
            and type(image['ImageVersion']) is str and re.fullmatch(r'\d{8}\.\d+\.\d+',image['ImageVersion']),
            'Original Ubuntu graphics runner identity required')
    packages = provenance['packages']
    require(type(packages) is list and 3 <= len(packages) <= 256, 'Bounded original graphics package roster required')
    identities, names = set(), set()
    for package in packages:
        exact(package, ('package','version','architecture'), 'installed graphics package identity')
        require(type(package['package']) is str and re.fullmatch(r'[a-z0-9][a-z0-9+.-]+',package['package'])
                and type(package['version']) is str and 1 <= len(package['version']) <= 128
                and re.fullmatch(r'[0-9A-Za-z.+:~\-]+',package['version'])
                and package['architecture'] in ('amd64','all'), 'Invalid installed graphics package identity')
        identity = package['package']+':'+package['architecture']+'='+package['version']
        require(identity not in identities, 'Duplicate installed graphics package identity')
        identities.add(identity);names.add(package['package'])
    require({'xvfb','mesa-utils-bin','libgl1-mesa-dri'} <= names, 'Original graphics tool/package identities required')
    external = {path:row for path,row in ready_pins.items() if path not in local_paths}
    require(type(provenance['file_sha256']) is dict
            and provenance['file_sha256'] == {path:row['sha256'] for path,row in external.items()},
            'Installed provenance host hashes differ from ready/preflight closure')
    generated = provenance['generated_config']
    require(type(generated) is dict and set(generated) == {'/etc/ld.so.cache'}
            and set(generated) <= set(external), 'Unexpected generated graphics host input')
    for path,row in generated.items():
        require(row == {'kind':'root-owned-ldconfig-cache','sha256':external[path]['sha256']},
                'Generated loader-cache provenance mismatch')
    require(type(provenance['file_packages']) is dict
            and set(provenance['file_packages']) == set(external)-set(generated)
            and all(type(value) is str and value in identities for value in provenance['file_packages'].values()),
            'Graphics package ownership roster mismatch')
    observed_external = {path:row for path,row in pins.items() if not Path(path).is_relative_to(evidence.root)}
    require(observed_external == external, 'Unexpected or omitted external spec input outside exact graphics closure')
    return {'host_inputs':[external[path] for path in sorted(external)],
            'local_evidence':evidence.finish(), 'ready_pin':pins[ready_path],
            'preflight_pin':ready_pins[preflight_path], 'provenance_pin':ready_pins[provenance_path]}


def _verify_graphics_host_files(rows, module):
    """Use the unchanged original ownership/access/digest rules, not a mock."""
    for row in rows:
        path = module.clean_path(row['path'])
        before = path.stat(follow_symlinks=False)
        require(before.st_uid == 0, 'External graphics input must remain root-owned (uid 0)')
        require(stat.S_ISREG(before.st_mode) and before.st_size == row['bytes']
                and 1 <= before.st_size <= GRAPHICS_FILE_MAX, 'External graphics file type/size changed')
        module.file_pin(row)  # Keeps original system modes, actual access and parent rules.
        after = path.stat(follow_symlinks=False)
        require(_signature(before) == _signature(after) and before.st_mode == after.st_mode
                and before.st_uid == after.st_uid == 0,
                'External graphics identity changed during original verification')


def classify_graphics_inputs(root, spec, supervisor_path):
    """Return only exact sorted host pins after static retained-provenance checks.

    No caller-selected external receipt, generic path relaxation, live collector
    dependency, copying, ownership change or production test bypass is provided.
    Original finalizer/sealer/owner still own live Xvfb/display admission.
    """
    contract = _graphics_inputs_contract(root, spec)
    module, supervisor_pin = load_supervisor(supervisor_path)
    _verify_graphics_host_files(contract['host_inputs'], module)
    repeated = _graphics_inputs_contract(root, spec)
    require(repeated == contract, 'Graphics provenance changed during host verification')
    require(pin(supervisor_path,1024*1024) == supervisor_pin, 'Original graphics validator changed')
    return contract['host_inputs']


def _track_graphics_inputs(evidence, spec, supervisor_path, *, expected=None):
    """Register local bytes and separately typed host rechecks for proof replay."""
    inputs = spec.get('inputs')
    require(type(inputs) is list, 'Sealed input inventory required')
    exterior = any(type(row) is dict and type(row.get('path')) is str
                   and not Path(row['path']).is_relative_to(evidence.root) for row in inputs)
    if not exterior and 'graphics' not in spec:
        hosts = []  # Preserve existing non-graphics parser-only synthetic fixtures.
    else:
        hosts = classify_graphics_inputs(evidence.root,spec,supervisor_path)
        contract = _graphics_inputs_contract(evidence.root,spec)
        require(contract['host_inputs'] == hosts, 'Graphics classification changed before retention')
        for row in contract['local_evidence']:
            evidence.read(row,GRAPHICS_READY_MAX)
        def recheck():
            require(classify_graphics_inputs(evidence.root,spec,supervisor_path) == hosts,
                    'Typed host graphics provenance changed during qualification')
        evidence.final_checks.append(recheck)
    require(expected is None or hosts == expected, 'Retained typed host graphics evidence changed')
    return hosts



def fixture_gate(evidence, fixture, reviewed, *, synthetic_fixture=False):
    exact(fixture, ('artifact', 'source_manifest', 'compile_receipt'), 'fixture bundle')
    exact(reviewed, ('artifact_sha256', 'source_manifest_sha256', 'compile_receipt_sha256'), 'independent reviewed hashes')
    require(all(sha(v) for v in reviewed.values()), 'Independent reviewed hashes required')
    for key in fixture:
        exact(fixture[key], ('path', 'bytes', 'sha256'), 'fixture file pin')
        require(fixture[key]['sha256'] == reviewed[key + '_sha256'], 'Fixture differs from independently reviewed hash')
    evidence.read(fixture['artifact'], 4 * 1024 * 1024)
    require(Path(fixture['artifact']['path']).name == ARTIFACT_NAME, 'Distinct QSL artifact name required')
    manifest = evidence.json(fixture['source_manifest'])
    receipt = evidence.json(fixture['compile_receipt'])
    reject_acceptance_claims(manifest)
    reject_acceptance_claims(receipt)
    require(type(receipt.get('schema')) is int and receipt['schema'] == 1
            and receipt.get('status') == 'PASS_COMPILE_ABI_ONLY'
            and receipt.get('diagnosticOnly') is True and receipt.get('runtimeAcceptance') is False
            and receipt.get('gameLaunched') is False, 'Fresh compile-only receipt required')
    require(receipt.get('sourceManifest') == fixture['source_manifest'], 'Compile/source manifest mismatch')
    require(receipt.get('artifact') == dict(fixture['artifact'], namespace='intermediary'),
            'Compile/artifact namespace mismatch')
    require(receipt.get('syntheticFixture', False) is synthetic_fixture, 'Synthetic compile proof cannot become runtime evidence')
    require(manifest.get('status') == 'EXACT_HISTORICAL_SOURCE_EXTRACTED_NOT_COMPILED_OR_RUNTIME_READY'
            and type(manifest.get('files')) is list, 'Exact historical source manifest required')
    manifest_sources = {}
    for row in manifest['files']:
        exact(row, ('path', 'bytes', 'sha256'), 'source manifest pin')
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) == row['path'],
                'Noncanonical source manifest relative path')
        path = str(Path(fixture['source_manifest']['path']).parent / relative)
        require(path not in manifest_sources, 'Duplicate manifest source path')
        manifest_sources[path] = dict(row, path=path)
    sources = receipt.get('sourceFiles')
    require(type(sources) is list and len(sources) >= len(SOURCE_HASHES) and len(sources) <= 64,
            'Complete reviewed source/resource inventory required')
    sources = [dict(row, path=str(Path(fixture['source_manifest']['path']).parent / row['path']))
               if type(row) is dict and type(row.get('path')) is str and not Path(row['path']).is_absolute()
               else row for row in sources]
    require({row.get('path'): row for row in sources} == manifest_sources and len(sources) == len(manifest_sources),
            'Compile/source inventory mismatch')
    seen = set()
    for row in sources:
        path = canonical_path(row.get('path'), evidence.root)
        matched = [name for name in SOURCE_HASHES if str(path).endswith('/' + name)]
        require(len(matched) <= 1, 'Ambiguous fixture source path')
        if not matched:
            # Build scripts/readme may be present but cannot replace exact source/resources.
            evidence.read(row, 1024 * 1024)
            continue
        name = matched[0]
        require(name not in seen and row['sha256'] == SOURCE_HASHES[name], 'Changed or duplicate reviewed fixture source')
        seen.add(name)
        evidence.read(row, 1024 * 1024)
    require(seen == set(SOURCE_HASHES), 'Incomplete exact fixture source/resource closure')
    return {'artifact': fixture['artifact'], 'source_manifest': fixture['source_manifest'],
            'compile_receipt': fixture['compile_receipt']}


def _lifecycle_console_lines(payload):
    """Recognize only the observed ModLauncher highlight layout, not arbitrary ANSI.

    Its %highlight{...%n} places the reset after the physical newline. The
    residual reset can therefore precede the first direct CLASS_DEFINED write.
    Keep raw lines separately: transport/reload receipts refer to those bytes.
    """
    require(payload.endswith(b'\n') and b'\x00' not in payload, 'Truncated or malformed log')
    try:
        raw_lines = payload.decode('utf-8', 'strict').split('\n')[:-1]
    except UnicodeError:
        raise ValueError('Malformed UTF-8 log') from None
    require(all(len(line.encode('utf-8')) <= MAX_LINE for line in raw_lines), 'Oversized log line')
    logical, highlighted, native_started = [], False, False
    for raw in raw_lines:
        line, reset = raw, False
        if line.startswith('\x1b[m'):
            require(highlighted and not native_started, 'Unpaired or late console SGR reset')
            highlighted, reset, line = False, True, line[3:]
        color = next((value for value in ('\x1b[32m', '\x1b[33m') if line.startswith(value)), None)
        if color is not None:
            require(not highlighted and not native_started, 'Unpaired or late console SGR color')
            line = line[len(color):]
            level = 'INFO' if color == '\x1b[32m' else 'WARN'
            require(re.match(r'\[(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}\] '
                             r'\[[^\[\]\r\n]{1,256}/'+level+r'\] \[[^\[\]\r\n]{1,256}\]: ', line)
                    is not None, 'SGR color requires matching ModLauncher log header')
            highlighted = True
        elif reset:
            require(line == 'NATIVE_QUILT_PROBE CLASS_DEFINED', 'Unexpected console SGR reset boundary')
        # No generic escape removal: embedded SGR, alternate reset/color codes,
        # OSC, cursor movement, CR, C1 controls, and DEL all remain forbidden.
        require(not any((ord(c) < 32 and c != '\t') or 0x7f <= ord(c) <= 0x9f for c in line),
                'Malformed control character in log')
        has_marker = 'NATIVE_QUILT_PROBE' in line or 'NETWORK_CONTROL_' in line
        require(not highlighted or not has_marker, 'Probe marker inside highlighted console message')
        native_started = native_started or 'NATIVE_QUILT_PROBE' in line
        logical.append(line)
    require(not highlighted, 'Unterminated console SGR highlight')
    return raw_lines, logical


def lifecycle_log(payload, *, role, phase, fixture_path, fixture_sha):
    """Accept only the fixture's actual stdout grammar, never invented JSON events."""
    raw_lines, lines = _lifecycle_console_lines(payload)
    markers, events = [], {}
    for index, line in enumerate(lines):
        if 'NATIVE_QUILT_PROBE' in line:
            require(line.startswith('NATIVE_QUILT_PROBE ') and len(line) <= 4096 and '\r' not in line,
                    'Malformed QSL marker prefix/line')
            markers.append((index, line))
        if 'NETWORK_CONTROL_' in line:
            require(any(line.startswith(name+' ') for name in ('NETWORK_CONTROL_READY', 'NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_DISCONNECTED')),
                    'Unknown or malformed transport event')
        for name in ('NETWORK_CONTROL_READY', 'NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_DISCONNECTED'):
            if name in line:
                require(line.startswith(name+' ') and name not in events and len(line) <= 2048,
                        'Malformed or duplicate transport event')
                events[name] = (index, decode(line[len(name)+1:].encode()))
        require(not any(fail in line for fail in ('NATIVE_QUILT_PROBE FAIL', 'NETWORK_CONTROL_FAIL',
                'Failed to start the minecraft server', 'Failed to load mods', 'ModLoadingException',
                'MixinApplyError', 'Exception in thread', 'OutOfMemoryError')), 'Failure marker in current log')
    prefix = 'NATIVE_QUILT_PROBE '
    common = [prefix+'CLASS_DEFINED',
      prefix+'PASS stage=pre_launch count=1 native_id=unified-quilt-probe group=dev.infinity.probes version=0.1.0+native source='+str(fixture_path)+' sha256='+fixture_sha,
      prefix+'PASS stage=init count=1 registry=unified_quilt_probe:anchor',
      prefix+'PASS stage=method_reference count=1 order=after_init']
    expected = common + ([prefix+'PASS stage=client_init count=1'] if role == 'client' else [
      prefix+'PASS stage=server_init count=1',
      prefix+'PASS stage=automatic_ready count=1',
      prefix+'PASS stage=ready phase='+phase+' marker='+MARKER+' read_before_write='+str(phase=='reopen').lower()])
    require(len(markers) == (5 if role == 'client' else 9), 'Wrong QSL marker count or role')
    require([line for _, line in markers[:len(expected)]] == expected, 'QSL marker order/identity/source/phase mismatch')
    result = {'markers': [{'line': i+1, 'text': line} for i, line in markers]}
    if role == 'server':
        tick = re.fullmatch(r'NATIVE_QUILT_PROBE PASS stage=ready_to_save ticks=5 mixin_ticks=([1-9][0-9]{0,9}) auto_ready=1 phase='+phase, markers[7][1])
        stop = re.fullmatch(r'NATIVE_QUILT_PROBE PASS stage=stopped ticks=([1-9][0-9]{0,9})', markers[8][1])
        require(tick is not None and 5 <= int(tick[1]) <= 2**31-1, 'Missing actual five tick/mixin sentinel')
        require(stop is not None and 5 <= int(stop[1]) <= 2**31-1, 'Missing final STOPPED callback')
        result.update(ticks=5, mixin_ticks=int(tick[1]), stopped_ticks=int(stop[1]), read_before_write=phase=='reopen')
    return result, events, raw_lines


def _identity(row):
    require(type(row) is dict and integer(row.get('pid'), 1, 2**31-1)
            and integer(row.get('start_ticks'), 1) and type(row.get('pgrp')) is int
            and row['pgrp'] == row['pid'] and type(row.get('session')) is int
            and row['session'] == row['pid'], 'Invalid owned role identity')


def _transport(report, spec, spec_pin):
    reject_acceptance_claims(report)
    reject_acceptance_claims(spec)
    require(type(spec.get('schema')) is str and spec['schema'] == 'network-ci-pair-v2'
            and spec.get('target') == 'unified' and integer(spec.get('port'), 25632, 25632),
            'Unified sealed pair required')
    diagnostic = spec.get('diagnostic_profile')
    require(type(diagnostic) is dict and diagnostic.get('diagnostic_only') is True
            and diagnostic.get('baseline_acceptance') is False, 'Diagnostic-only sealed profile required')
    require(type(report.get('schema')) is int and report['schema'] == 1
            and report.get('target') == 'unified' and report.get('status') == 'PASS'
            and report.get('passed') is True and report.get('game_launched') is True
            and report.get('phase') == 'complete' and report.get('spec_sha256') == spec_pin['sha256']
            and report.get('pair_spec_unchanged') is True and report.get('immutable_inputs_unchanged') is True
            and report.get('diagnostic_only') is True and report.get('baseline_acceptance') is False
            and report.get('diagnostic_profile') == diagnostic, 'No matching terminal diagnostic transport PASS')
    exact(report.get('exits'), ROLES, 'paired exits')
    require(all(integer(report['exits'][r], 0, 0) for r in ROLES), 'Both current owned exit0 required')
    require(report.get('cleanup_signals') == [] and report.get('cpu_probe_cleanup_signals', []) == []
            and report.get('cleanup_incomplete', False) is False
            and not any(k.endswith('_error') or k in ('failure','failure_context','failed_peer_observation') for k in report), 'Incomplete/forced cleanup refused')
    reload = report.get('completed_reload_release')
    require(type(reload) is dict and reload.get('status') == 'RELEASE_PUBLISHED_AFTER_OBSERVED_DWELL'
            and reload.get('release_published') is True, 'Completed reload release evidence required')
    dwell = reload.get('observed_dwell_at_release_seconds')
    require(type(dwell) in (float, int) and math.isfinite(dwell) and 2.0 <= dwell <= 10.0,
            'Completed reload dwell bound required')
    policy = report.get('cpu_probe_policy')
    expected_policy = {'contract':'EXACT_OSHI_PROCESSOR_DISPLAY_V3',
        'jdk_spawn_transition':'SYNCHRONOUS_EXACT_TARGET_REQUIRED', 'maximum_verification_seconds':1,
        'failed':False, 'sampled_observations':True, 'hard_resource_enforcement':False,
        'complete_process_history':False, 'failure':None, 'failure_context':None,
        'maximum_per_role':4, 'maximum_simultaneous_per_role':1, 'maximum_age_seconds':10,
        'maximum_cpu_seconds':2, 'maximum_rss_bytes':67108864}
    exact(policy, (*expected_policy, 'observed'), 'CPU helper contract')
    require(all(type(policy[key]) is type(value) and policy[key] == value
                for key, value in expected_policy.items()) and type(policy['observed']) is list
            and len(policy['observed']) <= 8, 'Successful retained CPU helper policy required')
    helpers, counts = set(), {role:0 for role in ROLES}
    for helper in policy['observed']:
        exact(helper, ('pid','start_ticks','role','observations','terminal_observations','retired_after_stat_race',
                       'age_seconds','cpu_ticks','rss_bytes','high_water_rss_bytes'), 'CPU helper observation')
        require(integer(helper['pid'],1,2**31-1) and integer(helper['start_ticks'],1)
                and helper['role'] in ROLES and integer(helper['observations'],1)
                and integer(helper['terminal_observations'],0) and type(helper['retired_after_stat_race']) is bool
                and type(helper['age_seconds']) in (int,float) and math.isfinite(helper['age_seconds'])
                and 0 <= helper['age_seconds'] <= 10 and integer(helper['cpu_ticks'],0)
                and integer(helper['rss_bytes'],0,67108864) and integer(helper['high_water_rss_bytes'],0,67108864),
                'Invalid or overbound CPU helper observation')
        identity = (helper['pid'], helper['start_ticks'])
        require(identity not in helpers, 'Duplicate CPU helper identity')
        helpers.add(identity); counts[helper['role']] += 1
        require(counts[helper['role']] <= 4, 'Per-role CPU helper count exceeded')
    validate_reload_structure(reload)
    require(report.get('save_acknowledged_after_command') is True and report.get('stop_requested') is True
            and integer(report.get('save_requested_after_line'), 0)
            and sha(report.get('saved_world_level_dat_sha256')), 'Terminal save/stop evidence required')
    for key in ('identities', 'probe', 'log_sha256'):
        exact(report.get(key), ROLES, 'paired '+key)
    require(integer(report.get('nonce'), 1), 'Current transport nonce required')
    require(all(sha(x) for x in report['log_sha256'].values()), 'Current terminal log hashes required')
    for role in ROLES:
        _identity(report['identities'][role])
    game_pids = {row['pid'] for row in report['identities'].values()}
    for helper in policy['observed']:
        require(helper['pid'] not in game_pids
                and helper['start_ticks'] >= report['identities'][helper['role']]['start_ticks'],
                'CPU helper contradicts current owned game identity/start')



def validate_reload_structure(row):
    keys = ('status','gate_started_monotonic','client_result_absent_monotonic',
        'conservative_probe_deadline_monotonic','gate_cutoff_monotonic','maximum_extra_wait_seconds',
        'required_observed_dwell_seconds','probe_deadline_margin_seconds','milestones','reload_start',
        'reload_completed','release_call_started_monotonic','release_call_returned_monotonic',
        'release_published','timing_basis','observed_dwell_seconds','dwell_satisfied_monotonic',
        'observed_dwell_at_release_seconds','extra_wait_before_release_seconds','extra_wait_through_publication_seconds')
    exact(row, keys, 'complete reload evidence')
    numbers = [key for key in keys if key.endswith(('_monotonic', '_seconds'))]
    require(all(type(row[key]) in (int,float) and math.isfinite(row[key]) and row[key] >= 0
                for key in numbers), 'Nonfinite/negative reload timing')
    require(row['client_result_absent_monotonic'] <= row['gate_started_monotonic']
            <= row['dwell_satisfied_monotonic'] <= row['release_call_started_monotonic']
            <= row['release_call_returned_monotonic'] < row['gate_cutoff_monotonic'],
            'Reload timing/order contradiction')
    for key in ('reload_start','reload_completed'):
        milestone = row[key]
        exact(milestone, ('milestone','line','raw_line','log_timestamp','observed_monotonic'), 'reload milestone')
        require(milestone['milestone'] == key and integer(milestone['line'],1)
                and type(milestone['raw_line']) is str and len(milestone['raw_line']) <= MAX_LINE
                and type(milestone['log_timestamp']) is str
                and type(milestone['observed_monotonic']) in (float,int)
                and math.isfinite(milestone['observed_monotonic']) and milestone['observed_monotonic'] >= 0,
                'Invalid typed reload milestone')
    require(row['milestones'] == [row['reload_start'],row['reload_completed']], 'Wrong reload milestone inventory')


def validate_reload_stdout(row, lines, events, module):
    validate_reload_structure(row)
    start, complete = row['reload_start'], row['reload_completed']
    require(1 <= start['line'] < complete['line'] <= len(lines)
            and complete['line'] < events['NETWORK_CONTROL_DISCONNECTED'][0]+1,
            'Reload milestones must precede current disconnect')
    recognized = []
    for index, line in enumerate(lines[:events['NETWORK_CONTROL_DISCONNECTED'][0]]):
        match = module.CompletedReloadGate.EMI_LINE.fullmatch(line)
        if match is not None and (match.group(2) == 'Starting EMI reload...'
                or re.fullmatch(r'Reloaded EMI in [0-9]+ms', match.group(2))):
            recognized.append(index+1)
    require(recognized == [start['line'], complete['line']],
            'Extra reload start/completion before current disconnect')
    # A normal EMI disconnect line after release is not itself a reload event.
    times = [0.0] * complete['line']
    for milestone in (start, complete):
        require(lines[milestone['line']-1] == milestone['raw_line'], 'Reload milestone differs from current stdout')
        times[milestone['line']-1] = milestone['observed_monotonic']
    gate = module.CompletedReloadGate(row['gate_started_monotonic'],
        row['client_result_absent_monotonic'], row['gate_cutoff_monotonic'])
    gate.observe(types.SimpleNamespace(lines=lines[:complete['line']], line_observed_monotonic=times))
    require(gate.ready(row['dwell_satisfied_monotonic'], True), 'Reload dwell was never satisfied')
    gate.before_release(row['release_call_started_monotonic'], True)
    gate.after_release(row['release_call_returned_monotonic'])
    require(gate.report == row, 'Reload report contradicts original gate timing/milestones')


def validate_socket_observations(report, module):
    observations = report.get('observations')
    require(type(observations) is list and 4 <= len(observations) <= 10000,
            'Continuous sampled socket observations required')
    phases = [row.get('phase') if type(row) is dict else None for row in observations]
    require(phases[:2] == ['before_client','after_matching_reply'] and phases[-1] == 'after_client_exit'
            and all(phase == 'during_completed_reload_dwell' for phase in phases[2:-1]),
            'Wrong transport/dwell observation sequence')
    listener_identity, peer_identity = None, None
    for index, observation in enumerate(observations):
        exact(observation, ('listener','owned','connected','tableSha256','phase'), 'socket observation')
        expected_connected = 0 < index < len(observations)-1
        require(observation['connected'] is expected_connected, 'Missing continuous paired connection observation')
        exact(observation['tableSha256'], ('tcp','tcp6','udp','udp6'), 'socket table digest inventory')
        require(all(sha(value) for value in observation['tableSha256'].values()), 'Invalid socket table digest')
        owned = observation['owned']
        require(type(owned) is list and 1 <= len(owned) <= 16, 'Owned socket inventory bound')
        tables = {key:'header\n' for key in ('tcp','tcp6','udp','udp6')}
        inodes = set()
        for socket in owned:
            exact(socket, ('protocol','local','remote','state','inode','role'), 'owned socket row')
            protocol = socket['protocol']
            require(protocol in tables and socket['role'] in ROLES
                    and type(socket['inode']) is str and re.fullmatch(r'[1-9][0-9]{0,19}',socket['inode'])
                    and socket['inode'] not in inodes and type(socket['state']) is str
                    and re.fullmatch(r'[0-9A-F]{2}',socket['state']), 'Invalid owned socket identity')
            inodes.add(socket['inode'])
            address = r'[0-9A-F]{32}:[0-9A-F]{4}' if protocol.endswith('6') else r'[0-9A-F]{8}:[0-9A-F]{4}'
            require(all(type(socket[key]) is str and re.fullmatch(address,socket[key]) for key in ('local','remote')),
                    'Malformed socket endpoint')
            tables[protocol] += '0: '+socket['local']+' '+socket['remote']+' '+socket['state']+' 0 0 0 0 0 '+socket['inode']+'\n'
        listener = module.verify_listeners(tables,inodes,25632)
        require(observation['listener'] == listener and listener['owned'] is True
                and type(observation['listener']['port']) is int, 'Listener does not match owned socket evidence')
        require(any(sock['role']=='server' and sock['inode']==listener['inode'] for sock in owned), 'Listener not server owned')
        if listener_identity is None:listener_identity = listener
        require(listener == listener_identity, 'Listener changed across current pair/dwell')
        if expected_connected:
            connections = [sock for sock in owned if sock['role']=='server' and sock['protocol']=='tcp'
                and sock['state']=='01' and sock['local']=='0100007F:6420' and sock['remote'].startswith('0100007F:')]
            require(len(connections)==1, 'Missing exact established server loopback peer')
            connection=connections[0]
            peers=[sock for sock in owned if sock['role']=='client' and sock['protocol']=='tcp'
                   and sock['state']=='01' and sock['local']==connection['remote'] and sock['remote']==connection['local']]
            require(len(peers)==1, 'Missing matching client loopback peer')
            if peer_identity is None:peer_identity=(connection,peers[0])
            require((connection,peers[0])==peer_identity, 'Peer identity changed during sampled dwell')
        else:
            require(not any(sock['role']=='client' for sock in owned), 'Unexpected client in unpaired observation')

def validate_phase(root, *, phase, spec_pin, report_pin, fixture, reviewed, supervisor_path,
                   runner=None, synthetic_fixture=False):
    """Validate live terminal files before another phase mutates the world/control files.

    For real reopen, runner is independently reviewed derivative provenance, not
    a replacement for the pinned original supervisor. This API cannot admit it.
    """
    require(phase in ('create', 'reopen') and type(synthetic_fixture) is bool, 'Exact lifecycle phase required')
    evidence = Evidence(root)
    fixture_gate(evidence, fixture, reviewed, synthetic_fixture=synthetic_fixture)
    spec, report = evidence.json(spec_pin), evidence.json(report_pin)
    _transport(report, spec, spec_pin)
    require(spec.get('synthetic_fixture', False) is synthetic_fixture
            and report.get('synthetic_fixture', False) is synthetic_fixture, 'Synthetic phase evidence mode mismatch')
    module, supervisor_pin = load_supervisor(supervisor_path)
    runner_pin = None
    if phase == 'reopen':
        owner, continuation, create_result = continuation_gate(evidence, runner=runner,
            spec_pin=spec_pin, report=report, report_pin=report_pin, fixture=fixture, reviewed=reviewed,
            supervisor_path=supervisor_path, synthetic_fixture=synthetic_fixture)
        runner_pin = runner['derivative_source']
    else:
        require(runner is None and 'continuation_owner' not in report, 'Create must retain original supervisor identity')
    require(type(spec.get('inputs')) is list and 1 <= len(spec['inputs']) <= 100000, 'Sealed input inventory required')
    host_graphics_inputs = _track_graphics_inputs(evidence,spec,supervisor_path)
    host_graphics_paths = {row['path'] for row in host_graphics_inputs}
    pins = {}
    for row in spec['inputs']:
        exact(row, ('path', 'bytes', 'sha256'), 'sealed input pin')
        require(type(row['path']) is str and integer(row['bytes'], 1) and sha(row['sha256']), 'Invalid sealed input identity')
        canonical_path(row['path'], None if row['path'] in host_graphics_paths else evidence.root)
        require(row['path'] not in pins, 'Duplicate sealed input pin')
        pins[row['path']] = row
    for row in fixture.values():
        require(pins.get(row['path']) == row, 'Fixture compile/source proof not sealed')
    require(spec.get('probe_path') != fixture['artifact']['path']
            and Path(spec.get('probe_path', '')).name != ARTIFACT_NAME, 'QSL fixture cannot replace transport probe')
    transport_path = canonical_path(spec.get('probe_path'), evidence.root)
    require(str(transport_path) in pins, 'Global transport artifact must be sealed')
    transport_pin = pins[str(transport_path)]
    evidence.read(transport_pin, 64*1024*1024)
    validate_socket_observations(report, module)
    destination = canonical_path(report_pin['path'], evidence.root).parent
    result, role_paths = {}, {}
    for role in ROLES:
        role_spec = spec.get(role)
        require(type(role_spec) is dict, 'Missing sealed role')
        profile = canonical_path(role_spec.get('cwd'), evidence.root)
        role_paths[role] = profile
        command = role_spec.get('command')
        require(type(command) is list and all(type(v) is str for v in command), 'Invalid sealed role command')
        require(command and Path(command[0]).name == 'java' and command[0] in pins,
                'Direct sealed Java executable required')
        canonical_path(command[0], evidence.root)
        evidence.read(pins[command[0]], 64*1024*1024)
        transport_copy = profile/'mods'/transport_path.name
        expected_transport = dict(transport_pin, path=str(transport_copy))
        require(pins.get(str(transport_copy)) == expected_transport, 'Both-role transport artifact must match sealed source')
        evidence.read(expected_transport, 64*1024*1024)
        phase_flags = [v for v in command if v.startswith('-Dunified.quiltProbe.phase=')]
        require(len(command) >= 2 and command[1] == '-Dunified.quiltProbe.phase='+phase
                and phase_flags == ['-Dunified.quiltProbe.phase='+phase]
                and len([v for v in command if v.startswith('-Dunified.quiltProbe.phase')]) == 1, 'Exact current QSL phase flag required')
        copy = profile/'mods'/ARTIFACT_NAME
        expected = dict(fixture['artifact'], path=str(copy))
        mods = role_spec.get('managed_mods')
        require(type(mods) is list and mods.count(str(copy)) == 1 and pins.get(str(copy)) == expected,
                'Both-role additive QSL fixture must be sealed')
        evidence.read(expected, 4*1024*1024)
        identity = report['identities'][role]
        _identity(identity)
        module.validate_probe(report['probe'][role], role, identity, report['nonce'], 25632)
        started_data, _ = evidence.capture(destination/(role+'-started.json'), 16384)
        started = decode(started_data)
        exact(started, ('role', 'identity'), 'started role receipt')
        require(started == {'role': role, 'identity': identity}, 'Current started identity mismatch')
        result_data, _ = evidence.capture(profile/('network-control-'+role+'-result.json'), 2048)
        probe = decode(result_data)
        module.validate_probe(probe, role, identity, report['nonce'], 25632)
        require(probe == report['probe'][role], 'Current result file/report mismatch')
        log_data, log_pin = evidence.capture(destination/(role+'.log'), MAX_LOG, report['log_sha256'][role])
        markers, events, lines = lifecycle_log(log_data, role=role, phase=phase,
                                             fixture_path=copy, fixture_sha=expected['sha256'])
        expected_events = ('NETWORK_CONTROL_READY', 'NETWORK_CONTROL_JSON') if role == 'server' else ('NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_DISCONNECTED')
        require(list(events) == list(expected_events), 'Wrong transport event count/order/role')
        module.validate_probe(events['NETWORK_CONTROL_JSON'][1], role, identity, report['nonce'], 25632)
        require(events['NETWORK_CONTROL_JSON'][1] == probe, 'Transport stdout/result mismatch')
        if role == 'server':
            module.validate_ready(events['NETWORK_CONTROL_READY'][1], identity, 25632)
            offset = report['save_requested_after_line']
            require(offset >= markers['markers'][7]['line'] and offset < len(lines), 'Save preceded actual QSL ready_to_save')
            tail = lines[offset:]
            saved_start = next((i for i, line in enumerate(tail) if 'Saving the game' in line), None)
            require(saved_start is not None and any('Saved the game' in line or 'Saved the world' in line for line in tail[saved_start+1:])
                    and any('All dimensions are saved' in line for line in tail), 'Current save acknowledgments missing from stdout')
            saved_ack = next(i for i, line in enumerate(tail) if i > saved_start
                             and ('Saved the game' in line or 'Saved the world' in line))
            require(markers['markers'][8]['line'] > offset + saved_ack + 1, 'STOPPED preceded save acknowledgment')
            require(offset > events['NETWORK_CONTROL_JSON'][0], 'Save preceded matching transport reply')
        else:
            module.validate_disconnect(events['NETWORK_CONTROL_DISCONNECTED'][1], identity, report['nonce'])
            validate_reload_stdout(report['completed_reload_release'], lines, events, module)
        result[role] = dict(markers, identity=identity, log=log_pin)
    require(role_paths['server'] != role_paths['client']
            and report['identities']['server']['pid'] != report['identities']['client']['pid'], 'Distinct current roles required')
    world = role_paths['server']/'world'
    saved, saved_pin = evidence.capture(world/'data/unified_quilt_probe.dat', MAX_NBT)
    parsed = saved_data(saved)
    _, level_pin = evidence.capture(world/'level.dat', MAX_LOG, report['saved_world_level_dat_sha256'])
    if phase == 'reopen':
        require(report['nonce'] != create_result['nonce'], 'Reopen must use a fresh transport nonce')
        old = [row['identity'] for row in create_result['roles'].values()]
        require(all((value['pid'], value['start_ticks']) != (prior['pid'], prior['start_ticks'])
                    and value['start_ticks'] > prior['start_ticks']
                    for value in report['identities'].values() for prior in old), 'Stale or nonserial role identities')
        owner.verify_world(root, continuation['source_world'],
                           evidence.json(continuation['world_inventory']))
    rows = evidence.finish()
    require(pin(supervisor_path, 1024*1024) == supervisor_pin, 'Original supervisor changed during qualification')
    return {'schema': 'quilt-qsl-lifecycle-phase-v1',
            'status': 'SYNTHETIC_PHASE_EVIDENCE_VALIDATED' if synthetic_fixture else 'QSL_PHASE_EVIDENCE_VALIDATED',
            'synthetic_fixture': synthetic_fixture, 'phase': phase, 'diagnostic_only': True,
            'baseline_acceptance': False, 'runtime_admission': False, 'qsl_networking_acceptance': False,
            'full_api_compatibility': False, 'target': 'unified', 'nonce': report['nonce'],
            'transport_origin': 'original-supervisor' if phase == 'create' else 'reviewed-continuation-derivative',
            'supervisor_source': supervisor_pin, 'continuation_source': runner_pin,
            'spec': spec_pin, 'report': report_pin, 'fixture': fixture, 'roles': result,
            'host_graphics_inputs':host_graphics_inputs,
            'world': {'path': str(world), 'saved_data': saved_pin, 'level_dat': level_pin, 'parsed': parsed},
            'evidence': rows}


def continuation_gate(evidence, *, runner, spec_pin, report, report_pin, fixture, reviewed,
                      supervisor_path, synthetic_fixture):
    """Read-only post-run provenance check. Never re-admit or execute a reopen."""
    exact(runner, ('owner_source', 'derivative_source', 'continuation_receipt',
                   'reviewed_owner_sources'), 'independent continuation source pins')
    expected = runner['reviewed_owner_sources']
    exact(expected, ('original_supervisor_sha256', 'derivative_run_sha256',
                     'owner_source_sha256'), 'reviewed owner source identity')
    require(all(sha(value) for value in expected.values())
            and expected['original_supervisor_sha256'] == SUPERVISOR_SHA256
            and runner['owner_source']['sha256'] == expected['owner_source_sha256']
            and runner['derivative_source']['sha256'] == expected['derivative_run_sha256'],
            'Continuation independently reviewed identity mismatch')
    owner_path = canonical_path(runner['owner_source']['path'], evidence.root)
    require(owner_path.name == 'quilt_continuation.py'
            and runner['derivative_source']['path'] == str(owner_path.with_name('owned_pair_run.py')),
            'Exact owner/derivative source paths required')
    payload = evidence.read(runner['owner_source'], 1024*1024)
    evidence.read(runner['derivative_source'], 1024*1024)
    owner = types.ModuleType('qsl_reviewed_postrun_owner')
    owner.__file__ = str(owner_path)
    exec(compile(payload, str(owner_path), 'exec'), owner.__dict__)
    _, actual_sources = owner.source_identity(supervisor_path)
    require(actual_sources == expected, 'Reviewed derivative AST/source identity mismatch')
    receipt = evidence.json(runner['continuation_receipt'])
    exact(receipt, ('schema', 'diagnostic_only', 'baseline_acceptance', 'qsl_network_acceptance',
                   'phase', 'create_spec', 'create_report', 'reopen_spec', 'fixture', 'reviewed',
                   'qualifier_source', 'owner_sources', 'source_world', 'destination_world',
                   'create_qualification', 'world_inventory'), 'continuation receipt')
    reject_acceptance_claims(receipt)
    require(receipt['schema'] == 'quilt-owned-world-continuation-v1'
            and receipt['phase'] == 'reopen' and receipt['diagnostic_only'] is True
            and receipt['baseline_acceptance'] is False and receipt['qsl_network_acceptance'] is False
            and receipt['owner_sources'] == expected and receipt['reopen_spec'] == spec_pin
            and receipt['fixture'] == fixture and receipt['reviewed'] == reviewed,
            'Continuation scope/build/spec mismatch')
    require(report.get('continuation_owner') == dict(expected, schema='quilt-lifecycle-continuation-owner-v1',
            phase='reopen', continuation_receipt=runner['continuation_receipt']),
            'Reopen terminal report lacks exact derivative owner binding')
    prelaunch_pin = report.get('continuation_prelaunch')
    require(type(prelaunch_pin) is dict and prelaunch_pin.get('path') ==
            str(Path(report_pin['path']).parent/'world-prelaunch.json'), 'Missing exact prelaunch checkpoint pin')
    prelaunch = evidence.json(prelaunch_pin)
    require(prelaunch == {'schema':'quilt-world-prelaunch-v1', 'phase':'reopen',
            'continuation_receipt':runner['continuation_receipt'], 'source_world':receipt['source_world'],
            'destination_world':receipt['destination_world'], 'world_inventory':receipt['world_inventory'],
            'create_spec':receipt['create_spec'], 'create_report':receipt['create_report'],
            'reopen_spec':spec_pin, 'checked_under_serial_lock':True, 'game_spawned_at_check':False},
            'Prelaunch inventory/serial-lock/phase binding mismatch')
    require(prelaunch.get('checked_under_serial_lock') is True and prelaunch.get('game_spawned_at_check') is False,
            'Typed prelaunch sequencing evidence required')
    require(Path(receipt['create_report']['path']).parent != Path(report_pin['path']).parent,
            'Reopen cannot reuse create capture destination')
    current_qualifier = pin(Path(__file__).resolve(), 1024*1024)
    evidence.read(receipt['qualifier_source'], 1024*1024)
    require(receipt['qualifier_source']['sha256'] == current_qualifier['sha256'],
            'Stale create qualifier source refused')
    create_spec = evidence.json(receipt['create_spec'])
    reopen_spec = evidence.json(spec_pin)
    owner.check_phase_specs(evidence.root, create_spec, reopen_spec)
    require(receipt['source_world'] == str(Path(create_spec['server']['cwd'])/'world')
            and receipt['destination_world'] == str(Path(reopen_spec['server']['cwd'])/'world'),
            'World lineage not bound to exact fresh roles')
    actual_create = validate_phase(evidence.root, phase='create', spec_pin=receipt['create_spec'],
        report_pin=receipt['create_report'], fixture=fixture, reviewed=reviewed,
        supervisor_path=supervisor_path, synthetic_fixture=synthetic_fixture)
    require(evidence.json(receipt['create_qualification']) == actual_create,
            'Retained create checkpoint differs from current evidence')
    inventory = evidence.json(receipt['world_inventory'])
    owner.verify_world(evidence.root, receipt['source_world'], inventory)
    evidence.final_checks.append(lambda: owner.verify_world(evidence.root, receipt['source_world'], inventory))
    # The independently reviewed derivative rechecks the destination against this
    # complete inventory under its serial lock immediately before the server spawn.
    # Post-run destination bytes are intentionally NOT required to equal pre-run.
    files = {row['path']: row for row in inventory['files']}
    for key, relative in (('saved_data', 'data/unified_quilt_probe.dat'), ('level_dat', 'level.dat')):
        require(files.get(relative) == dict(actual_create['world'][key], path=relative),
                'Create SavedData/level hash absent from complete inventory')
    for row in actual_create['evidence']:
        # Register retained create evidence for another end-of-validation check.
        evidence.read(row, max(MAX_JSON, row['bytes']))
    _track_graphics_inputs(evidence,create_spec,supervisor_path,expected=actual_create['host_graphics_inputs'])
    return owner, receipt, actual_create


def validate_pair(root, *, create_spec_pin, create_report_pin, reopen_spec_pin, reopen_report_pin,
                  fixture, reviewed, supervisor_path, runner, synthetic_fixture=False):
    """Qualify exactly one retained create plus fresh-profile authenticated reopen."""
    evidence = Evidence(root)
    receipt = evidence.json(runner['continuation_receipt'])
    require(receipt.get('create_spec') == create_spec_pin and receipt.get('create_report') == create_report_pin
            and receipt.get('reopen_spec') == reopen_spec_pin, 'Pair/continuation receipt mismatch')
    require(len({row['path'] for row in (create_spec_pin, create_report_pin, reopen_spec_pin, reopen_report_pin)}) == 4,
            'Separate phase specs/reports required')
    require(Path(create_report_pin['path']).parent != Path(reopen_report_pin['path']).parent,
            'Fresh phase capture directories required')
    create = validate_phase(root, phase='create', spec_pin=create_spec_pin, report_pin=create_report_pin,
        fixture=fixture, reviewed=reviewed, supervisor_path=supervisor_path, synthetic_fixture=synthetic_fixture)
    reopen = validate_phase(root, phase='reopen', spec_pin=reopen_spec_pin, report_pin=reopen_report_pin,
        fixture=fixture, reviewed=reviewed, supervisor_path=supervisor_path, runner=runner, synthetic_fixture=synthetic_fixture)
    for result in (create, reopen):
        for row in result['evidence']:
            evidence.read(row, max(MAX_JSON, row['bytes']))
        phase_spec = evidence.json(result['spec'])
        _track_graphics_inputs(evidence,phase_spec,supervisor_path,expected=result['host_graphics_inputs'])
    owner_raw = evidence.read(runner['owner_source'], 1024*1024)
    owner = types.ModuleType('qsl_pair_final_inventory_check')
    owner.__file__ = runner['owner_source']['path']
    exec(compile(owner_raw, owner.__file__, 'exec'), owner.__dict__)
    inventory = evidence.json(receipt['world_inventory'])
    evidence.final_checks.append(lambda: owner.verify_world(root, receipt['source_world'], inventory))
    return {'schema':'quilt-qsl-lifecycle-persistence-v1',
            'status':'SYNTHETIC_TWO_PHASE_EVIDENCE_VALIDATED' if synthetic_fixture else 'QSL_LIFECYCLE_PERSISTENCE_EVIDENCE_VALIDATED',
            'synthetic_fixture':synthetic_fixture, 'diagnostic_only':True,'baseline_acceptance':False,
            'runtime_admission':False,'qsl_networking_acceptance':False,'full_api_compatibility':False,
            'create':create,'reopen':reopen,'world_lineage':{'source':receipt['source_world'],
                'destination':receipt['destination_world'],'inventory':receipt['world_inventory'],
                'continuation_receipt':runner['continuation_receipt']},
            'evidence':evidence.finish()}
