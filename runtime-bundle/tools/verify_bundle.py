#!/usr/bin/env python3
"""Structural verification only: never loads or executes a mod's bytecode."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tomllib
import zipfile

FFAPI_VERSION = "0.116.7+2.2.1+1.21.1"
FFAPI_SHA256 = "f66cf2e5604053ae073652c4baf93721173f06560bf93458d427341f13892690"
JARJAR_METADATA = "META-INF/jarjar/metadata.json"
MOD_METADATA = "META-INF/neoforge.mods.toml"


def safe_archive_path(value: str) -> bool:
    return bool(value) and not value.startswith("/") and "\\" not in value and all(
        part not in ("", ".", "..") for part in value.split("/")
    )


def inventory(data: bytes, origin: str, depth: int = 0) -> list[dict]:
    if depth > 8:
        raise ValueError("Nested archive depth exceeds verification limit")
    with zipfile.ZipFile(io.BytesIO(data)) as jar:
        names = jar.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate ZIP entries: {origin}")
        if any(not safe_archive_path(n.rstrip('/')) for n in names):
            raise ValueError(f"Unsafe ZIP path: {origin}")
        bad = jar.testzip()
        if bad:
            raise ValueError(f"CRC failure: {origin}!/{bad}")
        metadata = tomllib.loads(jar.read(MOD_METADATA).decode()) if MOD_METADATA in names else {}
        mod_ids = [mod["modId"] for mod in metadata.get("mods", [])]
        if "quilt.mod.json" in names:
            qmeta = json.loads(jar.read("quilt.mod.json"))
            if qmeta.get("schema_version") != 1:
                raise ValueError("Unsupported Quilt metadata schema")
            mod_ids.append(qmeta["quilt_loader"]["id"])
        result = [{
            "path": origin,
            "sha256": hashlib.sha256(data).hexdigest(),
            "mod_ids": mod_ids,
            "licenses": [n for n in names if "license" in n.lower() or "notice" in n.lower()],
        }]
        if JARJAR_METADATA in names:
            entries = json.loads(jar.read(JARJAR_METADATA))["jars"]
            paths = [entry["path"] for entry in entries]
            if len(paths) != len(set(paths)):
                raise ValueError(f"Duplicate nested dependency paths: {origin}")
            for entry in entries:
                if not safe_archive_path(entry["path"]):
                    raise ValueError(f"Unsafe nested archive path: {entry['path']}")
                if not all(entry["identifier"].get(k) for k in ("group", "artifact")):
                    raise ValueError("Missing Maven identity")
                result.extend(inventory(jar.read(entry["path"]),
                                        f"{origin}!/{entry['path']}", depth + 1))
        return result


def verify(bundle: Path, ffapi: Path, qsl_inventory: Path | None = None) -> dict:
    qsl = json.loads(qsl_inventory.read_text())["modules"] if qsl_inventory else []
    if len({x["id"] for x in qsl}) != len(qsl):
        raise ValueError("Duplicate QSL module pins")
    upstream = ffapi.read_bytes()
    if hashlib.sha256(upstream).hexdigest() != FFAPI_SHA256:
        raise ValueError("Unrecognized FFAPI release hash")
    with zipfile.ZipFile(bundle) as host:
        nested = json.loads(host.read(JARJAR_METADATA))["jars"]
        if len(nested) != 1:
            raise ValueError("Host JarJar must contain only the FFAPI aggregate; QSL has one coordinated intake")
        dep = nested[0]
        if dep["identifier"] != {"group": "org.sinytra.forgified-fabric-api", "artifact": "forgified-fabric-api"}:
            raise ValueError("Incorrect upstream JarJar identity")
        if dep["version"] != {"range": f"[{FFAPI_VERSION}]", "artifactVersion": FFAPI_VERSION}:
            raise ValueError("Incorrect pinned version constraint")
        if host.read(dep["path"]) != upstream:
            raise ValueError("Embedded FFAPI differs from the official aggregate")
        managed = json.loads(host.read("META-INF/unified-infinity/bundled-qsl.json"))["modules"] if "META-INF/unified-infinity/bundled-qsl.json" in host.namelist() else []
        if len(managed) != len(qsl):
            raise ValueError("Host QSL inventory differs from explicitly pinned modules")
        host_meta = tomllib.loads(host.read(MOD_METADATA).decode())
        for entry in qsl:
            required = [d for d in host_meta.get("dependencies", {}).get("mod_compat_runtime", []) if d.get("modId") == entry["id"]]
            if len(required) != 1 or required[0].get("type") != "required" or required[0].get("versionRange") != f'[{entry["version"]}]':
                raise ValueError("Host must require the exact bundled QSL logical version")
            matches = [dep for dep in managed if dep["group"] == entry["group"] and dep["artifact"] == entry["artifact"]]
            if len(matches) != 1:
                raise ValueError("Missing or duplicate QSL Maven identity")
            dep = matches[0]
            if dep["version"] != entry["version"] or dep["id"] != entry["id"] or dep["sha256"] != entry["sha256"]:
                raise ValueError("QSL exact version pin mismatch")
            data = host.read(dep["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Embedded QSL checksum mismatch")
            if data != (qsl_inventory.parent / entry["file"]).read_bytes():
                raise ValueError("Embedded QSL differs from original module")
            with zipfile.ZipFile(io.BytesIO(data)) as module:
                meta = json.loads(module.read("quilt.mod.json"))["quilt_loader"]
                if meta["id"] != entry["id"] or meta["version"] != entry["version"]:
                    raise ValueError("Embedded QSL logical identity mismatch")
                if meta.get("metadata", {}).get("license") != "Apache-2.0":
                    raise ValueError("Unexpected QSL license declaration")
            if len(host.read("META-INF/licenses/QSL-Apache-2.0.txt")) < 100:
                raise ValueError("QSL accompanying license text missing")
        host.read("dev/modcompat/runtime/bundle/RuntimeBundle.class")
        for license_path in ("META-INF/licenses/FFAPI-Apache-2.0.txt", "META-INF/licenses/Connector-MIT.txt"):
            if len(host.read(license_path)) < 100:
                raise ValueError(f"Missing license text: {license_path}")
        if any(n.startswith(("net/fabricmc/", "org/sinytra/", "org/quiltmc/")) for n in host.namelist()):
            raise ValueError("Upstream classes must not be shaded into the host")
        if any(n.startswith("META-INF/services/") for n in host.namelist()):
            raise ValueError("Host must not replace Connector's early services")
    items = inventory(bundle.read_bytes(), bundle.name)
    with zipfile.ZipFile(bundle) as host:
        for entry in managed:
            items.extend(inventory(host.read(entry["path"]), bundle.name + "!/" + entry["path"]))
    ids = [mod_id for item in items for mod_id in item["mod_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate mod IDs in bundle")
    if not {"mod_compat_runtime", "fabric_api", "forgified_fabric_api", "fabric_api_base"}.issubset(ids):
        raise ValueError("Expected native and upstream module IDs missing")
    if len(items) != 45 + len(qsl):
        raise ValueError(f"Expected host + FFAPI + 43 nested modules + selected QSL; found {len(items)} archives")
    return {
        "status": "structural-check-passed",
        "runtime_tested": False,
        "bundle": str(bundle.resolve()),
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "ffapi_sha256": FFAPI_SHA256,
        "archive_count": len(items),
        "mod_id_count": len(ids),
        "archives": items,
        "bundled_qsl_ids": [x["id"] for x in qsl],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--ffapi", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--qsl-inventory", type=Path)
    args = parser.parse_args()
    report = verify(args.bundle, args.ffapi, args.qsl_inventory)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {report['archive_count']} archives and {report['mod_id_count']} preserved mod IDs")
    print("Byte-identical FFAPI verified; this check does not claim Minecraft runtime compatibility")


if __name__ == "__main__":
    main()
