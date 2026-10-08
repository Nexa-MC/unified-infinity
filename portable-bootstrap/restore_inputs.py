#!/usr/bin/env python3
"""Restore immutable official inputs under an explicit isolated build root."""
import argparse, concurrent.futures, hashlib, json, pathlib, tempfile, time, urllib.error, urllib.parse, urllib.request
HERE=pathlib.Path(__file__).resolve().parent

def digest(path,kind='sha256'):
    value=hashlib.new(kind)
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):value.update(data)
    return value.hexdigest()

def destination(root,name):
    p=pathlib.PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe relative path')
    out=root.joinpath(*p.parts)
    if not out.resolve().is_relative_to(root):raise ValueError('Destination leaves isolated root')
    return out

def validate(path,row):
    if 'bytes' in row and path.stat().st_size!=row['bytes']:raise ValueError('Size mismatch: '+row['path'])
    for kind in ('sha256','sha1'):
        if kind in row and digest(path,kind)!=row[kind]:raise ValueError(kind+' mismatch: '+row['path'])

def restore(root,row,allowed):
    path=destination(root,row['path'])
    if path.exists():validate(path,row);return {'path':row['path'],'status':'verified-existing','sha256':digest(path),'bytes':path.stat().st_size}
    def check(url):
        x=urllib.parse.urlsplit(url)
        if x.scheme!='https' or x.hostname not in allowed or x.username or x.password or x.port not in (None,443):raise ValueError('Non-allowlisted HTTPS URL')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            check(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener=urllib.request.build_opener(Redirect());path.parent.mkdir(parents=True,exist_ok=True)
    last=None
    for url in row['urls']:
        check(url)
        for attempt in range(3):
            try:
                with opener.open(urllib.request.Request(url,headers={'User-Agent':'Unified-Infinity-pinned-restoration/1'}),timeout=45) as response:
                    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.verified-download-',delete=False) as stream:
                        temp=pathlib.Path(stream.name)
                        try:
                            count=0
                            while data:=response.read(1024*1024):
                                count+=len(data)
                                if count>row.get('bytes',512*1024*1024):raise ValueError('Download exceeds bounded size')
                                stream.write(data)
                            stream.flush();validate(temp,row);temp.replace(path)
                        finally:temp.unlink(missing_ok=True)
                return {'path':row['path'],'status':'downloaded-and-verified','sha256':digest(path),'bytes':path.stat().st_size}
            except urllib.error.HTTPError as error:
                last=error
                if error.code in (404,410):break
                if error.code in (429,500,502,503,504) and attempt<2:time.sleep(1+attempt);continue
                raise
            except (TimeoutError,urllib.error.URLError) as error:
                last=error
                if attempt<2:time.sleep(1+attempt);continue
                raise
    raise RuntimeError('Pinned official artifact unavailable: '+row['path']) from last

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--lock',type=pathlib.Path,default=HERE/'input-lock.json');p.add_argument('--phase',action='append');p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    root=a.root.resolve();lock=json.loads(a.lock.read_text());rows=[r for r in lock['artifacts'] if not a.phase or r['phase'] in a.phase]
    if not 1<=a.workers<=4:raise ValueError('One to four bounded download workers')
    results=[];failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        tasks={pool.submit(restore,root,row,set(lock['allowedHosts'])):row for row in rows}
        for task in concurrent.futures.as_completed(tasks):
            row=tasks[task]
            try:result=task.result();results.append(result);print('VERIFIED '+row['path'],flush=True)
            except Exception as error:failures.append({'path':row['path'],'error':str(error)});print('FAILED '+row['path']+': '+str(error),flush=True)
    report={'status':'PASS' if not failures else 'FAILED','verified':results,'failures':failures,'jvmStarted':False,'lockSha256':digest(a.lock)}
    evidence=HERE/'evidence';evidence.mkdir(exist_ok=True);name='restore-'+('-'.join(a.phase) if a.phase else 'all')+'.json';(evidence/name).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'verified':len(results),'failed':len(failures),'receipt':str(evidence/name)}))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
