# Source-owned FML admission candidate

Read ../../docs/four-loader/pre-service-gate-implementation.md for design,
limitations and acceptance status. This directory is a source successor, never an
in-place patch to the accepted client. Keep the source archive, attribution and
LGPL license with any distribution.

Static checks (no JVM):

    python tools/check_source_candidate.py
    python tools/build_source.py --classpath-lock provenance/compile-classpath-lock.json

The build tool requires `--compile` to start one javac process. Use the existing
Java21 toolchain explicitly and only in a separately authorized build environment. It
refuses stale output and never launches Gradle or a game. A successful output has
an unapproved installation by default, so it cannot become a live runtime by
accident. Provide a reviewed installation policy only for a new sealed successor.

Before launch, use tools/validate_launch.py with a separately pinned build receipt.
That check is mandatory but not a metadata scan or permission to launch. The
source-owned existing launcher must invoke it before Popen; no active launcher
or profile has been changed here.
