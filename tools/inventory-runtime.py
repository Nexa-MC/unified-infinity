#!/usr/bin/env python3
"""Hash installed dependencies so an actual successful runtime can be reproduced."""
import hashlib,json,pathlib,sys
root=pathlib.Path(__file__).resolve().parent.parent
folder=root/sys.argv[1]
records=[{'path':str(p.relative_to(folder)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.rglob('*.jar'))]
out=root/'logs'/sys.argv[2];out.write_text(json.dumps({'scope':sys.argv[1],'artifacts':records},indent=2)+'\n');print(f'{len(records)} artifacts -> {out}')
