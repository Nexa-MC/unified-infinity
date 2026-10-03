#!/usr/bin/env python3
"""Bounded, static source/provenance checks. A pass is not JVM/service/runtime acceptance."""
import hashlib,json,pathlib,ast
ROOT=pathlib.Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run():
    provenance=json.loads((ROOT/'provenance/upstream-source.json').read_text())
    modified=[];unmodified=0
    for record in provenance['files']:
        path=ROOT/record['path'];assert path.is_file(),path
        if sha(path)==record['sha256']:unmodified+=1
        else:
            modified.append(record['path'])
            if path.suffix=='.java':
                s=path.read_text();assert 'Modified 2026-10-03 for Unified Infinity' in s
                assert 'SPDX-License-Identifier: LGPL-2.1-only' in s
    base=ROOT/'src/main/java/net/neoforged/fml/loading'
    service=(base/'ModDirTransformerDiscoverer.java').read_text()
    assert service.index('BootstrapInstallation.open')<service.index('FMLPaths.loadAbsolutePaths')
    assert 'Files.walk(' not in service
    assert service.index('admittedFolder(')<service.index('if (shouldLoadInServiceLayer(path))')
    cp=(base/'ClasspathTransformerDiscoverer.java').read_text();assert 'BootstrapInstallation.open' in cp
    assert 'permits(paths) && shouldLoadInServiceLayer(paths)' in cp
    normal=(base/'moddiscovery/ModDiscoverer.java').read_text()
    assert normal.index('permits(groupedPaths)')<normal.index('launchContext.addLocated(primaryPath)')
    assert 'permitsRuntimeObject(jarContents)' in normal and 'permitsRuntimeObject(mf)' in normal
    assert 'inheritRuntimeObject(provided, jarContents)' in normal
    assert 'Files.list(' not in (base/'moddiscovery/locators/ModsFolderLocator.java').read_text()
    jij=(base/'moddiscovery/locators/JarInJarDependencyLocator.java').read_text()
    assert 'nestedArchive(' in jij and 'zipFS.getPath("/")' not in jij
    for untouched in ['ModSorter.java','moddiscovery/ModValidator.java','TransformerDiscovererConstants.java','ImmediateWindowHandler.java']:
        record=next(x for x in provenance['files'] if x['path']=='src/main/java/net/neoforged/fml/loading/'+untouched)
        assert sha(ROOT/record['path'])==record['sha256'],untouched
    model=REPO/'source-workspace/admission-bootstrap/src/main/java/org/sinytra/connector/infinity/inventory'
    production=REPO/'source-workspace/connector-four-loader'
    duplicates=[str(p) for p in production.rglob('src/main/java/org/sinytra/connector/infinity/inventory/*.java')]
    assert not duplicates,duplicates
    assert (model/'AdmissionSession.java').is_file()
    for tool in (ROOT/'tools').glob('*.py'):ast.parse(tool.read_text())
    result={'status':'PASS-static-only','upstreamJavaSources':179,'unchangedUpstreamFiles':unmodified,'modifiedUpstreamFiles':modified,'duplicateProductionModelSources':duplicates,'thisStaticCheckStartsJvm':False,'thisStaticCheckRunsServiceMarkers':False,'successorInstalled':False}
    out=ROOT/'provenance/static-source-check.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':run()
