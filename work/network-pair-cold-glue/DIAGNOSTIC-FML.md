# Independent hardware-inventory-skip diagnostic FML

This separately named behavioral diagnostic extends the earlier observation-only FML, with explicit user approval on 2026-10-24. An official ModLauncher ILaunchPluginService targets only the exact hardware-collection lambda in net.minecraft.SystemReport, before class definition. A structural mismatch fails closed. It does not add a javaagent, alter operating-system permissions, or relax process/socket/identity admission.

All SystemReport instances in this diagnostic run omit hardware inventory entries, including later crash reports, not only the first startup report. Other report fields and game/mod/network code are retained. This is deliberately not original-game or original-loader acceptance. Original game JARs, baseline FML artifacts and input locks remain untouched.

Local bytecode verification uses the locked official obfuscated SystemReport class explicitly remapped with the official names. It is not observation of the generated NeoForge named game class. The actual CI-generated class must independently satisfy the transformation guard at runtime; local tests cannot claim that gate passed.

Opt-in only: driver --diagnostic-fml requires the unchanged refreshed full-build profile/proof. The ordinary build and original assembly complete and remain intact before this diagnostic overlay. No original artifact lock, baseline tuple, or accepted runtime receipt is replaced.

The native and Unified unconfigured FML derivatives replace exactly CommonLaunchHandler and its compiler-generated local record, add reviewed diagnostic classes and one explicit metadata resource, and append exactly one hardware-skip provider to the existing official launch-plugin service descriptor, and preserve every other original entry payload/metadata. Both bases are pinned separately. The Unified exact unapproved installation placeholder remains until a fresh configured BOOT is generated for each diagnostic role; the original source-owned argument/policy validator checks the resulting paths, digest, owners and API closure. The diagnostic configured receipt does not claim an unchanged full-source compilation.

A permanent rejecting JUL filter captures only fixed requested-command/caller enum labels and bounded PID. It is installed after FML preLaunch returns and before the ServiceRunner invoking Minecraft Main. No javaagent, global JUL config replacement, handler removal, or system/socket permission changes occur. Capture is bounded to30seconds/256records/64events/16KiB plus two small status lines. Trusted frozen JUL configuration is required. Foreign throwable decoding may block its caller; stack shape/depth rejection may lose observations. A blocked stdout sink can retain a daemon until JVM termination; final output can be lost. No event is executable identity or process-admission evidence.

Diagnostic paths:
- work/process-start-hardware-skip-diagnostic-fml: two derivative artifacts, source/compile receipts and manifest.
- work/network-pair-assembled-hardware-skip-diagnostic: four fresh role copies, policies and receipts.
- work/api1/ci/pair-seals-process-diagnostic: executable diagnostic seals.
- Driver diagnostic-fml-* results and runtime-evidence-diagnostic-fml logs.
The existing serial-pair.lock and original process/socket/identity/dwell/nonce/deadline gates remain unchanged. Only options.txt uses the already-existing mutable-client contract after initial exact copy.

Supervisor raw receipts carry the exact diagnostic manifest identity and false baseline acceptance. Driver never promotes derivative transport PASS into gameAcceptance, baselineAcceptance or fullApiCompatibility. Early safe diagnostic rows are separately extracted from bounded logs, so the usual32KiB log tail cannot hide them. Missing capture is UNOBSERVED, not absence of a process; observation_complete and admission_evidence always remain false.

Verification distinction: real pinned Java21 compilation and harmless child tests validate filter/drain/module routing; portable native derivative compilation reproduces exact class hashes. Four-role wiring tests use synthetic archives and mocked full-build/complete-validator evidence, with one test exercising the actual pinned assembler.prepare path/digest logic. Full real Unified derivative/configuration and game behavior remain unexecuted locally and require the bounded cold CI. Historical absent fixtures are reported separately, not passes.

Conditional next round is 2026-10-24T16:09:00Z through 16:54:00Z, only after the candidate passes review and preflight. Publication cannot precede 16:09; first-step admission must be no later than 16:13. Job timeout 36 minutes plus 5 minutes cancellation reserve must fit the fixed cutoff; first-step time is not job-start time. Earlier platform timeout can preempt cleanup; existing standard-runner teardown is the fallback, not a guarantee of autonomous cleanup after SIGKILL. No separate dispatch or duplicate job, and no JAR upload.
