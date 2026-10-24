"""Test-only exact reversal of rejected transition path labels."""
PREDECESSOR_SHA256 = 'e7e4bc4582081ff6cf48e2f223791a8019d9f615a6436ffd99329065ba3384d5'
REPLACEMENTS = [("        if target not in (str(helper), CPU_PROBE_PATH):\n            error = ValueError('CPU probe transition target forbidden')\n            # Path-label evidence from this existing readlink only, not inode identity.\n            deleted = target.endswith(' (deleted)')\n            label = target[:-10] if deleted else target\n            error.transition_target_diagnostic = {\n                'admission_evidence': False, 'identity_verified': False,\n                'path_label': 'PARENT_COMMAND_PATH' if label == command[0] else 'OTHER_PATH',\n                'deleted_suffix': deleted}\n            raise error\n", "        require(target in (str(helper), CPU_PROBE_PATH), 'CPU probe transition target forbidden')\n"), ("    if type(error) is ValueError and hasattr(error, 'socket_diagnostic'):\n        result['socket_diagnostic'] = error.socket_diagnostic\n    if type(error) is ValueError and hasattr(error, 'transition_target_diagnostic'):\n        result['transition_target_diagnostic'] = error.transition_target_diagnostic\n", "    if type(error) is ValueError and hasattr(error, 'socket_diagnostic'):\n        result['socket_diagnostic'] = error.socket_diagnostic\n")]

from peer_diagnostic_preservation import without_failed_peer_diagnostic

def without_transition_target_diagnostic(source):
    source = without_failed_peer_diagnostic(source)
    for reviewed, original in REPLACEMENTS:
        if source.count(reviewed) != 1:
            raise ValueError("Changed or duplicate transition target diagnostic block")
        source = source.replace(reviewed, original, 1)
    return source
