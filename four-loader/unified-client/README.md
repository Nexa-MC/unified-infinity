# PASS: real four-loader client baseline

The frozen98core/746host/7bprovider baseline passed actual built-in Mods-screen identities, OP Tab19entries and level127 OP Sword, Farmer’s Delight block/container/recipe UI, local-world save/reopen, independent NBT checks, and graceful exit0. See `unified-client-acceptance.json` and `evidence/client-2/`. All8original JARs remain unchanged.

Accepted retry2 used the completed transform cache, official generated IDE-style launch,1536MiB heap/2processors, no resident Gradle, and a passing2GiB headroom gate. No new cgroup OOM kills occurred. Failed attempt1 and resource investigation remain preserved. This is scoped MC1.21.1 acceptance, not a universal compatibility claim.

Two UI findings remain intentionally unfixed in this frozen baseline: the fixed16:9 preload letterboxes a1180x812window, and the existing56-row list mixes bundled APIs with the five real user mods. The newer requested API summary-row/credits projection requires its own successor verification. Name filtering after scrolling also retained an offscreen scroll position until scrolled back to top.

Original launch/staging/profile provenance is under `evidence/`. The immutable profile lock retains its original staging-time labels; actual execution outcome is recorded in the acceptance report. The environment-key-name audit is read-only and separate; it cannot reconstruct historical values.
