> Current runtime evidence: [v6 acceptance](../docs/fusion-v6/README.md).
> The development results below are historical; they do not replace the v6 scope and source-continuity limits.

# Unified ∞ Infinity preload UI

An actual FML **4.0.42** `ImmediateWindowProvider`, pinned to **NeoForge 21.1.219 / Minecraft 1.21.1 / Java 21**. This is a local research prototype, not a published release.

## What is ours, and what is reused

The GLSL shader, scene geometry, icon integration, layout, text rasterization, animation, bounded telemetry reader, GLFW creation, render scheduling and context handoff are implemented here. No default NeoForge artwork, fox animation, font, shader, static render buffers or window initialization is invoked.

`InfinityWindowProvider` extends the public `DisplayWindow` type solely because the pinned `NeoForgeLoadingOverlay.newInstance` ABI requires it. It overrides every hook that that overlay calls. NeoForge's later reload-completion/fade lifecycle bridge and the installed LWJGL/GLFW/OpenGL platform are reused. This is **not** a newly written graphics driver or a fully independent Minecraft loading-overlay implementation.

The game-layer overlay class is resolved only from `updateModuleReads(GAME layer)`. The early provider never imports, scans or eagerly loads Minecraft/mod classes to derive progress.

## Build

Run `./build.sh` from any directory. It uses the existing pinned Java 21 toolchain and FML/Gson/SLF4J/jopt-simple jars in `../run/neoforge-native/libraries`. Three compile-only LWJGL 3.3.3 artifacts belong in `.deps/`; `fetch-dependencies.sh` retrieves/checks the official Maven Central artifacts. They are not included in the output JAR. The Minecraft 1.21.1 runtime supplies LWJGL.

Output: `build/libs/unified-infinity-preload-0.1.0-dev.jar`

The build runs native-free tests and writes `build/reports/headless-tests.txt`. They cover progress truthfulness, invalid/fractional/overflow counts, file size/staleness/sequence handling, throttling, typography/icon rendering, real FML SPI resolution, and server startup without native graphics or client classes.

## Install into an isolated client profile

Place the JAR directly in the profile's `mods/` directory, alongside the loader distribution. Its service descriptor causes FML 4.0.42 to load it into the SERVICE module layer; it is not a late `@Mod` entry point and must not be nested in a regular mod JAR.

In that profile's `config/fml.toml`, set:

    earlyWindowControl = true
    earlyWindowProvider = "unifiedinfinity"

Use a fresh **absolute, per-launch** telemetry path on both producer and client JVM:

    -Dunified.infinity.progressFile=/absolute/profile/run-id/progress.json

Optional: `-Dunified.infinity.reducedMotion=true` gives a stationary orbit, static indeterminate dots and a maximum 10 Hz render rate. Normal animation is capped at 30 Hz. Snapshot I/O is capped at 10 Hz in both modes. No continuous busy loop or per-mod rendering thread exists.

`-Dunified.infinity.headless=true` explicitly suppresses graphics. Dedicated-server launch targets are already routed to FML's dummy provider; direct server initialization of this provider is additionally a safe no-op. A headless Minecraft client cannot use a real window and receives an explicit error if it requests handoff.

Revert to `earlyWindowProvider = "fmlearlywindow"` before removing the provider JAR. FML 4.0.42 disables early display when a selected provider is absent; it does not silently substitute ours or the stock display.

## Progress contract

The source-loader writes an atomically replaced UTF-8 JSON object, at most 16 KiB:

    {"stage":"transform","status":"running","completed":4,"total":8,"elapsedMs":123,"sequence":7}

Stages: `discover`, `resolve`, `transform`, `commit`. Statuses: `running`, `complete`, `failed`. `completed` and `total` may be null. An optional `error` is an exception-type-only display label.

The UI displays the actual stage and real counts when known; no overall completion percentage is derived. Unknown denominators remain indeterminate. `commit/complete` means compatibility preparation completed, and explicitly waits for Minecraft. The existing NeoForge reload lifecycle closes the scene only after the host reload really finishes. A missing, stale, oversized, malformed or regressing-sequence snapshot preserves the last valid observation and never aborts loader startup.

A single reused snapshot path across launches is discouraged: files modified more than two seconds before UI construction are rejected, but a unique run path is the robust stale-run boundary.

## Native smoke harness

`./native-harness.sh` requires a real graphical display and the three official LWJGL Linux native artifacts in `.deps/`. Launch it in the cloud desktop terminal, not a display-less shell. It opens the actual provider, verifies same-window GL-context handoff on the main thread, keeps rendering after handoff, and cleans up without Minecraft. It **never emits synthetic loader progress**, downloads Minecraft, authenticates, or connects to any server.

Set `PROGRESS_FILE` to a fresh real source-loader snapshot to observe actual stage events. With no source-loader process it truthfully shows "Waiting for loader events". Headless unit test event fixtures are never presented as a real loading run.

This harness is not an end-to-end Minecraft test. Actual NeoForge GAME-layer overlay creation, resource reload, fullscreen transitions, macOS/Windows and physical GPU behavior require separate client verification. Cloud native testing uses Mesa llvmpipe, a software renderer.

## Source contract evidence

The exact published 4.0.42 source JARs and installed bytecode were inspected, not inferred from current main-branch APIs:

- https://maven.neoforged.net/releases/net/neoforged/fancymodloader/loader/4.0.42/loader-4.0.42-sources.jar
- https://maven.neoforged.net/releases/net/neoforged/fancymodloader/earlydisplay/4.0.42/earlydisplay-4.0.42-sources.jar
- https://github.com/neoforged/FancyModLoader/blob/4.0/loader/src/main/java/net/neoforged/neoforgespi/earlywindow/ImmediateWindowProvider.java
- https://github.com/neoforged/FancyModLoader/blob/4.0/loader/src/main/java/net/neoforged/fml/loading/TransformerDiscovererConstants.java
- https://github.com/neoforged/NeoForge/blob/1.21.1/src/main/java/net/neoforged/neoforge/client/loading/NeoForgeLoadingOverlay.java

The critical contract is that rendering must stop using the background context before `setupMinecraftWindow` returns the existing GLFW handle. A lock serializes the final background frame with handoff, pending frames observe `handedOff`, and the startup thread reacquires the context. No game-owned window is destroyed in the later `close()` callback.

## Icon

`assets/original.svg` is the supplied source, preserved unchanged. The derived transparent SVG removes the outer badge/background/decorative pixels while retaining the cube/infinity artwork. Stale source provenance/signature metadata was removed only from the edited derivative; it is not represented as a signed original. A 256-pixel derivative is embedded as `/infinity-icon.png`.

## Opt-in actual-client QA evidence

`-Dunified.infinity.qaDirectory=/absolute/path/to/a/fresh/qa-directory` enables diagnostic capture. Leave it unset for normal use: no capture directory, file I/O or frame exports occur. When enabled, the provider saves at most 16 actual framebuffer images, once per real observed source-stage/status and for actual GAME overlay events. `lifecycle.jsonl` binds source frames to the exact snapshot sequence/counts and records initialization, context handoff, GAME overlay construction, host reload success/failure and render-resource closure. Missing source events never generate invented stage captures.

These captures are native framebuffer evidence, not evidence of reaching Minecraft's main menu by themselves. Pair them with the actual game log and CUA screen observation. Capture I/O makes QA runs unsuitable for normal loading-performance comparisons.

The native harness also supports `./native-harness.sh --reduced-motion`. It checks that two real framebuffer exports four seconds apart are byte-identical while no loader event occurs. This tests stationary reduced-motion presentation without fabricating progress.

## Verified client integration and branding

The official ModDevGradle `forgeclientdev` launch reached the actual Minecraft
1.21.1 main menu with 49 mods. Source snapshots, same-window context handoff,
NeoForge GAME-overlay rendering, successful resource reload and renderer cleanup
were verified together. The first development attempt exposed Connector's
supported `connector.clean.path` requirement; exporting NFRT's official
`vanillaDeobfuscated` artifact resolved it without changing Connector code.

The final host bundle includes narrow client-only main-menu/window-title hooks
under `runtime-bundle/src/client-branding`. Actual main-menu branding is
`Unified ∞ Infinity (49 mods)` and the window title is
`Unified ∞ Infinity | Minecraft 1.21.1`. Minecraft's copyright and NeoForge
21.1.219 in the Mods technical view were visually verified as preserved.

See `reports/verification.json` and `reports/final-handoff.json` for exact hashes,
Library evidence identifiers, test scope and remaining untested environments.
The optional `--animation` native harness capture records real framebuffer
samples; `tools/encode_animation.py` encodes them into a GIF with measured
capture timing and no interpolated frames or synthetic loader progress.
