#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
CP="docs/research/upstream/connector-2.0.0-beta.17+1.21.1-full.jar:probes/build/lib/fabric-api-base.jar:run/neoforge-native/libraries/net/fabricmc/sponge-mixin/0.15.2+mixin.0.8.7/sponge-mixin-0.15.2+mixin.0.8.7.jar"
tools/java-env.sh javac -proc:none --release 21 -cp "$CP" -d probes/build/classes probes/src/dev/compat/probe/*.java probes/src/dev/compat/probe/mixin/*.java
tools/java-env.sh jar --create --file probes/build/compat-parity-probe-0.2.0.jar -C probes/build/classes . -C probes/resources .
sha256sum probes/build/compat-parity-probe-0.2.0.jar
