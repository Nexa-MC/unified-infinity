#!/usr/bin/env python3
"""Read-only C1 proposal/reference gate. Never loads classes or starts a JVM.

This models exact symbol admission for review; it is not the production ASM
transformer. The optional compiled-input checker inspects constant-pool member
references and class headers, not reachability, bytecode verification or linking.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'tools/api-coverage'))
from forge_classfile import Reader, parse_classfile  # noqa: E402

FORGE = 'net/minecraftforge/'

def load_proposal():
    return json.loads((HERE/'proposed-allowlist.json').read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def key(item):
    return (item['kind'], item['owner'], item['name'], item['descriptor'])

def read_official_classes(proposal):
    result = {}
    for artifact in proposal['official_binary_archives']:
        path = ROOT/artifact['path']
        if sha(path) != artifact['sha256']:
            raise ValueError('Official archive pin mismatch: '+artifact['path'])
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.startswith(FORGE) and name.endswith('.class'):
                    item = parse_classfile(archive.read(name))
                    if item['name'] in result:
                        raise ValueError('Duplicate official class '+item['name'])
                    result[item['name']] = item
    return result

def resolve_member(classes, owner, kind, name, descriptor, seen=None):
    """Bounded exact inherited resolution; constructors never inherit."""
    seen = set() if seen is None else seen
    if owner in seen or owner not in classes:
        return None
    seen.add(owner)
    item = classes[owner]
    for member in item['members']:
        if (member['kind'],member['name'],member['descriptor']) == (kind,name,descriptor):
            return owner, member
    if name == '<init>':
        return None
    for parent in [item['super'], *item['interfaces']]:
        found = resolve_member(classes,parent,kind,name,descriptor,seen)
        if found:
            return found
    return None

def baseline_member_keys(proposal):
    baseline = proposal['api1_source_baseline']
    path = ROOT/baseline['path']
    if sha(path) != baseline['sha256']:
        raise ValueError('API1 source ZIP pin mismatch')
    with zipfile.ZipFile(path) as archive:
        text = archive.read(baseline['transformer_member']).decode()
    keys = set()
    for section, kind in [('METHODS','method'), ('FIELDS','field')]:
        body = re.search(r'Set<String> '+section+r' = Set\.of\((.*?)\n    \);', text, re.S).group(1)
        for token in re.findall(r'"([^"\n]+)"',body):
            owner, tail = token.split('.',1)
            if kind == 'field':
                name, descriptor = tail.split(':',1)
            else:
                name, descriptor = tail.split('(',1); descriptor = '('+descriptor
            keys.add((kind,FORGE+owner,name,descriptor))
    return keys

class ReferenceGate:
    def __init__(self, proposal):
        self.proposal = proposal
        self.additions = {key(s) for s in proposal['methods']+proposal['fields']}
        self.baseline = baseline_member_keys(proposal)

    def accepts_symbol(self, item):
        return key(item) in self.additions or key(item) in self.baseline

    def rejects_header(self, header):
        if header['name'].startswith(FORGE):
            return 'bundled Forge implementation '+header['name']
        parent = header.get('super')
        if parent and parent.startswith(FORGE) and parent != FORGE+'eventbus/api/Event':
            return 'Forge API subclass '+header['name']+' extends '+parent
        for iface in header.get('interfaces',[]):
            if iface.startswith(FORGE):
                return 'Forge API implementation '+header['name']+' implements '+iface
        return None

    def rejected_references(self, references):
        return [s for s in references if s['owner'].startswith(FORGE) and not self.accepts_symbol(s)]

def member_references(data):
    """Decode CONSTANT_Fieldref/Methodref/InterfaceMethodref without execution.

    Handles refer back to these entries, so method-handle targets are included.
    Unused constant-pool entries are conservatively included. Invokedynamic
    linkage, instruction opcode validity and runtime behavior remain unproven.
    """
    r = Reader(data)
    if r.u4() != 0xCAFEBABE: raise ValueError('not a classfile')
    r.u2(); r.u2()
    count = r.u2(); cp = [None]*count; i = 1
    while i < count:
        tag = r.u1()
        if tag == 1:
            raw = r.take(r.u2()).replace(b'\xc0\x80',b'\x00')
            value = raw.decode('utf-8','surrogatepass')
            cp[i] = (tag,value.encode('utf-16','surrogatepass').decode('utf-16'))
        elif tag in (3,4): cp[i] = (tag,r.take(4))
        elif tag in (5,6): cp[i] = (tag,r.take(8)); i += 1
        elif tag in (7,8,16,19,20): cp[i] = (tag,r.u2())
        elif tag in (9,10,11,12,17,18): cp[i] = (tag,r.u2(),r.u2())
        elif tag == 15: cp[i] = (tag,r.u1(),r.u2())
        else: raise ValueError('unknown constant-pool tag '+str(tag))
        i += 1
    result = []
    for value in cp:
        if value and value[0] in (9,10,11):
            owner = cp[cp[value[1]][1]][1]
            nt = cp[value[2]]
            result.append({'kind':'field' if value[0] == 9 else 'method','owner':owner,
                           'name':cp[nt[1]][1],'descriptor':cp[nt[2]][1],
                           'constant_pool_tag':value[0]})
    return sorted(result,key=key)
