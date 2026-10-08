#!/usr/bin/env python3
"""Read-only source/metadata audit; never starts Java, Gradle, a game, or a network request."""
from pathlib import Path
import hashlib
import json
import re
import tomllib
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "source-manifest.json").read_text())
    assert manifest["schema"] == 1 and manifest["status"] == "SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE"
    rows = manifest["files"]
    expected = {row["path"] for row in rows} | {"source-manifest.json"}
    found = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    assert found == expected, ("unexpected_or_missing_files", sorted(found ^ expected))
    for row in rows:
        relative = Path(row["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        path = root / relative
        assert path.is_file() and not path.is_symlink()
        data = path.read_bytes()
        assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"], row["path"]
        assert path.suffix.lower() not in {".jar", ".class", ".zip", ".gz", ".png", ".bin"}
    provenance = json.loads((root / "PROVENANCE.json").read_text())
    assert provenance["sourceApi"]["sha256"] == "814983ff6c233935f176a99b10a495cfa37971ffe1a73a6f8b097e893553ca8c"
    assert not any(provenance["validation"][key] for key in (
        "javaCompiled", "preparedCodecTestRun", "clientOrServerLaunched", "networkAcceptance", "downloads", "remoteWrites", "ciDispatched"))
    metadata = root / "gradle/verification-metadata.xml"
    assert hashlib.sha256(metadata.read_bytes()).hexdigest() == "301991fa4fb172adc5776daa36a48efadcb855f145cc386fdfc49e307fe9105f"
    ET.parse(metadata)
    mod = tomllib.loads((root / "src/main/resources/META-INF/neoforge.mods.toml").read_text())
    assert mod["mods"][0]["modId"] == "network_control"
    java = root / "src/main/java/dev/infinity/networkcontrol"
    assert {p.name for p in java.glob("*.java")} == {"NonceProbe.java", "NonceProbeClient.java", "NonceRequest.java", "NonceReply.java"}
    common = (java / "NonceProbe.java").read_text()
    assert "net.minecraft.client" not in common and "NonceProbeClient" not in common
    assert "NonceProbe::reply" in common and "clientReply" in common
    assert "server.getPort(), context.protocol(), context.flow())" in common
    client = (java / "NonceProbeClient.java").read_text()
    assert "input.port(), context.protocol(), context.flow())" in client
    schema = json.loads((root / "protocol-schema.json").read_text())
    definitions = schema["$defs"]
    assert set(definitions) == {"input", "release", "pass", "fail", "ready", "disconnected"}
    for definition in definitions.values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    passed = definitions["pass"]
    assert passed["properties"]["phase"] == {"const": "PLAY"}
    assert passed["properties"]["flow"] == {"enum": ["SERVERBOUND", "CLIENTBOUND"]}
    direction_rule = passed["allOf"][0]
    assert direction_rule["then"]["properties"]["flow"] == {"const": "SERVERBOUND"}
    assert direction_rule["else"]["properties"]["flow"] == {"const": "CLIENTBOUND"}
    source = "\n".join(p.read_text() for p in java.glob("*.java"))
    codes = set(re.findall(r'"([a-z][a-z0-9_]+)"', source)) - {"network_control", "request", "reply", "client", "server", "ok"}
    assert codes == set(definitions["fail"]["properties"]["code"]["enum"])
    print(json.dumps({"schema": 1, "sourceAudit": "PASS", "files": len(rows),
                      "compiled": False, "preparedJavaTestsRun": False, "gameOrNetworkAcceptance": False}, separators=(",", ":")))


if __name__ == "__main__":
    main()
