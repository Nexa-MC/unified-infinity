#!/usr/bin/env python3
"""Inspect, or explicitly compile, the self-authored native Quilt tooltip probe.

Default mode reads and hashes files only. --compile is a separate static build gate;
neither mode launches Minecraft or invokes any third-party initializer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build"
UPSTREAM = "docs/four-loader/quilt/upstream/"
CACHE = "run/quilt-native-client/gradle-cache/caches/"
LIBRARIES = CACHE + "modules-2/files-2.1/"
JDK = ".toolchains/jdk-21.0.12.1+1/"
MAPPINGS = CACHE + "quilt-loom/1.21.1/net.fabricmc.yarn.1_21_1.1.21.1+build.3-v2/mappings.tiny"
CLIENT = CACHE + "quilt-loom/minecraftMaven/net/minecraft/minecraft-merged-intermediary/1.21.1-net.fabricmc.yarn.1_21_1.1.21.1+build.3-v2/minecraft-merged-intermediary-1.21.1-net.fabricmc.yarn.1_21_1.1.21.1+build.3-v2.jar"
TOOLTIP = UPSTREAM + "qsl-alpha5-artifacts/tooltip.jar"
SOURCE_JAR = "docs/api-coverage/quilt/upstream/tooltip-10.0.0-alpha.5+1.21.1-sources.jar"
PROBE_NAME = "unified-native-quilt-tooltip-probe-0.1.0.jar"

# Ordered compile classpath: original official Quilt API JARs, locally remapped
# Minecraft client, then only explicitly pinned supporting Java libraries.
CLASSPATH_PINS = {
    UPSTREAM + "loader-0.30.1.jar": "a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb",
    UPSTREAM + "qsl_base-alpha5.jar": "7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465",
    UPSTREAM + "lifecycle_events-alpha5.jar": "1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4",
    TOOLTIP: "1d78ca2f96f1610a5905d0b9b7b833871aa112ab90b35ad524ca66e22ecd76b2",
    CLIENT: "bd5e9b18303dfbd03365286b126dfde5c688861307e0ed541e16313e6aca1d90",
    LIBRARIES + "org.jetbrains/annotations/24.0.1/13c5c75c4206580aa4d683bffee658caae6c9f43/annotations-24.0.1.jar": "61666dbce7e42e6c85b43c04fcfb8293a21dcb55b3c80e869270ce42c01a6b35",
    LIBRARIES + "com.mojang/brigadier/1.3.10/d15b53a14cf20fdcaa98f731af5dda654452c010/brigadier-1.3.10.jar": "c8ee4136e474ac7723ca2b432ec8d1a2bc88ef7d1ec57c314ba9e33cdc83dd75",
    LIBRARIES + "com.mojang/datafixerupper/8.0.16/67d4de6d7f95d89bcf5862995fb854ebaec02a34/datafixerupper-8.0.16.jar": "ffc138bc2596c291781b0d5e211ccac51f0f2345f27fc2742f335cedf7e2870d",
    LIBRARIES + "com.google.guava/guava/32.1.2-jre/5e64ec7e056456bef3a4bc4c6fdaef71e8ab6318/guava-32.1.2-jre.jar": "bc65dea7cfd9e4dacf8419d8af0e741655857d27885bb35d943d7187fc3a8fce",
    LIBRARIES + "com.google.guava/failureaccess/1.0.1/1dcf1de382a0bf95a3d8b0849546c88bac1292c9/failureaccess-1.0.1.jar": "a171ee4c734dd2da837e4b16be9df4661afab72a41adaf31eb84dfdaf936ca26",
    LIBRARIES + "org.slf4j/slf4j-api/2.0.9/7cf2726fdcfbc8610f9a71fb3ed639871f315340/slf4j-api-2.0.9.jar": "0818930dc8d7debb403204611691da58e49d42c50b6ffcfdce02dadb7c3c2b6c",
    LIBRARIES + "org.joml/joml/1.10.5/22566d58af70ad3d72308bab63b8339906deb649/joml-1.10.5.jar": "cac9f22f83a7aa33eebda73c16ff5261e3cb4911b6bafcf4c79ea486099d0c9a",
    LIBRARIES + "it.unimi.dsi/fastutil/8.5.12/c24946d46824bd528054bface3231d2ecb7e95e8/fastutil-8.5.12.jar": "b5543ee08d062d551cf0a5c9bc0fb70588b0382079029ba48941fa9c9be8a5d4",
    LIBRARIES + "org.apache.commons/commons-lang3/3.14.0/1ed471194b02f2c6cb734a0cd6f6f107c673afae/commons-lang3-3.14.0.jar": "7b96bf3ee68949abb5bc465559ac270e0551596fa34523fddf890ec418dde13c",
    LIBRARIES + "com.google.code.gson/gson/2.10.1/b3add478d4382b78ea20b1671390a858002feb6c/gson-2.10.1.jar": "4241c14a7727c34feea6507ec801318a3d4a90f070e4525681079fb94ee4c593",
    LIBRARIES + "com.mojang/authlib/6.0.54/de8bc95660e1b2fe8793fd427a7a10dcec5b3ea7/authlib-6.0.54.jar": "319ea7b53b5e52f62ad3e2b81e9db7f0751240edac548bd74f5f19e35dc21a3b",
}
PROVENANCE_PINS = {
    SOURCE_JAR: "125fcada141104a29a98cc0e88c63bed0325271eb99219d7068c9c17a42a931c",
    CACHE + "quilt-loom/1.21.1/minecraft-client.jar": "499f6897d1837516680f3114072d8106e11c9adcd933fe5cf051b551089b0c99",
    MAPPINGS: "0656f2619dc6e63f1fbfb06c2e4eaf541cec91853afb8ecd37588b229eca40f7",
    JDK + "bin/javac": "55859b80e7a9c4c4736be19ad3addeb35112ca6d17a30c4e0e116afc0a499bdb",
    JDK + "lib/modules": "70c5465dabf8e1bec2860631ea3ffd342f0ec23a5e2efd3a389d2abe32448f98",
    JDK + "release": "ebbd70bf00bab6d39addf51969c5ff244030b86b29de400b9fb10612ebd3ceec",
}
EXPECTED_REFMAP = {
    "org/quiltmc/qsl/tooltip/mixin/client/ItemStackMixin": {
        "getTooltip": "Lnet/minecraft/class_1799;method_7950(Lnet/minecraft/class_1792$class_9635;Lnet/minecraft/class_1657;Lnet/minecraft/class_1836;)Ljava/util/List;"
    },
    "org/quiltmc/qsl/tooltip/mixin/client/TooltipComponentMixin": {
        "of(Lnet/minecraft/client/item/TooltipData;)Lnet/minecraft/client/gui/tooltip/TooltipComponent;": "Lnet/minecraft/class_5684;method_32663(Lnet/minecraft/class_5632;)Lnet/minecraft/class_5684;"
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def verify_inputs() -> dict:
    for name, expected in {**CLASSPATH_PINS, **PROVENANCE_PINS}.items():
        require((ROOT / name).is_file(), f"missing pinned input: {name}")
        require(sha256(ROOT / name) == expected, f"pinned SHA-256 mismatch: {name}")
    with zipfile.ZipFile(ROOT / TOOLTIP) as archive:
        meta = json.loads(archive.read("quilt.mod.json"))["quilt_loader"]
        require(meta["id"] == "quilt_tooltip" and meta["version"] == "10.0.0-alpha.5+1.21.1", "original tooltip identity")
        entries = meta["entrypoints"]
        require(entries["client_events"] == entries["client_init"] == ["org.quiltmc.qsl.tooltip.impl.client.QuiltClientTooltipMod::INSTANCE"], "original static INSTANCE entrypoints")
        mixins = json.loads(archive.read("quilt_tooltip.mixins.json"))
        require(mixins["client"] == ["client.ItemStackMixin", "client.TooltipComponentMixin"], "original client-only mixins")
        require(not mixins.get("mixins") and not mixins.get("server") and mixins["injectors"]["defaultRequire"] == 1, "original required client mixin policy")
        refmap = json.loads(archive.read("tooltip.refmap.json"))
        require(refmap["mappings"] == EXPECTED_REFMAP, "exact original target descriptors")
        require(refmap["data"]["named:intermediary"] == EXPECTED_REFMAP, "exact original named:intermediary targets")
    return {"original_tooltip_identity": True, "original_static_INSTANCE_entrypoints": True,
            "original_required_client_mixins": True, "exact_refmap_targets": EXPECTED_REFMAP}


def collect_sources() -> tuple[list[Path], dict[str, bytes]]:
    sources = sorted((HERE / "src").rglob("*.java"))
    require(bool(sources), "no Java probe sources")
    for source in sources:
        text = source.read_text(encoding="utf-8")
        require("net.fabricmc" not in text and "net.neoforged" not in text, f"foreign loader API reference in {rel(source)}")
    resources = {p.relative_to(HERE / "resources").as_posix(): p.read_bytes()
                 for p in sorted((HERE / "resources").rglob("*")) if p.is_file()}
    require("quilt.mod.json" in resources, "missing native Quilt descriptor")
    require("fabric.mod.json" not in resources and "META-INF/neoforge.mods.toml" not in resources, "foreign loader descriptor")
    meta = json.loads(resources["quilt.mod.json"])
    require("environment" not in meta and "mixin" not in meta, "probe must stay common and use original module mixins")
    loader = meta["quilt_loader"]
    require("environment" not in loader, "probe must not be root client-only")
    require(loader["intermediate_mappings"] == "net.fabricmc:intermediary", "native intermediary namespace")
    entries = loader["entrypoints"]
    require(entries["client_events"] == entries["client_init"] == "dev.infinity.quilttooltipprobe.ClientProbe::INSTANCE", "probe static INSTANCE entrypoints")
    require({d["id"]: d["versions"] for d in loader["depends"]} == {
        "minecraft": "=1.21.1", "java": ">=21", "quilt_loader": ">=0.25.0",
        "quilt_base": "=10.0.0-alpha.5+1.21.1", "quilt_lifecycle_events": "=10.0.0-alpha.5+1.21.1",
        "quilt_tooltip": "=10.0.0-alpha.5+1.21.1"}, "exact native dependency closure")
    return sources, resources


def compile_command(sources: list[Path]) -> list[str]:
    return [JDK + "bin/javac", "-J-Xmx192m", "-J-XX:ActiveProcessorCount=1",
            "-J-Duser.language=en", "-J-Duser.country=US",
            "-J-Duser.timezone=UTC", "-encoding", "UTF-8", "-proc:none", "-g:none",
            "--release", "21", "-classpath", os.pathsep.join(CLASSPATH_PINS),
            "-d", rel(BUILD / "classes"), *map(rel, sources)]


def write_deterministic_jar(path: Path, entries: dict[str, bytes]) -> None:
    # Stored entries avoid compression-library variability. No manifests generated by
    # jar tooling, timestamps, inherited file modes, directory entries, or absolute paths.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)


def compile_probe(sources: list[Path], resources: dict[str, bytes], report: dict) -> None:
    classes = BUILD / "classes"
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir(parents=True)
    environment = dict(os.environ)
    for variable in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH"):
        environment.pop(variable, None)
    subprocess.run(compile_command(sources), cwd=ROOT, env=environment, check=True)
    entries = dict(resources)
    for path in sorted(classes.rglob("*.class")):
        name = path.relative_to(classes).as_posix()
        data = path.read_bytes()
        require(b"net/fabricmc" not in data and b"net/neoforged" not in data, f"foreign loader bytecode reference: {name}")
        require(name.startswith("dev/infinity/quilttooltipprobe/"), f"unexpected compiled payload: {name}")
        entries[name] = data
    require(any(name.endswith("CommonTooltipData.class") for name in entries), "missing common data class")
    target = BUILD / PROBE_NAME
    write_deterministic_jar(target, entries)
    report.update({"build_status": "COMPILED_STATIC_ONLY", "probe": rel(target), "sha256": sha256(target)})
    negatives = []
    for variant in ("missing-dependency", "unsupported-tooltip-version", "forged-managed-tooltip-id"):
        variant_entries = dict(entries)
        meta = json.loads(entries["quilt.mod.json"])
        loader = meta["quilt_loader"]
        if variant == "missing-dependency":
            loader["depends"].append({"id": "native_quilt_tooltip_missing_dependency", "versions": "=9.9.9"})
        elif variant == "unsupported-tooltip-version":
            next(d for d in loader["depends"] if d["id"] == "quilt_tooltip")["versions"] = ">=10.0.0-alpha.6+1.21.1"
        else:
            loader["id"] = "quilt_tooltip"
        variant_entries["quilt.mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode()
        negative = BUILD / (PROBE_NAME.removesuffix(".jar") + "-" + variant + ".jar")
        write_deterministic_jar(negative, variant_entries)
        negatives.append({"variant": variant, "path": rel(negative), "sha256": sha256(negative),
                          "must_reject_before": "NATIVE_QUILT_TOOLTIP_PROBE CLASS_DEFINED",
                          "runtime_status": "NOT RUN"})
    report["negative_controls"] = negatives
    # Recheck originals after javac and packaging, before writing a successful receipt.
    verify_inputs()
    (BUILD / "build-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true", help="explicitly invoke pinned javac and create deterministic probe/negative JARs; never run a game")
    args = parser.parse_args()
    original_contract = verify_inputs()
    sources, resources = collect_sources()
    report = {
        "build_status": "SOURCE_ONLY_NOT_COMPILED", "runtime_status": "NOT RUN",
        "native_client_status": "NOT RUN", "unified_client_status": "NOT RUN", "dedicated_server_status": "NOT RUN",
        "native_descriptor_only": True, "foreign_loader_source_references": False,
        "compile_classpath_pins_sha256": CLASSPATH_PINS, "provenance_pins_sha256": PROVENANCE_PINS,
        "sources_sha256": {rel(p): sha256(p) for p in sources},
        "resources_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in resources.items()},
        "builder_sha256": sha256(HERE / "build.py"), "original_contract": original_contract,
        "compile_command_from_repository_root": shlex.join(compile_command(sources)),
        "static_build_command": "python3 four-loader/quilt-api-probe/build.py --compile",
        "runtime_claim": "None: a source inspection or successful static build does not establish loader equivalence or game behavior.",
    }
    if args.compile:
        compile_probe(sources, resources, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
