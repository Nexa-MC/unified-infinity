#!/usr/bin/env python3
"""Fail closed unless all four real runs and unchanged input identity agree."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"id": "infinity_registry_probe:test_item", "count": 7, "Slot": 0}
PROBE = "infinity-registry-probe-0.1.0.jar"
fixture = ROOT / "registry-probe/build" / PROBE
fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
runs = {}
failures = []
for loader in ("native", "unified"):
    for stage in ("create", "reopen"):
        tag = f"registry-{loader}-{stage}"
        try:
            report = json.loads((ROOT / "logs" / (tag + ".json")).read_text())
            assert report["passed"] is True, report.get("error", "Run failed")
            assert report["input_mod_sha256"][PROBE] == fixture_sha, "Input fixture SHA mismatch"
            assert report["registration_positive_marker"] is True
            assert report["fabric_server_started_positive_marker"] is True
            assert report["save_flush_acknowledged"] is True
            assert report["all_dimensions_saved"] is True
            assert report["exit_code"] == 0
            assert report["persisted_item_after_stop"] == EXPECTED
            if stage == "reopen":
                assert report["persisted_item_before_start"] == EXPECTED
                assert not any(command.startswith(("setblock", "item replace")) for command in report["commands"]), "Reopen must not recreate the item"
            runs[tag] = {"passed": True, "report": f"logs/{tag}.json", "log": f"logs/{tag}.log"}
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            failures.append(f"{tag}: {type(exc).__name__}: {exc}")
result = {"passed": not failures, "fixture_sha256": fixture_sha,
          "semantic_parity": EXPECTED if not failures else None, "runs": runs, "failures": failures,
          "coverage": ["Minecraft 1.21.1 / Java 21", "direct intermediary bytecode item registration and identity lookup",
                       "Fabric SERVER_STARTED callback", "chest stack creation by real console commands",
                       "save flush and clean process stop", "independent persisted region-NBT read",
                       "restart and console-NBT lookup without recreating the stack", "identical original fixture JAR in both loaders"],
          "not_covered": ["third-party mod corpus", "client/render/input", "player login/network compatibility",
                          "arbitrary registries or content", "every lifecycle event", "performance", "universal compatibility"]}
(ROOT / "logs/registry-parity-summary.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["passed"] else 1)
