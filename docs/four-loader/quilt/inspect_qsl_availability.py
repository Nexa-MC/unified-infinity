#!/usr/bin/env python3
"""Static audit of official QSL alpha5 artifacts. Never executes downloaded code."""
import concurrent.futures,hashlib,io,json,pathlib,urllib.request,xml.etree.ElementTree as ET,zipfile
ROOT=pathlib.Path(__file__).parent
OUT=ROOT/'upstream'/'qsl-alpha5-artifacts';OUT.mkdir(exist_ok=True)
VERSION='10.0.0-alpha.5+1.21.1';BASE='https://maven.quiltmc.org/repository/release/'
HEADERS={'User-Agent':'Unified-Infinity-read-only-audit/1.0'}
def fetch(url):
 return urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=45).read()
def artifact(g,a):
 root=BASE+g.replace('.','/')+'/'+a+'/'+VERSION+'/'+a+'-'+VERSION
 row={'group':g,'artifact':a,'version':VERSION,'pom_url':root+'.pom'}
 try:
  b=fetch(root+'.pom');(OUT/(a+'.pom')).write_bytes(b);row['pom_sha256']=hashlib.sha256(b).hexdigest();e=ET.fromstring(b);ns={'m':'http://maven.apache.org/POM/4.0.0'}
  row['packaging']=e.findtext('m:packaging','jar',ns);row['dependencies']=[{x:d.findtext('m:'+x,namespaces=ns) for x in ['groupId','artifactId','version','scope']} for d in e.findall('m:dependencies/m:dependency',ns)]
  if row['packaging']!='pom':
   row['jar_url']=root+'.jar';b=fetch(root+'.jar');(OUT/(a+'.jar')).write_bytes(b);row.update(sha256=hashlib.sha256(b).hexdigest(),sha512=hashlib.sha512(b).hexdigest(),bytes=len(b))
   with zipfile.ZipFile(io.BytesIO(b)) as z:
    row['class_count']=len([n for n in z.namelist() if n.endswith('.class')]); row['metadata']=json.loads(z.read('quilt.mod.json')) if 'quilt.mod.json' in z.namelist() else None; row['has_fabric_metadata']='fabric.mod.json' in z.namelist()
 except Exception as e:row['error']=str(e)
 return row
pending=[('org.quiltmc','qsl')];seen=set();rows=[]
while pending:
 batch=[x for x in pending if x not in seen];seen.update(batch);pending=[]
 for row in concurrent.futures.ThreadPoolExecutor(10).map(lambda x:artifact(*x),batch):
  rows.append(row)
  if row.get('packaging')=='pom':
   pending += [(d['groupId'],d['artifactId']) for d in row['dependencies'] if d['groupId'].startswith('org.quiltmc') and d['version']==VERSION]
report={'timestamp_utc':'2026-10-03','mode':'static artifacts only; no module executed','rows':rows}
(ROOT/'qsl-availability.json').write_text(json.dumps(report,indent=2)+'\n')
for r in rows:print(r['group'],r['artifact'],r.get('packaging'),r.get('bytes'),r.get('class_count'),r.get('error','OK'))
