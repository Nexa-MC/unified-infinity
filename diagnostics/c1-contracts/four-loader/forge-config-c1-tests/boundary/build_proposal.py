#!/usr/bin/env python3
"""Build the review-only proposal; reads pinned inputs and writes only here."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
F = 'net/minecraftforge/'
C = F + 'common/ForgeConfigSpec'
M = F + 'fml/config/ModConfig'
I = F + 'fml/config/IConfigSpec'
E = F + 'fml/event/config/ModConfigEvent'
J = F + 'fml/javafmlmod/FMLJavaModLoadingContext'
B = F + 'fml/ModLoadingContext'
T = 'org/sinytra/connector/forge/config/'
TRANSFORMER = 'source-workspace/connector-four-loader/components/infinity-forge/src/main/java/org/sinytra/connector/forge/transform/Forge52Symbols.java'
ZIP = 'source-workspace/fml-unified/build/successor-client-api1/frozen-inputs/api1-source-only.zip'
PIN = 'c797a562f4a4b14eae619c89aaca75223f5315c599a9cd79f84d49f7a4af7e70'

def sha(path): return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
def symbol(kind, owner, name, descriptor):
    return {'kind': kind, 'owner': owner, 'name': name, 'descriptor': descriptor,
            'transformer_key': owner[len(F):] + '.' + name + (':' if kind == 'field' else '') + descriptor}

def main():
    assert sha(ZIP) == PIN, 'API1 source ZIP pin mismatch'
    methods = []
    def add(owner, name, desc, declaration_owner=None):
        entry = symbol('method', owner, name, desc)
        entry['declaration_owner'] = declaration_owner or owner
        entry['resolution'] = 'inherited-alias' if declaration_owner and owner != declaration_owner else 'declared'
        methods.append(entry)
    for name, desc in [('<init>', '()V'), ('comment', '(Ljava/lang/String;)L'+C+'$Builder;'),
        ('translation', '(Ljava/lang/String;)L'+C+'$Builder;'), ('push', '(Ljava/lang/String;)L'+C+'$Builder;'),
        ('pop', '()L'+C+'$Builder;'), ('define', '(Ljava/lang/String;Z)L'+C+'$BooleanValue;'),
        ('defineInRange', '(Ljava/lang/String;III)L'+C+'$IntValue;'),
        ('define', '(Ljava/lang/String;Ljava/lang/Object;)L'+C+'$ConfigValue;'),
        ('defineListAllowEmpty', '(Ljava/lang/String;Ljava/util/List;Ljava/util/function/Predicate;)L'+C+'$ConfigValue;'),
        ('worldRestart', '()L'+C+'$Builder;'), ('build', '()L'+C+';')]:
        add(C+'$Builder', name, desc)
    for suffix in ('$BooleanValue', '$IntValue', '$ConfigValue'):
        for name, desc in [('get', '()Ljava/lang/Object;'), ('set', '(Ljava/lang/Object;)V')]:
            add(C+suffix, name, desc, C+'$ConfigValue')
    add(C+'$IntValue', 'save', '()V', C+'$ConfigValue')
    add(C, 'isLoaded', '()Z'); add(C, 'save', '()V')
    for tail in ['', 'Ljava/lang/String;']:
        add(J, 'registerConfig', '(L'+M+'$Type;L'+I+';'+tail+')V', B)
    for name, desc in [('getType', '()L'+M+'$Type;'), ('getFileName', '()Ljava/lang/String;'),
                        ('getModId', '()Ljava/lang/String;'), ('getSpec', '()L'+I+';')]:
        add(M, name, desc)
    for suffix in ('$Loading', '$Reloading'):
        add(E+suffix, 'getConfig', '()L'+M+';', E)
    fields = [symbol('field', M+'$Type', 'COMMON', 'L'+M+'$Type;')]
    types = [{'owner': C+s, 'target': T+'ForgeConfigSpec'+s} for s in ('', '$Builder', '$ConfigValue', '$BooleanValue', '$IntValue')]
    types += [{'owner': I, 'target': T+'IForgeConfigSpec', 'restriction': 'descriptor-only; no external implementation or callable IConfigSpec member'},
              {'owner': M, 'target': T+'ForgeModConfig'}, {'owner': M+'$Type', 'target': T+'ForgeModConfig$Type'}]
    types += [{'owner': E+s, 'target': T+'ForgeModConfigEvent'+s} for s in ('$Loading', '$Reloading')]
    negatives = []
    def deny(kind, owner, name, desc, reason, evidence='official-member'):
        item = symbol(kind, owner, name, desc); item.update(reason=reason, evidence=evidence); negatives.append(item)
    for name in ('SERVER', 'CLIENT'):
        deny('field', M+'$Type', name, 'L'+M+'$Type;', 'C1 is COMMON-only')
    for name, desc in [('values','()[L'+M+'$Type;'), ('valueOf','(Ljava/lang/String;)L'+M+'$Type;'), ('extension','()Ljava/lang/String;')]:
        deny('method', M+'$Type', name, desc, 'enum methods are separate, deferred admission decisions')
    deny('method', B, 'get', '()L'+B+';', 'legacy context is outside C1')
    for tail in ('','Ljava/lang/String;'):
        deny('method', B, 'registerConfig', '(L'+M+'$Type;L'+I+';'+tail+')V', 'base context invocation owner is deferred')
        deny('method', M, '<init>', '(L'+M+'$Type;L'+I+';L'+F+'fml/ModContainer;'+tail+')V', 'native tracker owns config construction')
    for name, desc in [('getConfigData','()Lcom/electronwill/nightconfig/core/CommentedConfig;'), ('getHandler','()L'+F+'fml/config/ConfigFileTypeHandler;'), ('save','()V'), ('acceptSyncedConfig','([B)V')]:
        deny('method', M, name, desc, 'raw data, handler, direct ModConfig save and sync are outside C1')
    deny('field', F+'fml/config/ConfigTracker', 'INSTANCE', 'L'+F+'fml/config/ConfigTracker;', 'no second registry or externally exposed tracker')
    deny('method', F+'fml/config/ConfigTracker', 'fileMap', '()Ljava/util/concurrent/ConcurrentHashMap;', 'mutable tracker state is not exposed')
    deny('method', F+'fml/config/ConfigFileTypeHandler', '<init>', '()V', 'no second file engine')
    for name, desc in [('getValues','()Lcom/electronwill/nightconfig/core/UnmodifiableConfig;'), ('setConfig','(Lcom/electronwill/nightconfig/core/CommentedConfig;)V')]:
        deny('method', C, name, desc, 'raw spec access is outside the public C1 lifecycle')
    deny('method', I, 'afterReload', '()V', 'IConfigSpec is descriptor-only in C1')
    for owner in (E, F+'fml/config/IConfigEvent', E+'$Unloading'):
        deny('method', owner, 'getConfig', '()L'+M+';', 'unexercised event owner or deferred Unloading')
    for suffix in ('$Loading', '$Reloading'):
        deny('method', E+suffix, '<init>', '(L'+M+';)V', 'owner dispatches events; external construction is not admitted')
    for suffix in ('$ConfigValue', '$BooleanValue'):
        deny('method', C+suffix, 'save', '()V', 'unexercised invocation owner alias remains deferred')
    deny('method', C+'$Builder', 'comment', '([Ljava/lang/String;)L'+C+'$Builder;', 'unexercised overload')
    for suffix in ('$ConfigValue', '$BooleanValue', '$IntValue'):
        deny('method', C+suffix, 'get', '()Ljava/lang/Integer;', 'generic source type must not replace erased Object descriptor', 'fabricated-near-miss')
        deny('method', C+suffix, 'set', '(I)V', 'generic source type must not replace erased Object descriptor', 'fabricated-near-miss')
    paths = ['docs/api-coverage/forge-config/PROBE-PLAN.md', 'docs/api-coverage/forge-config/ABI-CONTRACTS.md',
             'docs/api-coverage/forge-config/member-shapes.csv', 'docs/api-coverage/forge-config/probe/ForgeConfigLifecycleProbe.java',
             'docs/api-coverage/forge-config/provenance.json', 'tools/api-coverage/forge_classfile.py', TRANSFORMER,
             'four-loader/forge-config-c1-tests/boundary/fixtures/NegativeConfigInputs.java']
    source_paths = [f'docs/api-coverage/forge-config/sources/{x}.java' for x in (C,B,J,M,I,E,F+'fml/config/IConfigEvent')]
    paths += source_paths
    lock = json.loads((ROOT/'docs/api-coverage/forge/inputs.lock.json').read_text())
    artifact_names = ('forge-1.21.1-52.1.0-universal.jar', 'fmlcore-1.21.1-52.1.0.jar', 'javafmllanguage-1.21.1-52.1.0.jar', 'eventbus-6.2.27.jar')
    artifacts = [{k:a[k] for k in ('path','sha256','url')} for a in lock['artifacts'] if Path(a['path']).name in artifact_names]
    for a in artifacts: assert sha(a['path']) == a['sha256'], a['path']
    proposal = {
        'schema_version': 1, 'status': 'proposal-only', 'production_admitted': False,
        'scope': 'C1 COMMON lifecycle probe; exact symbol proposal, not a production transformer or ledger update',
        'emitted_probe_validation': 'pending independent compilation against official Forge 52.1.0',
        'api1_source_baseline': {'path':ZIP, 'sha256':PIN, 'transformer_member':TRANSFORMER},
        'pinned_inputs': [{'path':p, 'sha256':sha(p)} for p in sorted(paths)],
        'official_binary_archives': sorted(artifacts, key=lambda a:a['path']),
        'types': sorted(types, key=lambda x:x['owner']),
        'methods': sorted(methods, key=lambda x:x['transformer_key']), 'fields': fields,
        'existing_dependencies': {'types':[F+'fml/common/Mod', J, F+'eventbus/api/IEventBus', F+'fml/event/lifecycle/FMLCommonSetupEvent'],
                                  'method_keys':['fml/javafmlmod/FMLJavaModLoadingContext.getModEventBus()Lnet/minecraftforge/eventbus/api/IEventBus;', 'eventbus/api/IEventBus.addListener(Ljava/util/function/Consumer;)V'],
                                  'context_target':'org/sinytra/connector/forge/loader/ForgeModLoadingContext'},
        'negative_symbols': sorted(negatives,key=lambda x:(x['kind'],x['transformer_key'])),
        'class_policy': {'reject_forge_implementation': True, 'reject_forge_subclass': True,
                         'existing_only_subclass_exception':F+'eventbus/api/Event', 'reject_bundled_forge_namespace':True,
                         'synthetic_negative_headers':[
                             {'name':'infinity/probe/CustomSpec','super':'java/lang/Object','interfaces':[I]},
                             *[{'name':'infinity/probe/Subclass'+s.replace('$',''), 'super':C+s,'interfaces':[]} for s in ('','$Builder','$ConfigValue','$BooleanValue','$IntValue')],
                             {'name':'infinity/probe/SubclassModConfig','super':M,'interfaces':[]},
                             {'name':'infinity/probe/SubclassLoading','super':E+'$Loading','interfaces':[]}]},
        'default_deny': 'All other Forge types/methods/fields remain unsupported, including omitted public and protected members, handles, inherited aliases and erased descriptor near-misses.',
        'runtime_guards_required': ['COMMON only; reject CLIENT/SERVER even if obtained without direct field access', 'Accept only the supported concrete source-derived spec; reject custom IConfigSpec and subclasses', 'Use the single native config owner, registry, file, watcher and lock'],
        'limitations': ['Static declaration/hierarchy evidence is not runtime linking or semantics proof', 'Source hashes bind the fixture but do not prove javac emitted these owners', 'Python reference gate tests do not execute or replace the production ASM transformer', 'Alias/type expansion beyond this probe requires independent emitted-class evidence and explicit approval'],
    }
    (HERE/'proposed-allowlist.json').write_text(json.dumps(proposal,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'proposal-only','methods':len(methods),'fields':len(fields),'new_types':len(types),'negative_symbols':len(negatives)},sort_keys=True))
if __name__ == '__main__': main()
