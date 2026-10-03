# M4 combined regression checkpoint

> Historical intermediate evidence. The accepted complete-source profile is documented in M5-FULL-SOURCE-ACCEPTANCE.md. Referenced historical binaries, raw logs and worlds are not included.

Target: Minecraft1.21.1 / Java21. No cross-version implementation is claimed.

## Newly verified combined intermediate binary
A fresh dedicated-server profile contains all three current components plus the exact
approved original Lithium Fabric0.15.4 JAR:
- Branded API host: e0fbbe9f5a101df29429719bfd171b5e56c55afdeefa027f39f5d1a72b35715b
- Experimental fixed core: 6acb0706519701e6816221a739e8f6d11d0bf280369ba87764b63f8345ef679c
- Preload provider: 7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99
- Unchanged Lithium:92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa

Both create/save and reopen/read runs passed, with scoreboard state read back and
normal exit. Full records: logs/combined-lithium-unified-{1,2}.json and logs.
The dedicated server remained loopback-only; the client-only branding/provider did
not open a window or interfere with this server run.

This is an INTERMEDIATE combined binary experiment. The complete Connector/FART/
Adapter source build is a separate task and does not inherit this runtime pass.
The official ModDevGradle binary-only pipeline avoids an unnecessary Minecraft
source decompile; its unchanged full Connector baseline now builds under the2GiB cap.

## Existing real client evidence
With core9a6e896e (before Lithium fixes), actual Minecraft reached the main menu,
showed Unified ∞ Infinity branding, retained Minecraft copyright and NeoForge
technical metadata, consumed actual loading stages, handed off the same GL window,
completed host reload and quit normally. This does not yet verify the fixed6acb
core or complete-source core in the client.

## Lithium repairs and limits
The source-reviewed experimental fixes repair parameter-annotation counts, inherited
interface/receiver lookup, and only safely unused/non-cancellable callback typing.
The original third-party JAR remains byte-identical.508 assertions and the failing
immutable-base control were recorded. Mixin safeguards stayed enabled.
Successful adapted candidates are not proof every configured Mixin path or gameplay
feature was exercised. No performance or universal-compatibility claim is made.
