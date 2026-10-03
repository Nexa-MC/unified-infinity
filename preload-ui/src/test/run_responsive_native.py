#!/usr/bin/env python3
"""Bounded native-only QA; every JVM uses the verified minimal local-game environment."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / 'preload-ui/build-candidate-responsive/20261003-source-v1'
JDK = ROOT / '.toolchains/jdk-21.0.12.1+1'
PROVIDER = CANDIDATE / 'libs/unified-infinity-preload-responsive-candidate.jar'
EXPECTED = 'ca776b212632f387a76dbb20be766f6fe4d852424a3af7bd59e05cb6e6f6be7a'
spec = importlib.util.spec_from_file_location('game_environment', ROOT / 'four-loader/launch-support/game_environment.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('compile', 'normal', 'reduced', 'early-close'))
    parser.add_argument('--session', required=True)
    args = parser.parse_args()
    if not args.session.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Use an alphanumeric session label')
    session = CANDIDATE / 'native-qa' / args.session
    session.mkdir(parents=True, exist_ok=True)
    policy.create_private_environment_directories(session)
    environment = policy.build_game_environment(os.environ, session, JDK, {})
    if hashlib.sha256(PROVIDER.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('Candidate provider bytes changed; review before testing')
    descriptor = {'mode': args.mode, 'candidateSha256': EXPECTED, 'environment': policy.public_policy_descriptor(),
                  'cooperativeCoreSha256': hashlib.sha256((CANDIDATE / 'core-classes/org/sinytra/connector/infinity/BoundedBatch.class').read_bytes()).hexdigest(),
                  'harnessDeadlineSeconds': 120, 'ownedChildWatchdogSeconds': 140,
                  'claim': 'native harness only, no Minecraft or loader-event acceptance'}
    (session / 'launch-policy.json').write_text(json.dumps(descriptor, indent=2) + '\n')
    base = (ROOT / 'preload-ui/build/classpath.txt').read_text().removesuffix(':build/classes:build/test-classes')
    harness = CANDIDATE / 'responsive-harness-classes'
    cp = base + ':' + str(PROVIDER) + ':' + str(CANDIDATE / 'core-classes')
    if args.mode == 'compile':
        harness.mkdir(exist_ok=True)
        command = [str(JDK / 'bin/javac'), '-J-Xmx128m', '-J-XX:ActiveProcessorCount=2', '--release', '21', '-encoding', 'UTF-8',
                   '-Xlint:all', '-cp', cp, '-d', str(harness),
                   str(ROOT / 'preload-ui/src/nativeTest/java/dev/modcompat/preload/ResponsiveNativeHarness.java')]
        with (session / 'compile.log').open('w') as output:
            result = subprocess.run(command, cwd=session, env=environment, stdout=output, stderr=subprocess.STDOUT, timeout=90)
        print((session / 'compile.log').read_text(), end='')
        return result.returncode
    # No broad cache/classpath scan: use pinned support dependencies and the candidate only.
    for name in ('lwjgl', 'lwjgl-glfw', 'lwjgl-opengl'):
        cp += ':' + str(ROOT / f'preload-ui/.deps/{name}-3.3.3-natives-linux.jar')
    cp += ':' + str(harness)
    # Exact support dependencies needed by FMLConfig/DisplayWindow; no game JARs.
    for relative in ('org/apache/logging/log4j/log4j-api/2.22.1/log4j-api-2.22.1.jar',
                     'com/mojang/logging/1.2.7/logging-1.2.7.jar',
                     'com/electronwill/night-config/core/3.8.3/core-3.8.3.jar',
                     'com/electronwill/night-config/toml/3.8.3/toml-3.8.3.jar'):
        dependency = ROOT / 'run/neoforge-native/libraries' / relative
        if not dependency.is_file():
            raise ValueError('Pinned native harness support dependency missing: ' + relative)
        cp += ':' + str(dependency)
    command = [str(JDK / 'bin/java'), '-Xmx128m', '-XX:MaxDirectMemorySize=64m', '-XX:ActiveProcessorCount=2',
               '-Djava.awt.headless=false', '-Dunified.infinity.qaScenario=' + args.mode, '-Dunified.infinity.reducedMotion=' + str(args.mode == 'reduced').lower(),
               '-cp', cp, 'dev.modcompat.preload.ResponsiveNativeHarness']
    print('NATIVE_QA_SESSION ' + str(session), flush=True)
    with (session / 'run.log').open('w') as output:
        child = subprocess.Popen(command, cwd=session, env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
        def stop_owned_child():
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
        watchdog = threading.Timer(140, stop_owned_child)
        watchdog.start()
        try:
            for line in child.stdout:
                output.write(line); output.flush(); print(line, end='', flush=True)
            status = child.wait(timeout=10)
        finally:
            watchdog.cancel()
            if child.poll() is None:
                stop_owned_child()
    (session / 'exit.json').write_text(json.dumps({'exitCode': status, 'candidateSha256': EXPECTED}) + '\n')
    return status

if __name__ == '__main__':
    sys.exit(main())
