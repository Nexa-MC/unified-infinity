# SPDX-License-Identifier: MIT
"""Small strict evidence/path contract shared by portable compile and validation."""
import json,math,os,pathlib,stat

def require(value,message):
 if not value:raise ValueError(message)

def canonical(path,root=None,kind='file',missing=False):
 raw=pathlib.Path(path);require('..' not in raw.parts,'parent traversal forbidden');p=raw.absolute()
 require(os.path.normpath(str(p))==str(p),'noncanonical path spelling')
 for ancestor in [*reversed(p.parents),p]:
  require(not ancestor.is_symlink(),'symlink path or ancestor forbidden: '+str(ancestor))
 if not missing:
  info=p.stat();require(stat.S_ISREG(info.st_mode) if kind=='file' else stat.S_ISDIR(info.st_mode),'nonregular input: '+str(p))
  require(p.resolve(strict=True)==p,'unredirected canonical path required')
 if root is not None:require(p.is_relative_to(root),'path outside declared consumer root')
 return p

def consumer_path(root,value,kind='file'):
 require(isinstance(value,str),'path must be a string');relative=pathlib.PurePosixPath(value)
 require(not relative.is_absolute() and '..' not in relative.parts,'consumer-relative path required')
 return canonical(root/relative,root,kind)

def no_aliases(paths):
 seen_paths=set();seen_files=set()
 for path in paths:
  require(str(path) not in seen_paths,'duplicate configured path alias');seen_paths.add(str(path));info=path.stat();identity=(info.st_dev,info.st_ino)
  require(identity not in seen_files,'duplicate configured hardlink alias');seen_files.add(identity)

def loads(data,max_bytes=3*1024*1024):
 if isinstance(data,str):data=data.encode()
 require(isinstance(data,bytes) and len(data)<=max_bytes,'JSON evidence size bound')
 def pairs(items):
  result={}
  for key,value in items:
   require(key not in result,'duplicate JSON key '+key);result[key]=value
  return result
 def invalid(value):raise ValueError('nonfinite JSON value '+value)
 def number(value):
  parsed=float(value);require(math.isfinite(parsed),'nonfinite JSON number');return parsed
 return json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid,parse_float=number)

def load(path,max_bytes=3*1024*1024):
 p=canonical(path);require(p.stat().st_size<=max_bytes,'JSON evidence size bound')
 return loads(p.read_bytes(),max_bytes)
