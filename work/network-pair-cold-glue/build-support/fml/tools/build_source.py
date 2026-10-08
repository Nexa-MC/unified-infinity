#!/usr/bin/env python3
"""Explicit full-source compile; no Gradle, game launch, upstream class injection, or profile mutation."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PROCESSOR = 'org.apache.logging.log4j.core.config.plugins.processor.PluginProcessor'
PROCESSOR_PINS = {
    'run/client-dev/libraries/org/apache/logging/log4j/log4j-core/2.22.1/log4j-core-2.22.1.jar': '46dccecac556623d8e2ce8648496824a82951d139062a4e61148aff1a25ed18d',
    'run/client-dev/libraries/org/apache/logging/log4j/log4j-api/2.22.1/log4j-api-2.22.1.jar': '5d7beae7ff15d8516d6517121d7f12a79a6ac180df64b5fcec55d5be21056e53',
}
PLUGIN_CACHE = 'META-INF/org/apache/logging/log4j/core/config/plugins/Log4j2Plugins.dat'
PLUGIN_CACHE_SHA = 'd0f0b5582b430acd1be817a94989f6eda13d359d6980dcdc1bb568408bcb76e6'
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''): h.update(chunk)
    return h.hexdigest()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--classpath-lock', type=pathlib.Path, required=True)
    ap.add_argument('--installation-policy', type=pathlib.Path)
    ap.add_argument('--javac', default='javac')
    ap.add_argument('--output', type=pathlib.Path, default=ROOT/'build/source-candidate')
    ap.add_argument('--compile', action='store_true', help='Starts two serial JVMs; requires released budget, never implied by validation')
    ns = ap.parse_args()
    lock = json.loads(ns.classpath_lock.read_text())
    if lock.get('schema') != 1: raise SystemExit('Unsupported dependency lock')
    dependencies=[]
    for item in lock['artifacts']:
        path=(REPO/item['path']).resolve()
        if sha(path) != item['sha256']: raise SystemExit('Dependency pin changed: '+str(path))
        if path.name.startswith('loader-4.0.42'): raise SystemExit('Upstream FML binary cannot mask missing source')
        dependencies.append(str(path))
    processors=[]
    for path, digest in PROCESSOR_PINS.items():
        if sum(item['path'] == path and item['sha256'] == digest for item in lock['artifacts']) != 1:
            raise SystemExit('Missing exact Log4j processor input: '+path)
        processors.append(str((REPO/path).resolve()))
    sources = sorted((ROOT/'src/main/java').rglob('*.java')) + sorted((ROOT.parent/'admission-bootstrap/src/main/java').rglob('*.java'))
    upstream=json.loads((ROOT/'provenance/upstream-source.json').read_text())
    expected=[x for x in upstream['files'] if x['path'].endswith('.java')]
    if len(expected) != 179 or any(not (ROOT/x['path']).is_file() for x in expected): raise SystemExit('Incomplete full FML source tree')
    policy = json.loads(ns.installation_policy.read_text()) if ns.installation_policy else {'schema':1,'approved':False}
    print(json.dumps({'status':'source-inputs-verified','fullFmlSources':len(expected),'sharedSources':len(sources)-179,'dependencyCount':len(dependencies),'installationApproved':policy.get('approved',False),'javaLaunched':False}))
    if not ns.compile: return
    build=ns.output.resolve();classes=build/'classes';classes.mkdir(parents=True,exist_ok=True)
    if any(classes.iterdir()): raise SystemExit('Refusing stale class output; choose a clean new build directory')
    args=['--release','21','-encoding','UTF-8','-proc:none','-classpath',os.pathsep.join(dependencies),'-d',str(classes),*map(str,sources)]
    argfile=build/'javac.args';argfile.write_text('\n'.join('"'+x.replace('\\','\\\\').replace('"','\\"')+'"' for x in args)+'\n')
    subprocess.run([ns.javac,'-J-Xmx192m','-J-XX:ActiveProcessorCount=2','@'+str(argfile)],check=True)
    # Keep the canonical class compilation intact. The second invocation emits
    # only metadata from the source annotation, using the fresh classes as input.
    generated=build/'log4j-plugin-resources';generated.mkdir()
    empty_sourcepath=build/'empty-log4j-sourcepath';empty_sourcepath.mkdir()
    processor_args=['--release','21','-encoding','UTF-8','-proc:only','-processor',PROCESSOR,
                    '-processorpath',os.pathsep.join(processors),'-implicit:none','-sourcepath',str(empty_sourcepath),
                    '-classpath',os.pathsep.join([str(classes),*dependencies]),'-d',str(generated),
                    str(ROOT/'src/main/java/net/neoforged/fml/loading/log4j/ForgeHighlight.java')]
    processor_argfile=build/'log4j-processor.args'
    processor_argfile.write_text('\n'.join('"'+x.replace('\\','\\\\').replace('"','\\"')+'"' for x in processor_args)+'\n')
    subprocess.run([ns.javac,'-J-Xmx192m','-J-XX:ActiveProcessorCount=1','@'+str(processor_argfile)],check=True)
    cache=generated/PLUGIN_CACHE
    if not cache.is_file() or sha(cache) != PLUGIN_CACHE_SHA or [p for p in generated.rglob('*') if p.is_file()] != [cache]:
        raise SystemExit('Metadata-only Log4j output differs from the reviewed source/upstream registration')
    for resource in (ROOT/'src/main/resources').rglob('*'):
        if resource.is_file():
            dest=classes/resource.relative_to(ROOT/'src/main/resources');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(resource,dest)
    dest=classes/'META-INF/unified-admission/installation.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(policy,sort_keys=True,separators=(',',':'))+'\n')
    shutil.copyfile(ROOT/'LICENSE-LGPL-2.1.txt',classes/'META-INF/unified-admission/LICENSE-LGPL-2.1.txt')
    shutil.copyfile(ROOT/'MODIFICATIONS.md',classes/'META-INF/unified-admission/MODIFICATIONS.md')
    cache_dest=classes/PLUGIN_CACHE;cache_dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(cache,cache_dest)
    jar=build/'fml-loader-4.0.42-unified-admission-candidate.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(classes.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(classes).as_posix(),(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
                archive.writestr(info,path.read_bytes())
    receipt={'schema':1,'artifact':str(jar),'sha256':sha(jar),'upstreamSourceSha256':upstream['archiveSha256'],'classCount':len(list(classes.rglob('*.class'))),'installationPolicySha256':sha(dest),'installationApproved':policy.get('approved',False),'sources':{str(p.relative_to(ROOT.parent)):sha(p) for p in sources}}
    receipt['annotationProcessor']={'class':PROCESSOR,'mode':'separate-proc-only-after-full-proc-none-compile','inputs':PROCESSOR_PINS,'cachePath':PLUGIN_CACHE,'cacheSha256':sha(cache)}
    (build/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__ == '__main__': main()
