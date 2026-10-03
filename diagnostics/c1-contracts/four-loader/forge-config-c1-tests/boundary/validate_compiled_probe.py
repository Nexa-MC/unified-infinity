#!/usr/bin/env python3
"""Inspect independently compiled official-Forge fixtures; never compile/run.

Usage:
  python3 validate_compiled_probe.py --positive /path/to/official-probe/classes
  python3 validate_compiled_probe.py --positive /path/to/classes --negative /path/to/negative/classes

Outputs a review-only JSON report. This is not evidence of a production
transformer pass, runtime linking, actual IO, owner semantics or a game run.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from c1_boundary import (HERE, FORGE, ReferenceGate, key, load_proposal,
                         member_references, parse_classfile, sha)

PREFIX = 'infinity/probe/forgeconfig/ForgeConfigLifecycleProbe'
NEGATIVE_PACKAGE = 'infinity/probe/forgeconfig/boundary/'

def inspect(path, prefix):
    result = []
    for file in sorted(path.rglob('*.class')):
        data = file.read_bytes(); header = parse_classfile(data)
        if header['name'] != prefix and not header['name'].startswith(prefix+'$') and not prefix.endswith('/'):
            continue
        if prefix.endswith('/') and not header['name'].startswith(prefix): continue
        result.append((file,header,member_references(data)))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--positive',type=Path,required=True)
    parser.add_argument('--negative',type=Path)
    args = parser.parse_args()
    proposal = load_proposal(); gate = ReferenceGate(proposal)
    positives = inspect(args.positive,PREFIX)
    failures = []; emitted = set(); positive_report = []
    if not positives: failures.append('No official-compiled lifecycle probe classes found')
    for file,header,refs in positives:
        rejected = gate.rejected_references(refs)
        header_rejection = gate.rejects_header(header)
        emitted.update(key(ref) for ref in refs if key(ref) in gate.additions)
        positive_report.append({'class':header['name'],'sha256':sha(file),'major':header['major'],
                                'rejected_header':header_rejection,'rejected_symbols':rejected,
                                'forge_member_references':[r for r in refs if r['owner'].startswith(FORGE)]})
        if rejected or header_rejection: failures.append('Positive class rejected: '+header['name'])
    missing = gate.additions-emitted
    if missing: failures.append('Proposed additions not emitted by this independently compiled probe')
    negative_report = []
    if args.negative:
        negatives = inspect(args.negative,NEGATIVE_PACKAGE)
        fixture = (HERE/'fixtures/NegativeConfigInputs.java').read_text()
        expected = {NEGATIVE_PACKAGE+n for n in re.findall(r'^(?:abstract )?class (\w+)',fixture,re.M)}
        observed = {h['name'] for _,h,_ in negatives}
        if observed != expected:
            failures.append('Negative fixture classes differ from source: '+repr(sorted(expected^observed)))
        for file,header,refs in negatives:
            rejected = gate.rejected_references(refs); header_rejection = gate.rejects_header(header)
            negative_report.append({'class':header['name'],'sha256':sha(file),'rejected_header':header_rejection,'rejected_symbols':rejected})
            if not rejected and not header_rejection: failures.append('Negative class was accepted: '+header['name'])
    report = {'status':'passed' if not failures else 'failed',
              'scope':'static official-compiled fixture member references and class headers only',
              'jvm_started':False,'production_transformer_executed':False,
              'independent_compilation_provenance':'Caller must retain official javac command/classpath receipt; not established by classfile parsing',
              'positive_classes':positive_report,'negative_classes':negative_report,
              'proposed_additions_observed':len(emitted),'proposed_additions_total':len(gate.additions),
              'unobserved_proposals':[dict(zip(('kind','owner','name','descriptor'),s)) for s in sorted(missing)],
              'failures':failures}
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if not failures else 1

if __name__ == '__main__': raise SystemExit(main())
