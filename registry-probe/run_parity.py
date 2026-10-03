#!/usr/bin/env python3
"""Positive assertions for real registration, API lifecycle, save and reopen."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time

from region_nbt import persisted_item

ROOT = Path(__file__).resolve().parents[1]
PROBE_NAME = "infinity-registry-probe-0.1.0.jar"
REGISTER = "INFINITY_REGISTRY_PROBE registration=PASS id=infinity_registry_probe:test_item"
LIFECYCLE = "INFINITY_REGISTRY_PROBE lifecycle=SERVER_STARTED registry=PASS id=infinity_registry_probe:test_item"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Server:
    def __init__(self, profile, loader, log_path, timeout):
        self.profile, self.loader = profile, loader
        properties = dict(line.split("=", 1) for line in (profile / "server.properties").read_text().splitlines()
                          if "=" in line and not line.startswith("#"))
        for key, expected in {"server-ip": "127.0.0.1", "online-mode": "true", "enable-rcon": "false", "enable-query": "false"}.items():
            assert properties.get(key) == expected, f"Unsafe profile setting {key}"
        assert (profile / "eula.txt").read_text().strip() == "eula=true"
        java = str(ROOT / ".toolchains/jdk-21.0.12.1+1/bin/java")
        args = [java, "-Xms512M", "-Xmx2G"]
        if loader == "native":
            cp = os.pathsep.join(str(p) for p in sorted((profile / "libraries").rglob("*.jar")))
            cp += os.pathsep + str(profile / "server.jar")
            args += ["-Dfabric.gameJarPath=" + str(profile / "server.jar"), "-cp", cp,
                     "net.fabricmc.loader.impl.launch.knot.KnotServer", "nogui"]
        else:
            args += ["@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt", "nogui"]
        self.proc = subprocess.Popen(args, cwd=profile, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        self.log = log_path.open("wb")
        self.output = ""
        self.deadline = time.monotonic() + timeout
        self.commands = []

    def pump(self, timeout=0.5):
        readable, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if readable:
            data = os.read(self.proc.stdout.fileno(), 65536)
            self.log.write(data)
            self.log.flush()
            self.output += data.decode("utf-8", errors="replace")

    def wait(self, regex, offset=0, seconds=None):
        deadline = min(self.deadline, time.monotonic() + seconds) if seconds else self.deadline
        while True:
            if (match := re.search(regex, self.output[offset:], re.MULTILINE)):
                return match.group(0)
            if self.proc.poll() is not None:
                self.pump(0)
                raise RuntimeError(f"Server exited {self.proc.returncode} while waiting for {regex}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Missing positive acknowledgement: {regex}")
            self.pump()

    def command(self, text):
        offset = len(self.output)
        self.log.write(("\n# HARNESS COMMAND: " + text + "\n").encode())
        self.log.flush()
        self.commands.append(text)
        self.proc.stdin.write((text + "\n").encode())
        self.proc.stdin.flush()
        return offset

    def ready(self):
        self.wait(r"Done \([^)]+\)! For help")
        self.wait(re.escape(REGISTER))
        self.wait(re.escape(LIFECYCLE))

    def load_chunk(self):
        self.command("forceload add 0 0")
        for attempt in range(60):
            offset = self.command("execute if loaded 0 64 0 run say INFINITY_REGISTRY_CHUNK_READY")
            try:
                self.wait(r"\[Server\] INFINITY_REGISTRY_CHUNK_READY", offset, seconds=2)
                return
            except TimeoutError:
                if time.monotonic() > self.deadline:
                    raise
        raise TimeoutError("Chunk 0,0 never became loaded")

    def stack(self):
        offset = self.command("data get block 0 64 0 Items")
        line = self.wait(r"0, 64, 0 has the following block data: \[[^\r\n]+", offset, seconds=30)
        assert re.search(r'id:\s*"infinity_registry_probe:test_item"', line), line
        assert re.search(r'count:\s*7\b', line), line
        assert re.search(r'Slot:\s*0b\b', line), line
        return line

    def save_stop(self):
        offset = self.command("save-all flush")
        self.wait(r"Saved the game|Saved the world", offset, seconds=90)
        offset = self.command("stop")
        self.wait(r"All dimensions are saved", offset, seconds=90)
        while self.proc.poll() is None:
            if time.monotonic() > self.deadline:
                raise TimeoutError("Server did not terminate cleanly")
            self.pump()
        self.pump(0)
        assert self.proc.returncode == 0, self.proc.returncode

    def close(self):
        if self.proc.poll() is None:
            try:
                self.command("stop")
                end = time.monotonic() + 30
                while self.proc.poll() is None and time.monotonic() < end:
                    self.pump()
            except (BrokenPipeError, OSError):
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.pump(0)
        self.log.close()


def run(loader, stage, timeout):
    profile = ROOT / "run" / ("registry-" + loader)
    tag = f"registry-{loader}-{stage}"
    report_path = ROOT / "logs" / (tag + ".json")
    res = {"tag": tag, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "loader": loader, "stage": stage, "passed": False,
           "input_mod_sha256": {p.name: sha(p) for p in sorted((profile / "mods").glob("*.jar"))},
           "network": "127.0.0.1 only; online-mode=true; RCON/query disabled",
           "scope": "project-owned unchanged Fabric JAR; direct item registration, Fabric SERVER_STARTED, actual persisted chest item; no third-party corpus or client coverage"}
    server = None
    try:
        assert res["input_mod_sha256"][PROBE_NAME] == sha(ROOT / "registry-probe/build" / PROBE_NAME), "Fixture input changed"
        if stage == "create":
            assert not (profile / "world").exists(), "Creation stage requires a fresh profile world"
        else:
            res["persisted_item_before_start"] = persisted_item(profile)
        server = Server(profile, loader, ROOT / "logs" / (tag + ".log"), timeout)
        server.ready()
        res["registration_positive_marker"] = True
        res["fabric_server_started_positive_marker"] = True
        server.load_chunk()
        if stage == "create":
            offset = server.command("setblock 0 64 0 minecraft:chest")
            server.wait(r"Changed the block at 0, 64, 0", offset, seconds=30)
            offset = server.command("item replace block 0 64 0 container.0 with infinity_registry_probe:test_item 7")
            server.wait(r"Replaced a slot at 0, 64, 0", offset, seconds=30)
        res["console_item_assertion"] = server.stack()
        server.save_stop()
        res["save_flush_acknowledged"] = True
        res["all_dimensions_saved"] = True
        res["exit_code"] = server.proc.returncode
        res["persisted_item_after_stop"] = persisted_item(profile)
        res["passed"] = True
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if server:
            server.close()
            res["commands"] = server.commands
            res["exit_code"] = server.proc.returncode
        report_path.write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res), flush=True)
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loader", choices=("native", "unified"), required=True)
    parser.add_argument("--stage", choices=("create", "reopen"), required=True)
    parser.add_argument("--timeout", type=int, default=480)
    options = parser.parse_args()
    result = run(options.loader, options.stage, options.timeout)
    raise SystemExit(0 if result["passed"] else 1)
