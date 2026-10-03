#!/usr/bin/env python3
"""Encode actual native harness framebuffer samples without inventing progress."""
import hashlib
import json
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent.parent
source = root / 'reports/native-animation-frames'
rows = [line.split(',') for line in (source / 'timing.csv').read_text().splitlines()]
if not (2 <= len(rows) <= 60):
    raise SystemExit('Expected a bounded real capture sequence of 2–60 frames')
images = [Image.open(source / name).convert('RGB') for name, _ in rows]
if len({image.size for image in images}) != 1:
    raise SystemExit('Capture dimensions changed')
times = [int(nanos) for _, nanos in rows]
if any(b <= a for a, b in zip(times, times[1:])):
    raise SystemExit('Capture clock did not advance')
durations = [max(10, round((b-a)/10_000_000)*10) for a,b in zip(times,times[1:])]
durations.append(durations[-1])
palette = images[0].quantize(colors=256)
frames = [image.quantize(palette=palette,dither=Image.Dither.NONE) for image in images]
out = root / 'reports/native-preload-animation.gif'
frames[0].save(out,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=False,disposal=2)
with Image.open(out) as check:
    if check.n_frames != len(rows): raise SystemExit('GIF lost captured frames')
report = {'origin':'Actual own OpenGL native-harness framebuffer samples; not a Minecraft video',
          'syntheticProgress':False,'frames':len(rows),'durationMs':sum(durations),
          'dimensions':list(images[0].size),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
          'timingSource':'reports/native-animation-frames/timing.csv','quantization':'GIF palette only; no inserted/interpolated frames'}
(root / 'reports/native-preload-animation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
