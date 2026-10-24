"""Test-only exact reversal of rejected PCI-query path categories."""

PREDECESSOR_SHA256 = 'cc3ef19dcefc5f96958830e85134813d37e437df073175c49a81892450cf064a'

ORIGINAL = """                'path_label': 'PARENT_COMMAND_PATH' if label == command[0] else 'OTHER_PATH',
"""

REVIEWED = """                'path_label': ('PARENT_COMMAND_PATH' if label == command[0] else {
                    '/usr/bin/lspci': 'PCI_QUERY_USR_BIN_PATH',
                    '/usr/sbin/lspci': 'PCI_QUERY_USR_SBIN_PATH',
                    '/bin/lspci': 'PCI_QUERY_BIN_PATH',
                    '/sbin/lspci': 'PCI_QUERY_SBIN_PATH'}.get(label, 'OTHER_PATH')),
"""


from socket_stage_preservation import without_socket_failure_stage

def without_official_path_diagnostic(source):
    source = without_socket_failure_stage(source)
    if source.count(REVIEWED) != 1:
        raise ValueError('Changed or duplicate rejected PCI-query path diagnostic block')
    return source.replace(REVIEWED, ORIGINAL, 1)
