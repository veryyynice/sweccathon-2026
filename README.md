# Grid Runner — a Mesocosm env skeleton

A ready-to-fill skeleton for a [Mesocosm](https://mesocosm.swecc.org) typed
environment. An LLM agent plays the env, gets scored, and the run is replayed
in the interactive showcase.

The included env (`env.py`) is a **placeholder gridworld** — an agent walks from
the top-left corner to a goal cell while avoiding hazards. Swap the game logic
for your own idea; keep the structure (seeded RNG, string-only `info`, shaped
scalar reward, `max_steps` guard) because that's what the platform enforces.

## Layout

```
benchanything.json      # manifest: spaces, reward, episode, scoring
env.py                  # BaseEnv: reset(seed,**params) / step(action) -> StepResult
adapter.py              # serves env over the 4-endpoint HTTP protocol (repo root)
test_env.py             # determinism + smart-vs-dumb discrimination checks
requirements.txt        # extra deps your env imports (stdlib-only by default)
showcase/
  index.html            # self-contained interactive replay player (vanilla JS + Canvas)
  data/
    make_placeholder.py # generates placeholder replay in the export schema
    replay.json         # replay the showcase reads (fetch)
    replay.js           # window.REPLAY fallback for file:// opens
.github/workflows/pages.yml   # deploys showcase/ to GitHub Pages
```

## Local dev

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install swecc-mesocosm

python test_env.py                 # determinism + discrimination (must pass)
mesocosm validate benchanything.json

# Ollama loop:
python adapter.py                  # terminal 1
mesocosm run local                 # terminal 2
```

## Showcase

```bash
python showcase/data/make_placeholder.py   # demoable data before a real run
# open showcase/index.html (works via file:// thanks to replay.js)
```

Controls: play/pause (`space`), step (`←`/`→`), switch episode (`↑`/`↓`),
draggable scrubber, speed `0.5×–4×`, hover a cell to inspect, live HUD with the
model's reasoning + chosen action.

## Ship pipeline

1. Push this repo (public). Keep manifest + `env.py` + `adapter.py` at the root.
2. `mesocosm auth login`
3. `mesocosm env submit --name "Grid Runner" --github-url <repo-url> --solo`
   — wait until `ready`; note the `domain_id` (`mesocosm env list`).
4. `mesocosm run create --domain <DOMAIN_ID> --vow-version 1.0.0 --model <model> --episodes 8 --visibility gallery_public --solo`
   — poll `mesocosm run get <RUN_ID>` until `completed` (lower `--episodes` on 429).
5. `mesocosm run export <RUN_ID> -o showcase/data/replay.json`
   then regenerate `replay.js` (`window.REPLAY = <contents of replay.json>;`).
6. Enable GitHub Pages (build_type = GitHub Actions). Live at
   `https://<user>.github.io/<repo>/`.
7. Update the env description to include the live Pages link.
