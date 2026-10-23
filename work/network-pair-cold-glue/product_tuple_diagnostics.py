"""Bounded failure-only tuple evidence. No raw content, paths, or acceptance."""
import hashlib
import json
from pathlib import Path
import stat
import time
import generated_output_diagnostics as safe

MAX_REPORT = 64 * 1024
BASELINE = 'work/network-pair-cold-glue/profiles/product-diagnostic-baseline.json'
SELECTED = {'META-INF/MANIFEST.MF', 'META-INF/neoforge.mods.toml',
            'META-INF/unified-infinity/bundled-qsl.json', 'META-INF/jarjar/metadata.json'}


def _read(root, relative, budget, limit):
    safe._check(budget)
    path = safe._safe(root, root / relative)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise safe.Limited('NOT_REGULAR_FILE')
    if info.st_size > limit:
        raise safe.Limited('FILE_SIZE_LIMIT')
    with path.open('rb') as source:
        count, digest = safe._hash(source, budget, limit)
        source.seek(0)
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise safe.Limited('FILE_SIZE_LIMIT')
    return raw, count, digest


def emit(consumer, profile, artifacts, receipts, deadline):
    root = Path(consumer).absolute()
    budget = [min(deadline, time.monotonic() + 20), safe.MAX_HASH_WORK]
    report = {'schema':1, 'diagnosticOnly':True, 'runtimeAcceptance':False,
              'complete':True, 'outputs':[], 'receipts':[],
              'metadataOnlyDifferenceConclusion':'UNAVAILABLE'}
    baseline = None
    try:
        raw, _, _ = _read(root, BASELINE, budget, 64 * 1024)
        baseline = json.loads(raw)
        if baseline['tupleHashes'] != profile['observedOutputReference'] or baseline['sha256'] != profile['observedOutputReference']['product']:
            raise safe.Limited('BASELINE_REFERENCE_MISMATCH')
    except Exception as error:
        baseline = None
        report.update(complete=False, baselineStatus=type(error).__name__)
    paths = []
    # All whole-file identities precede optional expanded ZIP work.
    for role in ('service','game','fml','product'):
        row = {'role':role, 'expectedSha256':profile['observedOutputReference'][role],
               'expectedBytes':baseline['tupleBytes'][role] if baseline else None,
               'expectedBytesScope':'OBSERVED_REFERENCE', 'actualSha256':None, 'actualBytes':None}
        report['outputs'].append(row)
        try:
            safe._check(budget)
            path = safe._safe(root, root / artifacts[role]['path'])
            info = path.stat()
            row['actualBytes'] = info.st_size
            if not stat.S_ISREG(info.st_mode):
                raise safe.Limited('NOT_REGULAR_FILE')
            if info.st_size > safe.MAX_FILE:
                raise safe.Limited('FILE_SIZE_LIMIT')
            with path.open('rb') as source:
                row['actualBytes'], row['actualSha256'] = safe._hash(source,budget,safe.MAX_FILE)
            row['status'] = 'MATCH' if row['actualSha256'] == row['expectedSha256'] else 'HASH_MISMATCH'
            if role == 'product':
                paths.append((path,row))
        except Exception as error:
            row['status'] = str(error) if isinstance(error,safe.Limited) else type(error).__name__
            report['complete'] = False
    for role in ('core','product','fml'):
        row = {'role':role}
        report['receipts'].append(row)
        try:
            raw, count, digest = _read(root, receipts[role]['path'], budget, 1024 * 1024)
            if digest != receipts[role]['sha256'] or count != receipts[role]['bytes']:
                raise safe.Limited('RECEIPT_PIN_MISMATCH')
            receipt = json.loads(raw)
            raw, count, digest = _read(root, receipt['log']['path'], budget, 8 * 1024 * 1024)
            if digest != receipt['log']['sha256'] or count != receipt['log']['bytes']:
                raise safe.Limited('LOG_PIN_MISMATCH')
            import refreshed_candidate
            states = refreshed_candidate.task_states(raw.decode('utf-8',errors='replace'))
            required = profile['requiredTasks'][role]
            row.update(receiptSha256=receipts[role]['sha256'],logSha256=digest,
                       successfulExit=receipt['exitCode']==0,
                       buildSuccessful=b'BUILD SUCCESSFUL' in raw and b'BUILD FAILED' not in raw,
                       requiredTaskCount=len(required),
                       executedRequiredTaskCount=sum(task in states and states[task] not in ('SKIPPED','NO-SOURCE','FAILED') for task in required),
                       observedTaskCount=len(states),inputsUnchanged=receipt['inputsBefore']==receipt['inputsAfter'])
        except Exception as error:
            row['status'] = str(error) if isinstance(error,safe.Limited) else type(error).__name__
            report['complete'] = False
    for path,row in paths:
        try:
            detail = safe._zip(path,budget,False,sample_limit=64)
            expected = {item['name']:item for item in baseline['zip']['samples']} if baseline else {}
            for sample in detail['samples']:
                name = sample.pop('name')
                sample['nameSha256'] = hashlib.sha256(name.encode()).hexdigest()
                if name in expected:
                    sample['name'] = name  # Only verified historical entry names are displayed.
                    sample['expectedPayloadSha256'] = expected[name]['payloadSha256']
                    sample['payloadMatchesReference'] = sample['payloadSha256']==expected[name]['payloadSha256']
                    sample['metadataMatchesReference'] = all(sample.get(key)==value for key,value in expected[name].items() if key not in ('name','payloadSha256'))
                sample['selectedGeneratedMetadata'] = name in SELECTED
            detail['inventoryTruncated'] = detail['entryCount'] > 64
            if baseline:
                detail['referenceAggregates'] = {key:baseline['zip'][key] for key in ('payloadAggregateSha256','entryOrderSha256','zipMetadataSha256','entryCount')}
            row['zip'] = detail
        except Exception as error:
            row['zipStatus'] = str(error) if isinstance(error,safe.Limited) else type(error).__name__
            report['complete'] = False
    if len(safe._json(report).encode()) > MAX_REPORT - 64:
        for row in report['outputs']:
            if 'zip' in row: row['zip'].pop('samples',None)
        report.update(complete=False,optionalDetailsDropped=True)
    marker = 'PRODUCT_TUPLE_DIAGNOSTIC ' + safe._json(report)
    if len((marker+'\n').encode()) > MAX_REPORT:
        marker = 'PRODUCT_TUPLE_DIAGNOSTIC {"complete":false,"error":"REPORT_LIMIT"}'
    print(marker,flush=True)
    return report


def inspect_tuple(consumer, profile, artifacts, receipts, deadline):
    """Keep the exact gate and original exception, even if evidence fails."""
    import refreshed_candidate
    try:
        return refreshed_candidate.inspect_tuple(consumer,profile,artifacts)
    except Exception:
        try:
            emit(consumer,profile,artifacts,receipts,deadline)
        except Exception:
            print('PRODUCT_TUPLE_DIAGNOSTIC {"complete":false,"error":"DIAGNOSTIC_FAILED"}',flush=True)
        raise
