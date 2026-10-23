# Installed graphics producer glue

`prepare(repo_root, consumer_root)` stages the exact frozen portable2 collector and portable3 supervisor and writes a text-only plan. It does not manufacture an installed-input lock or runtime receipt. Lifetime-adjusted collector SHA-256 is `82283cb5b254f1102a6022b95433f38b6fccf9f99aa8b8f3abc004d9f2507946`; supervisor remains `01f3796c0d6e9c54a770375f0ae1cc3451a89074bb88934023f997f7c48dc1bf`.

Call `availability(plan)` before restoring public inputs. It only reads actual runner identity, Ubuntu release data and installed required tool/library paths, reporting exact missing inputs. It launches no process and does not claim package ownership has already been verified.

Call `execute(plan)` only after builds and pair assembly finish and the outer driver's exact future-CI policy admits execution. It records real Ubuntu/ImageVersion/machine observations, installed package versions/architectures, canonical ownership, file hashes and the dpkg database identity. Only trusted root-owned installed `dpkg-query` and `ldd` are invoked. `ldd` inputs must first have an unambiguous observed package owner and an ELF header. Dependencies include the real Xvfb and glxinfo binaries, Mesa GLX dispatch and software DRI driver. Ubuntu usrmerge aliases are accepted only when they resolve to the same actual canonical file. Missing/ambiguous inputs fail before any graphics child starts. No package installation, signed APT closure, downloads, JVM, namespace, host setting or security change is performed.

The producer writes bounded observed evidence and the existing `OBSERVED_INSTALLED_PACKAGES` receipt shape. The new lock is validated by the hash-pinned collector. It starts that collector only through its reviewed CLI. Genuine `ready.json` must identify the owned collector, then the unchanged supervisor rechecks its real live Xvfb, display and renderer receipt. The returned object contains `readyPath`, `readyPin`, `ready`, `observedInputs` and the in-process `handle`. Neither PIDs nor renderer/memory values are invented.

The driver retains that handle while running the two pairs in sequence, within the collector's shared 2,520-second lifetime. Its `finally` block first terminates and waits for any retained pair supervisor, then calls `stop(result['handle'])`. An unreaped pair prevents graphics teardown and acceptance. TERM, INT and HUP unwind through this same path. Cleanup errors are recorded in the final driver receipt while the original exception is preserved. Cleanup signals only the exact owned collector via pidfd and checks the collector's own lifecycle record. The frozen collector owns and cleans Xvfb. A cleanup timeout is an explicit failure; live ownership handles are retained instead of claiming cleanup or signaling imported PIDs.

Twelve source/mock graphics-runner tests passed, including lifetime-receipt consistency and preservation of primary errors when readiness or pidfd setup cleanup fails, as well as frozen source staging, no premature lock/receipt, early missing-input rejection without package/GL commands, dependency parsing, wrong-runtime rejection and exact-owned lifecycle cleanup. No package, native graphics, JVM, network, CI or game command was executed during this source task. Actual installed closure and graphics feasibility remain unobserved until future admitted CI.

The driver defers handled stop signals through `execute(..., interrupt_check=...)` and the returned handle assignment. The runner checks pending stops before creation and after it has retained ownership, and wraps all child creation, pidfd acquisition and readiness in one `BaseException` cleanup scope. Before a pidfd exists it terminates and waits only on its retained direct `Popen` child; any cleanup failure stays attached to the original error. Repeated signals cannot interrupt this cleanup or the driver final-receipt transition.


## Noble libc6 usrmerge metadata repair (2026-10-23)

`dpkg-query --search` emits diversion annotations separately from direct file owners.
The parser admits only the paired `libc6` annotation for
`/lib64/ld-linux-x86-64.so.2` to the same path plus `.usr-is-merged`, corroborated
by exactly one installed `/var/lib/dpkg/diversions` triple. The database and
ancestors must be root-owned and not group/world-writable, the read is bounded,
and its exact file hash is rechecked after observation. Malformed triples,
duplicate/conflicting paths, local or unrelated annotations, mismatched packages,
and missing metadata fail closed. The actual source alias must resolve to the
trusted canonical file, which independently needs a unique installed
`libc6:amd64` direct owner. An annotation never creates ownership. The protective
`--no-rename` destination need not exist. Existing canonical owner aliases, native
file hashes, root ownership/modes, Ubuntu runner and measured graphics gates remain.

Official references:
- https://git.launchpad.net/ubuntu/+source/glibc/plain/debian/debhelper.in/libc.preinst?h=ubuntu/noble
- https://git.launchpad.net/ubuntu/+source/dpkg/plain/src/query/main.c?h=ubuntu/noble
- https://manpages.ubuntu.com/manpages/noble/man1/dpkg-divert.1.html

The parser tests use text fixtures with the real local loader symlink resolution;
they do not claim an Ubuntu execution, renderer result, or game acceptance.
Both workflow copies allow 1,320 work seconds inside a 25-minute job, retaining
three minutes for cleanup. This is a bounded follow-up to the actual prior run's
successful restore/build/probe, not a change to build identity or expected hashes.
