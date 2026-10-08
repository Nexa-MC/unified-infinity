"""Run one owned build command and clean its new process group before returning."""
import os
from pathlib import Path
import signal
import subprocess
import time

def members(group):
    result=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==group and fields[0] not in ('Z','X'):
                result.append((int(path.name),int(fields[3]),path.stat().st_uid))
        except (FileNotFoundError,ProcessLookupError):continue
    return result

def stop_group(process):
    """Only the fresh session/group created by this exact Popen is selected."""
    for sig,budget in ((signal.SIGTERM,8),(signal.SIGKILL,8)):
        alive=members(process.pid)
        if not alive:break
        if any(session!=process.pid or uid!=os.geteuid() for _,session,uid in alive):
            raise RuntimeError('Owned build group identity changed; no signal sent')
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        deadline=time.monotonic()+budget
        while members(process.pid) and time.monotonic()<deadline:time.sleep(0.1)
    process.wait(timeout=3)
    if members(process.pid):raise RuntimeError('Owned build descendants survived bounded cleanup')

def run(command,*,cwd,env,stdout,stderr,timeout):
    if timeout<=0:raise TimeoutError('Build time budget expired before spawn')
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
    try:
        code=process.wait(timeout=timeout)
    except BaseException:
        stop_group(process)
        raise
    # Gradle --no-daemon may briefly finish its single-use daemon after the
    # launcher exits. No next JVM phase starts until this owned group is empty.
    until=time.monotonic()+5
    while members(process.pid) and time.monotonic()<until:time.sleep(0.1)
    if members(process.pid):stop_group(process)
    return subprocess.CompletedProcess(command,code)
