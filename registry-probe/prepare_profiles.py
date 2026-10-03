#!/usr/bin/env python3
"""Prepare separate disposable profiles using verified local immutable inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CONNECTOR = "9a6e896e7742fb920469266808c409c76ac0ab84e0d82f7ac4b5ecbe9ee11eb1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(accept_eula):
    if not accept_eula:
        raise SystemExit("Explicit --accept-eula is required for the authorized test")
    probe = ROOT / "registry-probe/build/infinity-registry-probe-0.1.0.jar"
    connector = ROOT / "integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar"
    bundle = ROOT / "runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar"
    assert sha(connector) == EXPECTED_CONNECTOR, "Derived Connector changed; re-pin deliberately"
    manifest = {}
    for name, baseline, port in (("native", "fabric-native", 25566), ("unified", "neoforge-compat", 25567)):
        profile = ROOT / "run" / ("registry-" + name)
        if profile.exists():
            raise SystemExit(f"Profile already exists, refusing to overwrite: {profile}")
        profile.mkdir()
        base = ROOT / "run" / baseline
        shutil.copytree(base / "libraries", profile / "libraries", copy_function=os.link)
        if name == "native":
            os.link(base / "server.jar", profile / "server.jar")
        (profile / "mods").mkdir()
        inputs = [probe]
        if name == "native":
            inputs.append(base / "mods/fabric-api-0.116.7+1.21.1.jar")
        else:
            inputs += [connector, bundle]
        for artifact in inputs:
            shutil.copy2(artifact, profile / "mods" / artifact.name)
        subprocess.run(["python3", str(ROOT / "tools/configure-test-profile.py"), str(profile), "--accept-eula"], check=True)
        prop = profile / "server.properties"
        prop.write_text(prop.read_text().replace("server-port=25565", f"server-port={port}"))
        manifest[name] = {"profile": str(profile.relative_to(ROOT)), "port": port,
                          "input_mod_sha256": {p.name: sha(p) for p in sorted((profile / "mods").glob("*.jar"))}}
    assert manifest["native"]["input_mod_sha256"][probe.name] == manifest["unified"]["input_mod_sha256"][probe.name]
    output = ROOT / "logs/registry-inputs.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-eula", action="store_true")
    prepare(parser.parse_args().accept_eula)
