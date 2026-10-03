#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export JAVA_HOME="$ROOT/.toolchains/jdk-21.0.12.1+1"
export GRADLE_USER_HOME="$ROOT/.gradle"
export PATH="$JAVA_HOME/bin:$ROOT/.toolchains/gradle-8.11.1/bin:$PATH"
exec "$@"
