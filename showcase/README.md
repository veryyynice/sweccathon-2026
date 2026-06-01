# Replay Lab — interactive showcase

A single self-contained page that replays a real Mesocosm bench run of the
**Efficient Scientific Discovery** environment and lets you *drive* the replay.

**Live:** https://veryyynice.github.io/sweccathon-2026/

## What it does

The agent plays a scientist probing a hidden function `f(x)` over `x ∈ [-8, 8]`
with noisy, budgeted experiments, then submits which law family it is
(`linear / quadratic / exponential / periodic / piecewise`). The showcase plots
every probe on an oscilloscope-style field so you can *see* the shape the model
saw, turn by turn.

## Interactivity

- **Transport:** play/pause, step forward/back, first/last, and a draggable
  timeline scrubber that jumps to any turn.
- **Speed:** 0.5× / 1× / 2× / 4×.
- **Episode rail:** click any of the 8 episodes (colored green = correct,
  red = wrong) to switch; controls persist per episode.
- **Hover-to-inspect:** hover a probe to read its `x`, observed `y`, precision
  and cost; the current turn highlights the action taken (amber ring + guide).
- **Live HUD:** step reward, cumulative reward, budget, experiment count, the
  agent's JSON action, a plain-language readout of the move, and a lab notebook
  of all probes so far.
- **Keyboard:** `space` play/pause · `←`/`→` step · `↑`/`↓` switch episode.

## Data

- Reads `data/replay.json` (the exported run) via `fetch`.
- Falls back to `window.REPLAY` from `data/replay.js` so it also works when the
  file is opened directly over `file://`.

Each turn carries `observation`, `action`, `reward`, `terminated`, `truncated`
and `info`; render values (x, observed y, precision, budget, verdict) are read
from `turn.info` / `board_after` string fields and parsed to numbers.

Regenerate the bundle after re-exporting a run:

```bash
mesocosm run export RUN_ID -o showcase/data/replay.json
python3 -c "import json;d=json.load(open('showcase/data/replay.json'));open('showcase/data/replay.js','w').write('window.REPLAY = '+json.dumps(d,separators=(',',':'))+';\n')"
```

## Deploy

Pushed to GitHub Pages from the `showcase/` folder via
`.github/workflows/pages.yml` (configure-pages → upload-pages-artifact →
deploy-pages).
