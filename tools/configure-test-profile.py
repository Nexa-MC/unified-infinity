#!/usr/bin/env python3
"""Configure only a disposable loopback profile; requires explicit EULA flag."""
import argparse,pathlib
p=argparse.ArgumentParser();p.add_argument('profile',type=pathlib.Path);p.add_argument('--accept-eula',action='store_true');a=p.parse_args()
if not a.accept_eula:raise SystemExit('Explicit approved EULA acceptance required')
a.profile.mkdir(parents=True,exist_ok=True)
(a.profile/'eula.txt').write_text('eula=true\n')
(a.profile/'server.properties').write_text('server-ip=127.0.0.1\nserver-port=25565\nonline-mode=true\nenable-rcon=false\nenable-query=false\nmax-players=1\nview-distance=2\nsimulation-distance=2\nspawn-protection=0\nlevel-seed=1211\nlevel-name=world\nmotd=Private compatibility test\n')
print('Configured loopback-only test profile. Minecraft EULA accepted: https://www.minecraft.net/en-us/eula')
