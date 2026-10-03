#!/usr/bin/env python3
import hashlib,json,pathlib,shutil,subprocess,zipfile
base=pathlib.Path(__file__).resolve().parent;repo=base.parent;t=base/'connector-unified';src=repo/'lithium-trial/adapter-core-2.0.43+1.21.1-sources.jar'; expected='7fe14fb8f5c4a737ac5e7e8d9c563b698f3341fc2a58c9074d4d3f2b08e9f4f8'
assert hashlib.sha256(src.read_bytes()).hexdigest()==expected
up=base/'upstream';shutil.copy2(src,up/src.name);shutil.copy2(repo/'lithium-trial/adapter-LICENSE.txt',up/'Adapter-LICENSE.txt')
module=t/'components/infinity-adapter'; sources=module/'src/main/java'
if module.exists():raise SystemExit('Refusing to replace existing Adapter source project')
with zipfile.ZipFile(src) as z:
 for n in z.namelist():
  if n.endswith('.java'):
   assert '..' not in pathlib.PurePosixPath(n).parts and not n.startswith('/')
   p=sources/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
patch=repo/'lithium-trial/patches/final/adapter-source.patch'
subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)],cwd=sources,check=True)
provenance=json.loads((repo/'lithium-trial/patches/final/provenance.json').read_text())
for item in provenance['identity']['patched_sources']:assert hashlib.sha256((sources/item['path']).read_bytes()).hexdigest()==item['sha256']
r=module/'src/main/resources/META-INF/unified-infinity';r.mkdir(parents=True,exist_ok=True);shutil.copy2(up/'Adapter-LICENSE.txt',r/'LICENSE-Adapter-MIT.txt')
(module/'build.gradle.kts').write_text('''plugins { `java-library` }
group = "org.sinytra.adapter"
version = "2.0.43+1.21.1-infinity"
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)); withSourcesJar() }
repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net")
    maven("https://libraries.minecraft.net")
}
dependencies {
    compileOnly("org.jetbrains:annotations:24.0.1")
    api("com.mojang:datafixerupper:8.0.16")
    api(platform("org.ow2.asm:asm-bom:9.8"))
    listOf("asm", "asm-commons", "asm-tree", "asm-analysis", "asm-util").forEach { api("org.ow2.asm:$it") }
    implementation("com.mojang:logging:1.1.1")
    implementation("com.google.guava:guava:32.1.2-jre")
    implementation("org.slf4j:slf4j-api:2.0.0")
    implementation("net.fabricmc:sponge-mixin:0.14.0+mixin.0.8.6")
    implementation("io.github.llamalad7:mixinextras-common:0.3.1")
}
tasks.withType<JavaCompile>().configureEach { options.release.set(21); options.compilerArgs.add("-proc:none") }
''')
p=t/'settings.gradle.kts';s=p.read_text()+'\ninclude(":infinity-adapter")\nproject(":infinity-adapter").projectDir = file("components/infinity-adapter")\n';p.write_text(s)
p=t/'build.gradle.kts';s=p.read_text().replace('substitute(module("org.sinytra:ForgeAutoRenamingTool")).using(project(":infinity-fart"))','substitute(module("org.sinytra:ForgeAutoRenamingTool")).using(project(":infinity-fart"))\n            substitute(module("org.sinytra.adapter:core")).using(project(":infinity-adapter"))');s+='''
tasks.named<ShadowJar>("fullJar") {
    dependsOn(":infinity-adapter:sourcesJar")
    from(project(":infinity-adapter").layout.buildDirectory.file("libs/infinity-adapter-2.0.43+1.21.1-infinity-sources.jar")) {
        into("META-INF/unified-infinity/sources")
    }
    manifest.attributes("Unified-Infinity-Build" to "complete-connector-fart-adapter-source-research")
}
''';p.write_text(s)
result={'schema':1,'status':'source-prepared-not-built','module':'org.sinytra.adapter:core:2.0.43+1.21.1','sources_jar_sha256':expected,'source_file_count':len(list(sources.rglob('*.java'))),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'validated_experiment_sha256':provenance['artifact_sha256'],'patched_sources':provenance['identity']['patched_sources'],'license_sha256':hashlib.sha256((up/'Adapter-LICENSE.txt').read_bytes()).hexdigest()};(base/'provenance/adapter-source-integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
