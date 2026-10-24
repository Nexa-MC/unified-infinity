# Historical cold native/Unified network diagnostic

The execution overview below records the original144-file preparation. Its first publication and failed early preflight are preserved. Current successor identities, dependency repairs and execution limits are described in [COHERENT-PAIR-SUCCESSOR.md](../../COHERENT-PAIR-SUCCESSOR.md); historical counts below are not the successor closure.

This supersedes the earlier proposal's intentionally stopping preflight. The serial driver now contains the actual restoration, build, probe compilation, pair assembly, graphics handoff and supervisor invocations. It is prepared source, with successful Python-only staging checks. No cold download, JVM, graphics process, game, Git write or CI run has occurred during preparation. Publication remains paused and belongs to the reviewing publisher.

## API-independent fixed recovery round: 04:09–04:54 UTC

This separate source-only candidate does not use the public jobs API. The prior
job-anchored proof is preserved unchanged. It is not a retry or alternate access
route for that endpoint. The first step records only a local wall/monotonic
clock anchor, explicitly NOT actual job start or remaining platform job time.

Before checkout, the first step requires current UTC <= fixed cutoff minus the
36-minute job timeout and 300-second platform cancellation reserve. The job
necessarily began no later than this step. Therefore, if platform timeout and
cancellation/runner teardown behave as documented, their outer envelope cannot
exceed the fixed cutoff. The platform job is still one standard Ubuntu job,
36 minutes, $0 overage. This proof assumes trustworthy runner UTC and normal
platform behavior; it is not a hard independent kernel/process containment claim.

This candidate targets 24 October 2026 only. First-step admission is 04:09:00
through 04:13:00 UTC inclusive. Do not publish before 04:09:00: push triggers CI.
Queue delay makes no latest push time guaranteed; target the window opening.
Before publication recheck remote HEAD, all active runs, the existing zero-overage
guard and remaining time. Missing the admission window means no execution. No phase,
restart or rerun may replace the anchor or renew its deadline.

Local useful-work cutoff is the earlier of first-step capture plus 1,980 seconds
and round cutoff minus 300 seconds cancellation minus 180 seconds cleanup.
Preparation and execution consume the same immutable local lease. Admission
requires at least 1,560 seconds of that LOCAL lease, not a promise that the
platform job has that much time left. An earlier actual job start may cause
platform timeout before local work or graceful cleanup completes. Neither
1,560 useful seconds before job timeout nor 180 seconds of cleanup inside the
actual job is guaranteed or claimed.

The surviving driver watchdog requests owned cleanup at its work cutoff. The
pair's normal 600-second limit is clamped to the inherited driver cutoff. The
surviving graphics owner independently enforces work cutoff plus 90 seconds and
cleanup cutoff plus 180 seconds, using both clocks. Readiness and lifecycle must
echo those exact cutoffs. Clock rollback cannot give back monotonic time; a
forward wall movement expires the local lease earlier. Private same-boot anchor
identity and metadata checks are fail-closed.

Owned-handle cleanup remains bounded and tested. Abrupt SIGKILL of a controlling
owner can orphan children whose caller-side timer no longer runs; evidence I/O
and kernel-blocked operations are not universally contained by Python. Those
cases rely on standard runner teardown/platform cancellation. They must not be
reported as local cleanup success or independent all-descendant containment.
The existing platform memory safety gates, dependency/artifact hashes and
process ownership checks are not relaxed. No permissions, credentials,
additional runners, uploads or paid services are introduced.

Historical relative limits below describe the predecessor, not this fixed round.

## Execution path

1. `driver.py prepare` reconstructs the exact source candidate from four verified source-only archives, stages all runtime/build/config helpers, preserves the unchanged four probe classes and every resource/license, and writes consumer-local plans. A real integrated preparation succeeded with all 670 source records and 801 source/config files verified.
2. `driver.py run` first checks actual Ubuntu24 runner graphics availability. Missing installed Xvfb/glxinfo/Mesa inputs stop before the large downloads; it does not install packages or fabricate graphics evidence.
3. It restores 4,270 deduplicated official runtime/toolchain/asset records, then the 706 verified core build artifacts, four PRODUCT/QSL inputs, four pinned snapshot aliases and four approved original mods. Matching hashes reuse already restored bytes. Every download uses exact existing hashes, declared HTTPS origins, byte bounds and bounded retries. Repository-layout fallback URLs remain availability-unverified until the first cold run.
4. Five serial recipes extract the approved JDK/Gradle, run the official NeoForge client/server installers, export the genuine binary-only ModDev client recipe and seal it. Verification checks the exact 95-file server closure, 95 client classpath identities, four FML generated artifacts, two ModDev outputs, clean.jar and all 3,888 unique assets.
5. The full-module and matching PRODUCT build run offline through the preserved source recipe, pinned local repositories and strict Gradle verification. All build/installer descendants are capped at 512 MiB and one active processor/worker. The candidate identity and all four artifact hashes must equal the reviewed candidate; a mismatch stops for comparison.
6. Direct javac/java uses the already proven 192 MiB/one-CPU recipe to compile the unchanged probe and run its original 46 real codec/input assertions. The deterministic own JAR must match the existing `dbecc6c9…` reference. Both groups use that same exact JAR.
7. Fresh native and Unified profiles each contain exactly EMI, Sophisticated Core, Sophisticated Backpacks and the probe. NeoForge EMI is the native original; Fabric EMI is the Unified original. Complete accepted configs and original JAR bytes are preserved. The source-owned FML assembler validates Unified's single owner and 46 API archives / 47 logical IDs.
8. The graphics producer records the actual installed package versions/owners/file hashes, then invokes the frozen measured collector. Observed provenance never claims a verified signed archive chain. The collector supplies the live display/PID/renderer evidence; no placeholder qualifies.
9. Native and Unified run serially through the reviewed supervisor. Each pair has distinct server/client processes, real loopback ownership, typed PLAY nonce/direction/main-thread checks, authoritative server counter, disconnect, save and stop. Each game retains 1280 MiB / two CPUs. The unchanged pair gate is 3,758,096,384 bytes plus at least 256 MiB measured graphics reserve.

The fixed round uses the immutable first-step-anchored work cutoff described above, with a maximum local work lease of 1,980 seconds. Pair and graphics cutoffs cannot renew it. TERM, INT and HUP are deferred across collector creation, pidfd acquisition and the driver handle handoff; the collector runner checks for pending stops only where its cleanup owns the child. Repeated stop signals are deferred through cleanup and final reporting. All three signals trigger ordered cleanup: stop and wait up to 30 seconds for the retained owned pair supervisor before stopping the graphics collector (up to 20 seconds). If the pair cannot be reaped, graphics teardown is skipped and acceptance fails closed. Cleanup failures are recorded without replacing the original failure or suppressing the final receipt. The local lease reserves 180 seconds for ordered cleanup, but an earlier platform timeout can preempt it; this is not a promise of remaining job time. The driver prints text receipts and bounded failure/game log tails. There is no artifact upload, binary log encoding, Actions cache, secret use, paid service or larger runner. The single standard Ubuntu24 job has a 36-minute hard timeout and the first-step admission inequality retains five minutes for platform cancellation. The publisher must recheck the existing zero-dollar stop-spend guard before any authorized push/run; this source package does not reopen the earlier denied publication.

## Inputs versus untested execution

Source/config prerequisites are now concrete and verified locally. Every one of the 169 identity dependencies is covered by existing strict metadata and the supplemental core lock. Four complete source-only archives pass recursive binary exclusion. No official runtime URL/hash record is missing from the reconciled runtime lock. The same approved original mod bytes have explicit vendor URLs and hashes.

The remaining observations require a real authorized cold runner: current installed graphics availability, official fallback URL availability, successful offline/installer regeneration, and the actual native/Unified wire result. Missing graphics is an input condition; it is not permission to silently install unpinned packages. Cold failure must preserve its specific receipt/log and retain all original pins.

The new source code replaces the earlier missing orchestration rather than claiming it already executed. Existing historical build receipts remain separate; the pair adapter requires new runtime/build/probe receipts whose paths and logs belong to this consumer.

## Review surface

`network-pair.yml` is the concrete workflow source. The isolated publication tree contains it at `.github/workflows/network-pair.yml`, alongside a complete hash manifest. The existing deployment branch is exactly `diagnostic/network-pair-20261006-a`. Its first144-file version was published and ran; this successor has not been published or run. A future authorized update preserves that branch history by a normal fast-forward. There are no main/PR/fork/schedule triggers.

The earlier full-module/render candidate remains game-unverified. A successful automated pair would establish the NeoForge host's typed network control only. QSL/Forge facade wire integration, manual GUI/tooltips, EMI recipe interaction, backpack rendering and full API compatibility remain separate claims.
