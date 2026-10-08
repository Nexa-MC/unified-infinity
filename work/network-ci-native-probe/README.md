# Bounded NeoForge PLAY nonce probe

**SOURCE PREPARATION ONLY. Not compiled, launched, or accepted.** This directory
contains four source-owned production Java classes, prepared test source, build
metadata, schemas, provenance, and this license. No game, generated Minecraft
class, downloaded JAR, world, account credential, Gradle wrapper binary, or
runtime acceptance result belongs here.

The future diagnostic builds this probe once and uses the **identical JAR bytes**
in the native NeoForge and Unified client/server pairs. The pinned build is
NeoForge 21.1.219, Minecraft 1.21.1, ModDevGradle 2.0.140, Java 21 and Gradle 8.11.1.
It follows the existing `api-contract-controls/client-development/build.gradle`
binary-artifact preparation pattern, with no run configuration or launcher.
Use only the reviewed bootstrap's verified JDK/Gradle. The existing complete
strict dependency verification metadata is copied intact under `gradle/`.
Its sufficiency for this new build has not been demonstrated; unexplained
resolution failures must stop the build. This small source package does not itself
provide a cold-CI download closure. No selected Unified tuple hash is embedded.

## Observable operation

1. The common NeoForge mod registers required version-1 PLAY payloads named
   `network_control:request` and `network_control:reply`, using the pinned API's
   default main-thread handling. Requests have a positive nonzero signed long
   nonce and sequence 1; replies add counter 1. Their custom data is exactly
   12 and 16 bytes respectively. Both codecs reject short, long, out-of-range,
   and invalid-sequence payloads. There are no strings, paths or commands.
2. The client-only entrypoint installs its callback during client setup. The
   common class never imports, names, or eagerly binds a client class. The loader
   selects the extra `@Mod(..., dist = Dist.CLIENT)` entrypoint only on clients.
   The pinned FML 4.0.42 provider supports multiple entrypoints for one mod ID:
   it filters by the actual physical side and orders common entrypoints first.
   Both constructors receive the same mod container's event bus. The inspected
   provider, container, annotation and side-selection source hashes match the
   recorded original upstream 4.0.42 files; their hashes are in provenance.
3. The future official client command includes `--quickPlayMultiplayer
   127.0.0.1:25631` for native, or port 25632 for Unified, and exact offline
   `APILocal` / `dd29b97d-cafa-3d53-94e1-f85f75bcf1f6`. The probe reacts to the
   real `ClientPlayerNetworkEvent.LoggingIn`, checks the actual UUID and name,
   remote non-memory IPv4 loopback connection, configured port, client main
   thread and absence of an integrated server, then sends exactly once.
4. The server learns the nonce only from that PLAY request. Its handler checks
   the real `ServerPlayer`, UUID/name, instance of the dedicated server, main
   thread, protocol/direction, and real IPv4 loopback socket. One server-only
   counter changes 0 to 1. A duplicate request fails before a second mutation.
   The receipt records that mutation; `IPayloadContext.reply` carries it back.
5. The client checks the same actual connection, main thread, UUID/name, PLAY
   direction, matching nonce, sequence 1, counter 1 and exactly one reply.
   It records PASS, but remains joined until the supervisor captures live socket
   evidence and writes the fixed release file. Then it closes that connection,
   calls the normal client disconnect, verifies the real LoggingOut event refers
   to the closed connection, emits its disconnect marker and calls normal stop.

The server's `counter_before`/`counter_after` describe its authoritative mutation;
the client's same fields describe the observed expected operation and matching
reply. The client does not mutate a second authoritative counter. Per-run nonce
correlation belongs to the supervisor; a fresh positive 63-bit nonce is required
for each pair. This deliberately narrows the earlier feasibility plan's 128-bit
wording. It is a correlation value, not an authentication secret.

## Fixed files and closed schemas

Every fixture file is relative to the official profile's `FMLPaths.GAMEDIR`.
No property, environment variable or packet can change these names. The supervisor
must create fresh private profiles and reject existing outputs, temporary files,
symlinks, and any client input in the server profile. No credentials appear here.
Both fixture roles check both output names and temporary siblings during setup.
An old output is retained and a sticky FAIL marker is emitted; stale evidence is
never reused as this run's PASS. Output replacement is only allowed after the
current process has successfully created that role's result, to supersede PASS
with FAIL. The parent profile directory must remain private and supervisor-owned.

Client input: `network-control-input.json`, at most 128 bytes, exact ASCII form:

```json
{"schema":1,"nonce":123456789,"sequence":1,"port":25631}
```

The final LF is mandatory. Key order and spacing are exactly as above, with no
spaces. Nonce is 1 through 9223372036854775807, port is 25631 or 25632. Duplicate
keys, unknown keys, exponents, escaped values, non-ASCII, extra lines and overflow
are rejected. The input is only in the client profile.

Release: `network-control-release.json` in the client profile, at most 96 bytes:

```json
{"schema":1,"nonce":123456789,"sequence":1}
```

Again the exact form ends in LF and nonce must match. The supervisor writes it
only after matching both PASS files and live independent PID/socket observations.
It must publish this small file atomically. The probe never accepts commands.

Results: `network-control-client-result.json` or
`network-control-server-result.json`, at most 2048 bytes each. A fixed-name `.tmp`
sibling is created with CREATE_NEW and atomically moved into place. A sticky FAIL
can replace this process's earlier PASS; no subsequent PASS is allowed. A failure
writing a result leaves failure evidence on stdout. Missing files always fail.
Machine-readable metadata in `protocol-schema.json` defines exact key sets.

Each PASS explicitly records `phase: "PLAY"` and `flow: "SERVERBOUND"` (server)
or `flow: "CLIENTBOUND"` (client), using the enum values read from the actual
payload context after validating them. These are not inferred from the role.

Stdout markers, each followed by one space and compact one-line JSON:

- `NETWORK_CONTROL_READY`: server start event, exact fields schema, role, pid,
  start_ticks, port, main_thread, dedicated_server. This is not a round-trip PASS
- `NETWORK_CONTROL_JSON`: same bounded PASS/FAIL object as the result file
- `NETWORK_CONTROL_DISCONNECTED`: exact fields schema, role, pid, start_ticks,
  nonce, sequence, player_uuid, code, emitted only on observed expected logout

The marker stream writes directly to the supervised process's stdout descriptor,
so Minecraft's redirected `System.out` cannot add logging prefixes. Consumers
must match markers at column zero and reject malformed marker-prefixed rows.

PID uses `ProcessHandle.current()`. `start_ticks` reads Linux `/proc/self/stat`
field 22, not wall-clock time; the supervisor must independently match it. All
FAIL codes are fixed literals; exception messages and ambient data are excluded.
The client bounds join to 90 seconds after setup, reply to 20 seconds after send,
and release/logout to 15 seconds after its reply. The outer supervisor also owns
startup, process, save and shutdown deadlines, including hung game ticks.

## Future validation, not a present acceptance result

With the reviewed closure, `gradle --no-daemon --dependency-verification=strict
jar probeCodecTest` is the prepared build/test target. The Java test needs the
official compile/runtime classes and runs only when that later JVM work is
authorized. It tests actual codec boundaries, exact encoding, invalid lengths,
closed input parsing and nonce overflow without starting a game. It has not run.

Then the independently prepared supervisor must require distinct owned process
IDs/start ticks, the actual assigned loopback listener and connected sockets,
the same own-JAR hash in all four processes, both matching receipts, no failure,
the expected disconnect event, actual client exit, clean server save/stop and
both exit codes. A probe PASS alone is insufficient. The server keeps running
until the supervisor supplies its already-approved fixed save/stop commands.

Prepared game-negative cases remain unrun: duplicate request, duplicate reply,
wrong actual player, integrated server, memory connection, non-loopback address,
wrong thread, wrong nonce, early disconnect, stale result/release, missing or
mismatched release, and response timeout. The codec cannot prove dispatch/thread
or transport properties in an isolated test.

This tests the NeoForge PLAY API under native NeoForge and Unified. It makes no
Forge, Fabric or QSL API parity claim and no EMI recipe, backpack interaction,
tooltip, rendering, GPU performance, or broader real-mod acceptance claim. The
probe must be an explicit additional mod in each reviewed profile and seal.
