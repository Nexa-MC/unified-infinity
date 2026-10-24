"""Test-only exact normalization of the reviewed console capacity correction."""

CAPACITY_BLOCK = '# The sealed 95-entry Unified classpath produces a 20,072-byte JNA line.\n# Keep that complete diagnostic within a finite 32 KiB line envelope; the\n# 2 MiB process log, 2 KiB protocol JSON, and all capture checks are unchanged.\nMAX_LINE = 32 * 1024\n'
ORIGINAL_CAPACITY = "MAX_LINE = 16 * 1024\n"
PREDECESSOR_SUPERVISOR_SHA256 = 'c0bbb9713411dd4a0107608977a1bee47b2df711abd93a5bda55baae9d927746'

def without_console_capacity(source):
    """Remove only the exact comment/constant delta; no gate or parser rewrite."""
    if source.count(CAPACITY_BLOCK) != 1:
        raise ValueError('Expected exactly one reviewed console capacity block')
    if source.count('MAX_LINE = ') != 1:
        raise ValueError('Duplicate or changed console capacity assignment')
    return source.replace(CAPACITY_BLOCK, ORIGINAL_CAPACITY, 1)
