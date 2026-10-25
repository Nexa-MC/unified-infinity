"""Separate future owner: file cancellation, bounded group cleanup, atomic durable journal.
Never use tool/session interruption as a qualified cancellation; hard termination or filesystem failure may prevent finalization. Stops are sampled after wait and after cleanup; our signal-recording window closes before the final sample and durable terminal write.
"""
from pathlib import Path
import datetime,json,os,signal,subprocess,time,hashlib,uuid
import bounded_process
from owner_completion_model import OwnerBinding,OwnedCompletion

def atomic_json(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_name(path.name+'.tmp-'+str(os.getpid()))
 encoded=(json.dumps(value,indent=2)+'\n').encode('utf-8')
 with temporary.open('xb') as f:
  f.write(encoded);f.flush();os.fsync(f.fileno())
 os.replace(temporary,path)
 fd=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return {'sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded)}

def run(command,*,cwd,env,stdout,stderr,timeout,cancel_file,owner_receipt):
 if type(command) not in (list,tuple) or not command or not all(type(arg) is str for arg in command):raise ValueError('Explicit nonempty string command sequence required')
 command=tuple(command)  # One immutable dispatch snapshot, also used by every journal and completion.
 if timeout<=0:raise TimeoutError('Budget expired before spawn')
 cancel_file=Path(cancel_file);owner_receipt=Path(owner_receipt)
 if owner_receipt.exists():raise FileExistsError('Fresh owner receipt required')
 now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
 state={'schema':2,'runId':uuid.uuid4().hex,'ownerPid':os.getpid(),'startedUtc':now(),'command':command,'timeoutSeconds':timeout,'cleanupReserveSeconds':25,'cancelFile':str(cancel_file),'status':'PREPARED','cleanupQualified':False,'childSpawned':False,'namespaceScope':'Owning Python process namespace only; not a host-wide process claim.'}
 atomic_json(owner_receipt,state)
 pending=[];previous={};process=None;failure=None;code=None;deadline=time.monotonic()+timeout
 def note_signal(number,frame):
  if not pending:pending.append(number)
 for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
  old=signal.getsignal(number)
  if old!=signal.SIG_IGN:previous[number]=old;signal.signal(number,note_signal)
 def cancellation_check():
  if pending:raise InterruptedError('Owner received '+signal.Signals(pending[0]).name)
  if cancel_file.exists():raise InterruptedError('Owner observed task-specific cancellation file')
 try:
  cancellation_check()
  process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
  state.update(childSpawned=True,childPid=process.pid,ownedProcessGroup=process.pid,ownedSession=process.pid,status='RUNNING')
  atomic_json(owner_receipt,state)
  while True:
   cancellation_check();remaining=deadline-time.monotonic()
   if remaining<=0:raise subprocess.TimeoutExpired(command,timeout)
   try:code=process.wait(timeout=min(0.1,remaining));break
   except subprocess.TimeoutExpired:pass
  cancellation_check()
  state['status']='CHILD_EXITED'
 except BaseException as e:
  failure=e;state['status']='TIMED_OUT' if isinstance(e,subprocess.TimeoutExpired) else ('CANCELLED' if isinstance(e,InterruptedError) else 'FAILED')
  state['failure']=type(e).__name__+': '+str(e)
 finally:
  state['cleanupStartedUtc']=now()
  try:
   if process is not None:
    if process.poll() is None or bounded_process.members(process.pid):bounded_process.stop_group(process)
    else:process.wait(timeout=3)
    survivors=bounded_process.members(process.pid)
    state.update(childReturnCode=process.returncode,remainingOwnedMembers=survivors)
    if survivors:raise RuntimeError('Owned group still has live members')
   else:state['remainingOwnedMembers']=[]
   state['cleanupQualified']=True
  except BaseException as e:
   state['cleanupQualified']=False;state['cleanupError']=type(e).__name__+': '+str(e)
   if failure is None:failure=e
   else:failure.add_note(state['cleanupError'])
  # Close our signal-recording window before the final pending-stop sample.
  # A stop captured during wait or cleanup must never become command success.
  for number,old in previous.items():signal.signal(number,old)
  state['stopRecordingClosedUtc']=now()
  state['cancellationAcceptanceBoundary']='Final stop/file sample after cleanup and restored signal handlers, before terminal publication.'
  try:cancellation_check()
  except InterruptedError as e:
   state['stopRequested']=True;state['stopReason']=str(e)
   if failure is None:failure=e;state['status']='CANCELLED';state['failure']=type(e).__name__+': '+str(e)
   else:failure.add_note('Stop was also requested: '+str(e))
  if not state['cleanupQualified'] and state['status']=='CHILD_EXITED':state['status']='CLEANUP_FAILED'
  state['commandSucceeded']=failure is None and code==0
  state['finishedUtc']=now();state['terminal']=True
  emitted=atomic_json(owner_receipt,state)
 if failure is not None:raise failure
 # Bind the owner's own final state and emitted bytes, never a journal reread.
 binding=OwnerBinding(schema=1,run_id=state['runId'],owner_pid=state['ownerPid'],child_pid=state['childPid'],process_group=state['ownedProcessGroup'],session=state['ownedSession'],receipt_path=str(owner_receipt.absolute()),journal_sha256=emitted['sha256'],journal_bytes=emitted['bytes'],terminal=state['terminal'],cleanup_qualified=state['cleanupQualified'],remaining_members=tuple(tuple(row) for row in state['remainingOwnedMembers']),status=state['status'],command_succeeded=state['commandSucceeded'])
 return OwnedCompletion(tuple(command),code,binding)

from owner_completion_validation import validate_completion
