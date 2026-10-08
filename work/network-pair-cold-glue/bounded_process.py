"""Run one owned build command and clean its new process group before returning."""
import os
from pathlib import Path
import signal
import subprocess
import time
from contextlib import contextmanager


@contextmanager
def owned_stops():
    """Record stops across spawn, handle assignment, wait and owned cleanup.

    This reuses the recovered native owner's record-only handler semantics.
    No signal mask is changed or inherited by the child. Ignored signals stay
    ignored; handled/default stop requests become failures after cleanup.
    """
    previous = {}
    pending = []
    failed = False
    def request(number, _frame):
        if not pending:
            pending.append(number)
    def check():
        if pending:
            raise InterruptedError('Owned command interrupted by '+signal.Signals(pending[0]).name)
    try:
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            old = signal.getsignal(number)
            if old != signal.SIG_IGN:
                previous[number] = old
                signal.signal(number, request)
        yield check
    except BaseException:
        failed = True
        raise
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        if not failed:
            check()

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
    process, failure, code = None, None, None
    deadline = time.monotonic()+timeout
    with owned_stops() as check_stop:
        try:
            check_stop()
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            while True:
                check_stop()
                remaining=deadline-time.monotonic()
                if remaining<=0:raise subprocess.TimeoutExpired(command,timeout)
                try:
                    code=process.wait(timeout=min(0.2,remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            # Single-use Gradle descendants must finish before the next JVM.
            until=min(deadline,time.monotonic()+5)
            while members(process.pid) and time.monotonic()<until:
                check_stop()
                time.sleep(0.1)
        except BaseException as error:
            failure=error
        finally:
            if process is not None:
                try:
                    if failure is not None or members(process.pid):stop_group(process)
                except BaseException as cleanup:
                    if failure is None:failure=cleanup
                    else:failure.add_note('Owned cleanup also failed: '+type(cleanup).__name__+': '+str(cleanup))
        if failure is not None:raise failure
        check_stop()
        return subprocess.CompletedProcess(command,code)
