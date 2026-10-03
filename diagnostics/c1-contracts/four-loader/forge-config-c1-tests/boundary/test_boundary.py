#!/usr/bin/env python3
"""Deterministic standard-library static tests; no JVM, Gradle or game."""
from __future__ import annotations
import csv
import io
import json
import re
import sys
import unittest
import zipfile

sys.dont_write_bytecode = True
from c1_boundary import (HERE, ROOT, FORGE, ReferenceGate, baseline_member_keys,
                         key, load_proposal, read_official_classes, resolve_member, sha)

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = load_proposal()
        cls.classes = read_official_classes(cls.proposal)
        cls.gate = ReferenceGate(cls.proposal)
        with (ROOT/'docs/api-coverage/forge-config/member-shapes.csv').open() as stream:
            cls.ledger = list(csv.DictReader(stream))

    def test_proposal_remains_review_only_and_exact(self):
        p = self.proposal
        self.assertEqual(p['status'],'proposal-only')
        self.assertFalse(p['production_admitted'])
        self.assertEqual((len(p['types']),len(p['methods']),len(p['fields'])),(10,28,1))
        all_symbols = p['methods']+p['fields']
        self.assertEqual(len({key(s) for s in all_symbols}),len(all_symbols))
        for s in all_symbols:
            self.assertNotIn('*',s['owner']+s['name']+s['descriptor'])
            sep = ':' if s['kind'] == 'field' else ''
            self.assertEqual(s['transformer_key'],s['owner'][len(FORGE):]+'.'+s['name']+sep+s['descriptor'])
        self.assertTrue(self.gate.additions.isdisjoint(self.gate.baseline))

    def test_pinned_inputs_match(self):
        for item in self.proposal['pinned_inputs']:
            with self.subTest(path=item['path']):
                self.assertEqual(sha(ROOT/item['path']),item['sha256'])
        p = self.proposal['api1_source_baseline']
        self.assertEqual(sha(ROOT/p['path']),p['sha256'])
        with zipfile.ZipFile(ROOT/p['path']) as archive:
            self.assertEqual(archive.read(p['transformer_member']),(ROOT/p['transformer_member']).read_bytes())

    def test_reference_sources_match_official_archives(self):
        provenance = json.loads((ROOT/'docs/api-coverage/forge-config/provenance.json').read_text())
        pinned_sources = {p['path'] for p in self.proposal['pinned_inputs'] if '/sources/net/minecraftforge/' in p['path']}
        validated = set()
        for item in provenance['files']:
            if item['path'] not in pinned_sources: continue
            self.assertEqual(sha(ROOT/item['archive']),item['archive_sha256'])
            with zipfile.ZipFile(ROOT/item['archive']) as archive:
                self.assertEqual(archive.read(item['member']),(ROOT/item['path']).read_bytes())
            validated.add(item['path'])
        self.assertEqual(validated,pinned_sources)

    def test_every_proposed_symbol_resolves_exactly_in_official_forge(self):
        for item in self.proposal['methods']+self.proposal['fields']:
            with self.subTest(symbol=item['transformer_key']):
                found = resolve_member(self.classes,item['owner'],item['kind'],item['name'],item['descriptor'])
                self.assertIsNotNone(found)
                declared, member = found
                self.assertTrue(member['access'] & 0x0001)
                if item['kind'] == 'method':
                    self.assertEqual(declared,item['declaration_owner'])
                    expected = 'declared' if declared == item['owner'] else 'inherited-alias'
                    self.assertEqual(item['resolution'],expected)
                else:
                    self.assertTrue(member['access'] & 0x0008)
                    self.assertTrue(member['access'] & 0x4000)

    def test_allowlisted_declarations_agree_with_member_shapes(self):
        ledger = {(r['kind'],r['forge_owner'],r['name'],r['forge_descriptor']):r for r in self.ledger}
        checked = 0
        for s in self.proposal['methods']+self.proposal['fields']:
            declaration = (s['kind'],s.get('declaration_owner',s['owner']),s['name'],s['descriptor'])
            if declaration in ledger:
                self.assertEqual(ledger[declaration]['forge_visibility'],'public')
                self.assertEqual(ledger[declaration]['admitted'],'False')
                checked += 1
            else:
                self.assertIn(declaration[1],(FORGE+'fml/ModLoadingContext',FORGE+'fml/event/config/ModConfigEvent'))
        self.assertEqual(checked,25)
        self.assertTrue(all(r['admitted']=='False' for r in self.ledger))

    def test_erased_values_and_required_inherited_aliases(self):
        c = FORGE+'common/ForgeConfigSpec'
        for suffix in ('$BooleanValue','$IntValue','$ConfigValue'):
            for name,desc in [('get','()Ljava/lang/Object;'),('set','(Ljava/lang/Object;)V')]:
                self.assertIn(('method',c+suffix,name,desc),self.gate.additions)
        self.assertIn(('method',c+'$IntValue','save','()V'),self.gate.additions)
        value = self.classes[c+'$ConfigValue']
        self.assertIn('Ljava/util/function/Supplier<TT;>;',value['signature'])
        for suffix in ('$BooleanValue','$IntValue'):
            self.assertEqual(self.classes[c+suffix]['super'],c+'$ConfigValue')
            self.assertFalse(any(m['name'] in ('get','set','save') for m in self.classes[c+suffix]['members']))

    def test_context_and_event_aliases_resolve_without_admitting_base_owners(self):
        base = FORGE+'fml/ModLoadingContext'
        context = FORGE+'fml/javafmlmod/FMLJavaModLoadingContext'
        event = FORGE+'fml/event/config/ModConfigEvent'
        self.assertEqual(self.classes[context]['super'],base)
        for suffix in ('$Loading','$Reloading'):
            self.assertEqual(self.classes[event+suffix]['super'],event)
        owners = {s['owner'] for s in self.proposal['methods']}
        for omitted in (base,event,FORGE+'fml/config/IConfigEvent'):
            self.assertNotIn(omitted,owners)
            self.assertNotIn(omitted,{t['owner'] for t in self.proposal['types']})

    def test_common_is_only_admitted_field_and_no_enum_methods(self):
        fields = self.proposal['fields']
        self.assertEqual([(s['owner'],s['name'],s['descriptor']) for s in fields],[(FORGE+'fml/config/ModConfig$Type','COMMON','Lnet/minecraftforge/fml/config/ModConfig$Type;')])
        self.assertFalse(any(s['owner']==FORGE+'fml/config/ModConfig$Type' for s in self.proposal['methods']))
        self.assertFalse(any(s['owner']==FORGE+'fml/config/IConfigSpec' for s in self.proposal['methods']))

    def test_negative_symbols_are_denied_and_official_shapes_are_real(self):
        self.assertEqual(len(self.proposal['negative_symbols']),34)
        for s in self.proposal['negative_symbols']:
            with self.subTest(symbol=s['transformer_key']):
                self.assertFalse(self.gate.accepts_symbol(s))
                found = resolve_member(self.classes,s['owner'],s['kind'],s['name'],s['descriptor'])
                if s['evidence']=='official-member':
                    self.assertIsNotNone(found)
                else:
                    self.assertIsNone(found)

    def test_every_other_config_declaration_stays_denied(self):
        accepted, denied = 0, 0
        for r in self.ledger:
            s = {'kind':r['kind'],'owner':r['forge_owner'],'name':r['name'],'descriptor':r['forge_descriptor']}
            if self.gate.accepts_symbol(s): accepted += 1
            else: denied += 1
            if r['forge_visibility']=='protected':
                self.assertFalse(self.gate.accepts_symbol(s))
        self.assertEqual((accepted,denied),(20,164))

    def test_custom_specs_and_forge_subclasses_remain_blocked(self):
        for header in self.proposal['class_policy']['synthetic_negative_headers']:
            with self.subTest(header=header):
                self.assertIsNotNone(self.gate.rejects_header(header))
        self.assertIsNotNone(self.gate.rejects_header({'name':FORGE+'config/Evil','super':'java/lang/Object','interfaces':[]}))
        self.assertIsNone(self.gate.rejects_header({'name':'infinity/probe/OwnEvent','super':FORGE+'eventbus/api/Event','interfaces':[]}))

    def test_frozen_transformer_preserves_exact_default_deny(self):
        p = self.proposal['api1_source_baseline']
        with zipfile.ZipFile(ROOT/p['path']) as archive: text = archive.read(p['transformer_member']).decode()
        for source in ('if (!METHODS.contains(symbol)) throw unsupported(',
                       'if (!FIELDS.contains(symbol)) throw unsupported(',
                       'if (mapped == null) throw unsupported(',
                       'reader.getSuperName().startsWith(F) && !reader.getSuperName().equals(EVENT)',
                       'for (String iface : reader.getInterfaces()) if (iface.startsWith(F))',
                       'omit Forge InnerClasses metadata; reject other API subclasses, interfaces and reflective strings'):
            self.assertIn(source,text)
        for symbol in self.proposal['methods']+self.proposal['fields']:
            self.assertNotIn(symbol['transformer_key'],text)

if __name__ == '__main__':
    capture = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests)
    result = unittest.TextTestRunner(stream=capture,verbosity=2).run(suite)
    report = {'status':'passed' if result.wasSuccessful() else 'failed','scope':'static proposal and official declarations only',
              'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
              'jvm_started':False,'gradle_started':False,'game_started':False,'production_transformer_executed':False,
              'output':re.sub(r'Ran (\d+) tests in [0-9.]+s', r'Ran \1 tests (elapsed time omitted)', capture.getvalue())}
    print(json.dumps(report,indent=2,sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
