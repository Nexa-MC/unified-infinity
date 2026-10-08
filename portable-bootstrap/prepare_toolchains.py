#!/usr/bin/env python3
"""Verify and extract the two approved distributions; never start Java."""
import argparse,hashlib,json,pathlib,tarfile,zipfile
HERE=pathlib.Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=pathlib.Path,required=True);args=parser.parse_args();root=args.root.resolve()
    for row in json.loads((HERE/'input-lock.json').read_text())['artifacts']:
        if row['phase']!='toolchains':continue
        path=root/row['path'];assert path.stat().st_size==row['bytes'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        if path.name.endswith('.tar.gz'):
            target=root/'.toolchains/jdk-21.0.12.1+1'
            if target.exists():continue
            with tarfile.open(path) as archive:
                members=archive.getmembers();assert sum(m.size for m in members)<1024*1024*1024
                for m in members:assert pathlib.PurePosixPath(m.name).parts[0]=='jdk-21.0.12.1+1'
                archive.extractall(root/'.toolchains',filter='data')
        else:
            target=root/'.toolchains/gradle-8.11.1'
            if target.exists():continue
            with zipfile.ZipFile(path) as archive:
                assert sum(m.file_size for m in archive.infolist())<512*1024*1024
                for member in archive.infolist():
                    part=pathlib.PurePosixPath(member.filename);assert not part.is_absolute() and '..' not in part.parts and part.parts[0]=='gradle-8.11.1'
                    out=root/'.toolchains'/part
                    if member.is_dir():out.mkdir(parents=True,exist_ok=True)
                    else:out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(archive.read(member));out.chmod((member.external_attr>>16)&0o777 or 0o644)
    print('Verified/extracted Java 21.0.12.1+1 and Gradle 8.11.1; no JVM started')
if __name__=='__main__':main()
