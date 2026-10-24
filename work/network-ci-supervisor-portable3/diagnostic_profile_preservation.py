"""Test-only exact byte reversal of the diagnostic provenance metadata delta.

Each frozen replacement must occur once. Unrelated source mutations remain visible
to predecessor hashes; no AST rewriting or runtime-policy normalization occurs.
"""

PREDECESSOR_SHA256 = '1b489c7cd6db677cb067cc6f3d564c2e813baacaada2b4d583d911953aee7183'

REPLACEMENTS = (
    ('''def diagnostic_report_fields(spec):
    """Label an explicitly selected diagnostic without granting any admission."""
    if 'diagnostic_profile' not in spec:
        return {}
    profile = spec['diagnostic_profile']
    exact_keys(profile, ('manifest_path', 'manifest_sha256', 'diagnostic_only',
                         'baseline_acceptance'), 'diagnostic profile')
    require(profile['diagnostic_only'] is True and profile['baseline_acceptance'] is False,
            'Diagnostic profile must explicitly reject baseline acceptance')
    require(isinstance(profile['manifest_path'], str) and
            1 <= len(profile['manifest_path']) <= 4096, 'Invalid diagnostic manifest path')
    clean_path(profile['manifest_path'])
    require(isinstance(profile['manifest_sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', profile['manifest_sha256']) is not None,
            'Invalid diagnostic manifest digest')
    return {'diagnostic_profile': dict(profile), 'diagnostic_only': True,
            'baseline_acceptance': False}


def verify_diagnostic_profile(spec, pins):
    """Check only provenance; all ordinary file and runtime gates remain required."""
    fields = diagnostic_report_fields(spec)
    if not fields:
        return
    profile = fields['diagnostic_profile']
    row = pins.get(profile['manifest_path'])
    require(row is not None and row['sha256'] == profile['manifest_sha256'],
            'Diagnostic manifest must match an existing sealed input')
    raw = read_bounded(profile['manifest_path'], 16 * 1024)
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Diagnostic manifest changed during verification')
    manifest = decode_json(raw, 16 * 1024)
    exact_keys(manifest, ('schema', 'diagnostic_only', 'baseline_acceptance', 'build_receipts'),
               'diagnostic manifest')
    require(manifest['schema'] == 'fml-process-start-diagnostic-v1' and
            manifest['diagnostic_only'] is True and manifest['baseline_acceptance'] is False,
            'Invalid diagnostic-only manifest')
    receipts = manifest['build_receipts']
    require(isinstance(receipts, list) and len(receipts) == 2,
            'Exactly two diagnostic build receipt pins required')
    seen = set()
    for receipt in receipts:
        exact_keys(receipt, ('path', 'bytes', 'sha256'), 'diagnostic build receipt pin')
        require(isinstance(receipt['path'], str), 'Invalid diagnostic build receipt path')
        require(integer(receipt['bytes'], 1) and isinstance(receipt['sha256'], str) and
                re.fullmatch('[0-9a-f]{64}', receipt['sha256']) is not None,
                'Invalid diagnostic build receipt pin')
        path = str(clean_path(receipt['path']))
        require(path not in seen, 'Duplicate diagnostic build receipt path')
        seen.add(path)
        require(pins.get(path) == receipt, 'Diagnostic build receipt must match a sealed input')


''', ''),
    ('''    if 'diagnostic_profile' in spec:
        keys = (*keys, 'diagnostic_profile')
''', ''),
    ('''    verify_diagnostic_profile(spec, pins)
''', ''),
    ('''        self.report.update(diagnostic_report_fields(spec))
''', ''),
    ('''                          'runtime_evidence_observed': False, 'passed': False,
                          **diagnostic_report_fields(spec)}))
''', "                          'runtime_evidence_observed': False, 'passed': False}))\n"),
    ('''                      'game_launched': report['game_launched'], 'result': str(destination / 'result.json'),
                      **diagnostic_report_fields(spec)}))
''', "                      'game_launched': report['game_launched'], 'result': str(destination / 'result.json')}))\n"),
)


def without_diagnostic_profile(source):
    for reviewed, original in REPLACEMENTS:
        if source.count(reviewed) != 1:
            raise ValueError('Changed, missing or duplicate diagnostic-profile metadata block')
        source = source.replace(reviewed, original, 1)
    return source
