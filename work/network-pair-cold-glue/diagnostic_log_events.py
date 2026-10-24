"""Bounded allowlist-only extraction, not admission or absence-of-process evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat

MAX_LOG_BYTES=2*1024*1024
MAX_LINE_BYTES=512
COMMANDS={'LSHW','LSPCI','LSCPU','DMIDECODE','SLEEP_FIXTURE'}
CALLERS={'OSHI_EXECUTING_COMMAND_RUN_NATIVE','FIXTURE','OTHER'}
STATES={'STARTED','ACTIVE','DISABLED','STOPPED','EXPIRED','RECORD_LIMIT','EVENT_LIMIT','OUTPUT_LIMIT',
        'UNSUPPORTED_MANAGER','UNSUPPORTED_PROVIDER','UNSUPPORTED_LOGGER','UNSUPPORTED_FILTER',
        'DEBUG_ALREADY_ENABLED','SECURITY_RESTRICTION','ALREADY_OWNED','SETUP_FAILED','CAPTURE_FAILED'}
EVENT_KEYS={'kind','requested_command','caller','pid','diagnostic_only','admission_evidence'}
STATUS_KEYS={'kind','state','diagnostic_only','admission_evidence'}
MARKERS=(b'processbuilder_debug',b'processbuilder_diagnostic_status')

def unique_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate key')
        value[key]=item
    return value

def valid(row):
    if type(row) is not dict or row.get('diagnostic_only') is not True or row.get('admission_evidence') is not False:
        return False
    if row.get('kind')=='processbuilder_debug':
        return (set(row)==EVENT_KEYS and type(row['requested_command']) is str
                and row['requested_command'] in COMMANDS and type(row['caller']) is str and row['caller'] in CALLERS
                and type(row['pid']) is int and 1<=row['pid']<=2147483647)
    if row.get('kind')=='processbuilder_diagnostic_status':
        return set(row)==STATUS_KEYS and type(row['state']) is str and row['state'] in STATES
    return False

def extract(path):
    """Read at most 2 MiB; no malformed text or exception content leaves this function."""
    result={'schema':'bounded-process-diagnostic-log-v1','status':'UNOBSERVED',
            'diagnostic_only':True,'admission_evidence':False,'baseline_acceptance':False,
            'observation_complete':False,'absence_of_process_evidence':False,
            'log_pin':None,'events':[],'statuses':[],'malformed_rows':0,
            'overflow':False,'log_available':False,'log_changed':False}
    descriptor=None
    try:
        descriptor=os.open(Path(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        before=os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            result['status']='INVALID_OR_INCOMPLETE';return result
        result['log_available']=True
        if before.st_size>MAX_LOG_BYTES:
            result.update(status='INVALID_OR_INCOMPLETE',overflow=True);return result
        with os.fdopen(descriptor,'rb') as stream:
            descriptor=None
            payload=stream.read(MAX_LOG_BYTES)
            after=os.fstat(stream.fileno())
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(before)!=identity(after) or len(payload)!=before.st_size:
            result.update(status='INVALID_OR_INCOMPLETE',log_changed=True);return result
        result['log_pin']={'path':str(Path(path)),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        for line in payload.split(b'\n'):
            if not any(marker in line for marker in MARKERS):continue
            if len(line)>MAX_LINE_BYTES or not line.startswith(b'{') or not line.endswith(b'}'):
                result['malformed_rows']+=1;continue
            try:
                row=json.loads(line.decode('ascii'),object_pairs_hook=unique_object)
                accepted=valid(row)
            except (ValueError,TypeError,UnicodeError,RecursionError):accepted=False
            if not accepted:
                result['malformed_rows']+=1;continue
            key='events' if row['kind']=='processbuilder_debug' else 'statuses'
            cap=64 if key=='events' else 2
            if len(result[key])>=cap:result['overflow']=True
            else:result[key].append(row)
        if result['malformed_rows'] or result['overflow']:result['status']='INVALID_OR_INCOMPLETE'
        elif result['events'] or result['statuses']:result['status']='OBSERVED_INCOMPLETE'
    except (OSError,ValueError):
        result['status']='UNOBSERVED'
    finally:
        if descriptor is not None:os.close(descriptor)
    return result
