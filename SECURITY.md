# Security and sensitive reports

Unified Infinity is experimental. No supported production/security-maintenance
window is promised for the v6 research baseline. Dependency versions are pinned
for reproducible evidence, not a claim that they are free of known vulnerabilities.

Mod admission metadata is not an operating-system sandbox. Loaded mods and
native libraries can exercise the game process's privileges. Use trusted inputs,
a separate test instance and backups; keep authentication data outside test logs.

## Reporting

Do not open a public issue containing secrets, private server details, personal
data, or an unpublished exploit. If GitHub offers **Report a vulnerability** on
this repository's Security page, use that private route. Its availability is a
repository setting; this document does not claim it is enabled.

If that route is unavailable, ask a maintainer for a private reporting channel
before sending sensitive details. Do not assume an upstream project's security
inbox represents this fork. Ordinary non-sensitive bugs can use issues.

A report should identify the affected revision, prerequisites, impact and a
minimal reproduction with synthetic data. Do not test against someone else's
server or account without authorization. If a credential has been exposed,
revoke or rotate it through its provider; removing it from the latest commit
alone does not remove earlier Git copies.
