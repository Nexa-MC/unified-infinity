#!/usr/bin/env python3
"""Run official ModDevGradle tasks in an isolated cache; no session fabrication."""
import os,pathlib,subprocess,sys,urllib.parse
root=pathlib.Path(__file__).resolve().parents[2]
env=os.environ.copy(); env['JAVA_HOME']=str(root/'.toolchains/jdk-21.0.12.1+1');env['PATH']=env['JAVA_HOME']+'/bin:'+env['PATH'];env['GRADLE_USER_HOME']=str(root/'run/client-dev/gradle-cache');env['XDG_CACHE_HOME']=str(root/'run/client-dev/xdg-cache')
env['NFRT_ASSET_ROOT']=str(root/'run/client-dev/assets')
opts=['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
p=urllib.parse.urlparse(env.get('HTTPS_PROXY') or env.get('HTTP_PROXY',''))
if p.hostname:
 for scheme in ['http','https']:
  opts.extend([f'-D{scheme}.proxyHost={p.hostname}',f'-D{scheme}.proxyPort={p.port}'])
env['JAVA_TOOL_OPTIONS']=' '.join(opts)
env['GRADLE_OPTS']=' '.join(opts)
args=sys.argv[1:] or ['tasks','--all']
if 'runClient' in args and '--launch' not in args:
 raise SystemExit('Use --launch runClient only after the UI worker is ready; no game is launched by preparation.')
args=[a for a in args if a!='--launch']
cmd=[str(root/'.toolchains/gradle-8.11.1/bin/gradle'),'--no-daemon','--console=plain','--max-workers=4','--project-cache-dir',str(root/'run/client-dev/gradle-project-cache'),'-p',str(root/'tools/client-setup/development')]+args
raise SystemExit(subprocess.call(cmd,env=env))
