# Genuine Quilt/QSL server control

## Verified result

**PASS:** fresh create-3 (26.186s) and same-world reopen-2 (13.315s), both exit 0. The identical original probe SHA256 `f420e2021563d25931f1783f5a5744943dfbafc7557ae5c52ff2090331066b04` passed all eight exact-once stages. The registry/provider/resource and original-source assertions passed; genuine QSL READY/END/STOPPED and own Mixin ticks passed; reopen required the marker before any write, and independent NBT reads passed before/after. See `native-control-summary.json` and the exact log/JSON pair under `logs/`. The game runtime is stopped.

The isolated host could not resolve the Mojang public-key endpoint; `online-mode=true` remained enabled, and no player account/authentication or network-join claim is made. This does not affect the tested dedicated-server lifecycle and persistence path.

This harness validates the project-owned Quilt-only fixture on official Quilt Loader 0.30.1 and Minecraft 1.21.1, using the two unchanged QSL 10.0.0-alpha.5+1.21.1 modules (`qsl_base` and `lifecycle_events`). It never uses the Unified adapter, a second API implementation, or OP Tab.

## Vendor provenance

- Installation uses the official Quilt 0.15.1 installer and its supported server CLI: https://quiltmc.org/en/install/server/
- Exact metadata: https://meta.quiltmc.org/v3/versions/loader/1.21.1/0.30.1/server/json
- Installer and each installed dependency are checked against official Maven checksum sidecars. The game JAR is reused only after checking the official Minecraft manifest SHA1.
- `provenance/` contains retrieved responses, exact URLs, and local SHA256 records. `native-environment-lock.json` is created only after the complete official install verifies.
- Quilt meta currently reports SHA1/SHA256/SHA512 of the checksum **text**, rather than of the Loader JAR bytes. All three reproduce exactly. The official Maven checksum sidecar verifies the original Loader JAR as SHA256 `a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb`; the harness records this discrepancy instead of silently accepting the wrong digest.
- Quilt Loader and QSL are Apache-2.0 according to the official repository/module metadata and sources. The probe is project-owned MIT. Minecraft remains proprietary and is used only under the previously approved local-test EULA; none of these artifacts is published here.

## Isolation and execution

The dedicated server binds to 127.0.0.1:25621, keeps `online-mode=true`, enforces an empty whitelist, and disables RCON, query, and status. It has no LAN advertiser and uses no accounts or account tokens. Coordinate the single game-runtime slot before launching. No installer retry is allowed after a second authorization denial.

1. `python four-loader/quilt-native-control/prepare_native.py` installs the exact official runtime without launching Minecraft
2. `python four-loader/quilt-native-control/pin_native.py --probe-sha256 <confirmed-fixture-hash>` independently verifies official checksums, stages exactly three authorized mod JARs, and writes the immutable environment lock
3. `python -m unittest discover -s four-loader/quilt-native-control -p 'test_*.py' -v`
4. After runtime-slot approval, `python four-loader/quilt-native-control/run_native.py --phase create --runtime-slot-approved`
5. After create succeeds, use `--phase reopen` with the same world and fixture

The run harness waits for both vanilla readiness and the fifth genuine QSL END tick with the own Mixin sentinel. It requests `save-all flush`, waits for the console acknowledgment, then requests `stop`. It checks one occurrence of every expected stage, ordering, original source identity/hash, no client initializer on the server, successful shutdown, and independently reads bounded compressed Minecraft SavedData after exit. Reopen also performs an independent read before launch, and the fixture requires the persisted marker before writing.

Evidence belongs in `logs/native-{create,reopen}-{attempt}.{log,json}`. Each attempt requires a new evidence filename. No existing world or prior evidence is deleted. A passing native control proves the fixture's native expectations, not Unified compatibility or support for arbitrary Quilt mods.

## Initial finding

Attempt create-1 (original fixture SHA256 `a364850812d3d519087263d71a83a0a8c8db3387673d847ce665111ca5b33d24`) failed before class definition or world creation. Its Mixin configuration reserved the ordinary entrypoint package `dev.infinity.quiltprobe.*`, causing genuine Mixin `IllegalClassLoadError`. This is a fixture defect, not a Unified failure. The fixture owner is responsible for separating the Mixin package and returning a new immutable hash. Original failure evidence is preserved.

The next create-2 run passed all stages and independently verified saved NBT. Reopen-1 failed because the original `SavedData.Factory` supplied null `DataFixTypes`; vanilla 1.21.1 dereferences that value when loading existing data. The correct saved marker remained byte-identical on disk. This second fixture-only correction uses vanilla `SAVED_DATA_COMMAND_STORAGE` (`class_4284.field_45077`) for same-version DataVersion 3955; it makes no cross-version DFU claim. The old world and runtime lock are archived, and the new immutable probe is tested in a fresh pair.
