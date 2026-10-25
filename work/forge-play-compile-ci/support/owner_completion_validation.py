"""Bind a future live owner completion to its exact terminal journal.
Not a forensic tool for an earlier process, and not a host-wide teardown certificate.
"""
from pathlib import Path
import hashlib,json,os,re,stat
from owner_completion_model import OwnerBinding,OwnedCompletion
MAX_JOURNAL_BYTES=256*1024

def _object_without_duplicates(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError('Duplicate JSON key')
  result[key]=value
 return result

def validate_completion(path,completion,command,error_present=False):
 result={'qualified':False,'reason':'UNVALIDATED','scope':'Live owner completion only; not historical or host-wide cleanup.'}
 try:
  if error_present:raise ValueError('Outer owner/compile failure')
  if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):raise ValueError('Invalid expected command')
  if type(completion) is not OwnedCompletion or type(completion.args) is not tuple or completion.args!=tuple(command) or type(completion.returncode) is not int or completion.returncode!=0:raise ValueError('No matching successful live child completion')
  record=completion.owner_binding
  if type(record) is not OwnerBinding or type(record.schema) is not int or record.schema!=1:raise ValueError('Missing immutable live owner binding')
  if not (record.terminal is True and record.cleanup_qualified is True and type(record.remaining_members) is tuple and record.remaining_members==() and record.status=='CHILD_EXITED' and record.command_succeeded is True):raise ValueError('Live owner itself did not report successful cleanup/completion')
  binding={'schema':record.schema,'runId':record.run_id,'ownerPid':record.owner_pid,'childPid':record.child_pid,'ownedProcessGroup':record.process_group,'ownedSession':record.session,'ownerReceipt':record.receipt_path,'journalSha256':record.journal_sha256,'journalBytes':record.journal_bytes}
  for key in ['ownerPid','childPid','ownedProcessGroup','ownedSession','journalBytes']:
   if type(binding.get(key)) is not int or binding[key]<=0:raise ValueError('Invalid live binding field: '+key)
  if binding['journalBytes']>MAX_JOURNAL_BYTES:raise ValueError('Live journal exceeds the supported bound')
  if binding['ownerPid']!=os.getpid():raise ValueError('Binding belongs to a different Python owner')
  if not binding['childPid']==binding['ownedProcessGroup']==binding['ownedSession']:raise ValueError('Live group/session mismatch')
  if not re.fullmatch('[0-9a-f]{32}',binding.get('runId','')):raise ValueError('Missing per-run identity')
  if not re.fullmatch('[0-9a-f]{64}',binding.get('journalSha256','')):raise ValueError('Missing emitted-byte hash')
  p=Path(path)
  if str(p.absolute())!=binding.get('ownerReceipt'):raise ValueError('Unexpected owner journal path')
  # Do not follow a replaced final-path symlink. All parent directories belong to the fresh task.
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  try:
   info=os.fstat(fd)
   if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_JOURNAL_BYTES:raise ValueError('Not a bounded regular journal')
   with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(MAX_JOURNAL_BYTES+1)
  finally:os.close(fd)
  observed=hashlib.sha256(raw).hexdigest();result.update(observedSha256=observed,observedBytes=len(raw))
  if len(raw)!=binding['journalBytes'] or observed!=binding['journalSha256']:raise ValueError('Journal differs from bytes emitted by live owner')
  data=json.loads(raw.decode('utf-8'),object_pairs_hook=_object_without_duplicates)
  if not isinstance(data,dict) or type(data.get('schema')) is not int or data.get('schema')!=2:raise ValueError('Unexpected journal schema')
  for key in ['runId','ownerPid','childPid','ownedProcessGroup','ownedSession']:
   if data.get(key)!=binding[key] or type(data.get(key)) is not type(binding[key]):raise ValueError('Wrong owner identity field: '+key)
  if data.get('command')!=command:raise ValueError('Wrong command')
  if type(data.get('childReturnCode')) is not int or data['childReturnCode']!=completion.returncode:raise ValueError('Wrong child result')
  if not all(data.get(key) is True for key in ['terminal','cleanupQualified','childSpawned','commandSucceeded']):raise ValueError('Incomplete or unsuccessful terminal ownership')
  if data.get('status')!='CHILD_EXITED' or data.get('remainingOwnedMembers')!=[]:raise ValueError('Owner did not finish cleanly')
  if data.get('stopRequested') or 'failure' in data or 'cleanupError' in data:raise ValueError('Stop/failure cannot qualify as command success')
  result.update(qualified=True,reason='EXACT_LIVE_OWNER_JOURNAL',ownerIdentity={k:binding[k] for k in ['runId','ownerPid','childPid','ownedProcessGroup','ownedSession']})
 except (AttributeError,KeyError,OSError,TypeError,ValueError,UnicodeError) as e:result['reason']=str(e)
 return result
