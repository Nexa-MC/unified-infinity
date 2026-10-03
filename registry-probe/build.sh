#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
JAVA=.toolchains/jdk-21.0.12.1+1/bin
mkdir -p registry-probe/build/classes registry-probe/build/lib
python3 - <<'PY'
import pathlib, zipfile
out = pathlib.Path('registry-probe/build/lib')
with zipfile.ZipFile('run/fabric-native/mods/fabric-api-0.116.7+1.21.1.jar') as z:
    for module in ('fabric-api-base', 'fabric-lifecycle-events-v1'):
        name = next(n for n in z.namelist() if n.startswith('META-INF/jars/' + module + '-'))
        (out / (module + '.jar')).write_bytes(z.read(name))
PY
CP="run/fabric-native/.fabric/remappedJars/minecraft-1.21.1-0.19.3/server-intermediary.jar:registry-probe/build/lib/fabric-api-base.jar:registry-probe/build/lib/fabric-lifecycle-events-v1.jar"
for jar in $(find run/fabric-native/libraries -name '*.jar' | sort); do CP="$CP:$jar"; done
"$JAVA/javac" -proc:none --release 21 -cp "$CP" -d registry-probe/build/classes registry-probe/src/dev/infinity/registryprobe/RegistryProbe.java
"$JAVA/jar" --create --date=2026-01-01T00:00:00Z --file registry-probe/build/infinity-registry-probe-0.1.0.jar -C registry-probe/build/classes . -C registry-probe/resources .
"$JAVA/javap" -c -p -classpath registry-probe/build/infinity-registry-probe-0.1.0.jar dev.infinity.registryprobe.RegistryProbe > registry-probe/build/direct-bytecode.txt
sha256sum registry-probe/build/infinity-registry-probe-0.1.0.jar
