"""Immutable in-memory records returned by a future live owner, never reconstructed from journals."""
from dataclasses import dataclass
@dataclass(frozen=True)
class OwnerBinding:
 schema:int
 run_id:str
 owner_pid:int
 child_pid:int
 process_group:int
 session:int
 receipt_path:str
 journal_sha256:str
 journal_bytes:int
 terminal:bool
 cleanup_qualified:bool
 remaining_members:tuple
 status:str
 command_succeeded:bool
@dataclass(frozen=True)
class OwnedCompletion:
 args:tuple
 returncode:int
 owner_binding:OwnerBinding
