#!/usr/bin/env python3
"""Build-only wrapper for pinned Connector sources, using the approved Java 21 / Gradle 8.11.1."""
import os,pathlib,subprocess,sys,urllib.parse
root=pathlib.Path(__file__).resolve().parent.parent
workspace=root/'source-workspace'
env=os.environ.copy();env['JAVA_HOME']=str(root/'.toolchains/jdk-21.0.12.1+1');env['PATH']=env['JAVA_HOME']+'/bin:'+env['PATH'];env['GRADLE_USER_HOME']=str(workspace/'gradle-cache');env['XDG_CACHE_HOME']=str(workspace/'xdg-cache')
# Official ModDevGradle 2.0.140 binary-only Minecraft artifact mode; never decompile here.
env['CI']='true'
env['HOME']=str(workspace/'home');env['XDG_CONFIG_HOME']=str(workspace/'xdg-config')
(workspace/'home').mkdir(exist_ok=True);(workspace/'xdg-config').mkdir(exist_ok=True)
opts=['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts',f"-Duser.home={workspace/'home'}"]
p=urllib.parse.urlparse(env.get('HTTPS_PROXY') or env.get('HTTP_PROXY',''))
if p.hostname:
 for scheme in ['http','https']: opts.extend([f'-D{scheme}.proxyHost={p.hostname}',f'-D{scheme}.proxyPort={p.port}'])
env['JAVA_TOOL_OPTIONS']=' '.join(opts);env['GRADLE_OPTS']=' '.join(opts)
# HotSpot applies _JAVA_OPTIONS after command-line JVM options, including NeoForm's -Xmx4G.
env['_JAVA_OPTIONS']='-Xmx2G -XX:ActiveProcessorCount=2'
args=sys.argv[1:] or ['fullJar']
project='connector-combined' if '--unified' in args else 'connector'
args=[a for a in args if a!='--unified']
if any(x.lower().split(':')[-1].startswith(('run','publish','upload','release')) for x in args):raise SystemExit('This wrapper allows build and inspection tasks only')
cmd=[str(root/'.toolchains/gradle-8.11.1/bin/gradle'),'--no-daemon','--console=plain','--max-workers=2','--no-parallel','-Dorg.gradle.jvmargs=-Xmx2G','--project-cache-dir',str(workspace/(project+'-project-cache')),'-p',str(workspace/project)]+args
raise SystemExit(subprocess.call(cmd,env=env))
