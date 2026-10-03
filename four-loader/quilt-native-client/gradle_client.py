#!/usr/bin/env python3
"""Official pinned Quilt Loom development flow, profile-private writable state."""
import os, pathlib, subprocess, sys, urllib.parse
ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'run/quilt-native-client'
env = os.environ.copy()
env['JAVA_HOME'] = str(ROOT / '.toolchains/jdk-21.0.12.1+1')
env['PATH'] = env['JAVA_HOME'] + '/bin:' + env['PATH']
env['GRADLE_USER_HOME'] = str(PROFILE / 'gradle-cache')
env['XDG_CACHE_HOME'] = str(PROFILE / 'xdg-cache')
opts = ['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
proxy = urllib.parse.urlparse(env.get('HTTPS_PROXY') or env.get('HTTP_PROXY', ''))
if proxy.hostname:
    for scheme in ('http', 'https'):
        opts.extend([f'-D{scheme}.proxyHost={proxy.hostname}', f'-D{scheme}.proxyPort={proxy.port}'])
env['JAVA_TOOL_OPTIONS'] = env['GRADLE_OPTS'] = ' '.join(opts)
args = sys.argv[1:] or ['prepareClientLaunch']
if any('runServer' in a for a in args):
    raise SystemExit('This approved OP Tab control is client-only.')
if any('runClient' in a for a in args):
    if '--launch' not in args or '--runtime-slot-approved' not in args:
        raise SystemExit('Runtime slot and desktop assignment required; pass --launch --runtime-slot-approved only after authorization.')
    if '--offline' not in args:
        raise SystemExit('The frozen acceptance runtime must launch with --offline.')
    subprocess.run([sys.executable, str(ROOT/'four-loader/quilt-native-client/verify_profile.py'), '--runtime'],check=True)
args = [a for a in args if a not in ('--launch','--runtime-slot-approved')]
# Standalone preparation can remap the full approved closure before the game.
# The direct IDE-style launch runs only after this daemon has exited.
cmd = [str(ROOT / '.toolchains/gradle-8.11.1/bin/gradle'), '-Dorg.gradle.jvmargs=-Xmx768m -XX:ActiveProcessorCount=2', '--no-daemon', '--console=plain', '--max-workers=2', '--project-cache-dir', str(PROFILE / 'gradle-project-cache'), '-p', str(ROOT / 'four-loader/quilt-native-client/development')] + args
raise SystemExit(subprocess.call(cmd, env=env))
