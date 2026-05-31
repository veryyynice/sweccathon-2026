# Long Horizon Grid Balancer

A [Mesocosm](https://mesocosm.swecc.org) typed environment. An LLM agent acts as a
**Grid Operator** facing a hidden evening demand spike that threatens grid failure.
Each turn it either **buys a forecast** of the hidden net load at one hour (trading
cost for precision) or **submits a final 24-hour battery dispatch schedule**.

```
Final Score = (1000 if dispatch prevents grid failure at the true peak, else 0)
              − total cost of forecasts
```

The interesting tension: forecasts cost money that's deducted from the score, so the
agent must buy *just enough* information to pin down the peak hour and magnitude,
then concentrate its limited battery reserve there.

## Mechanics

- **Horizon:** 24 hours. A smooth daily net-load curve, plus one hidden spike in the
  evening window (hours 17–20) that exceeds grid capacity (100).
- **Battery:** total dischargeable reserve `70`, per-hour limit `70`. Success requires
  `schedule[peak_hour] >= true_demand[peak_hour] − capacity` while total discharge
  stays within the reserve — so spreading the battery thin fails.
- **Forecast tiers** (cost / Gaussian noise σ): `quick` 1/25, `standard` 3/12,
  `precision` 7/4, `extreme` 10/0.
- **Actions (JSON):**
  - `{"action":"forecast","tier":"quick|standard|precision|extreme","target_hour":int}`
  - `{"action":"dispatch","battery_schedule":[24 ints, +discharge / −charge]}`
- Forecast steps reward `0`; the score lands on the final dispatch (or on timeout).
- `max_steps = 30`, deterministic, seedable.

## Layout

```
benchanything.json      # manifest (JSON action space, scalar reward, scoring)
env.py                  # GridBalancerEnv(BaseEnv): reset / step -> StepResult
adapter.py              # serves the env over the 4-endpoint HTTP protocol
test_env.py             # determinism + smart-vs-dumb discrimination
requirements.txt        # stdlib-only
showcase/
  index.html            # interactive replay dashboard (vanilla JS + Canvas)
  data/make_placeholder.py  # generates placeholder replay in the export schema
  data/replay.json      # data the showcase reads (fetch)
  data/replay.js        # window.REPLAY fallback for file://
.github/workflows/pages.yml
```

## Local dev

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install swecc-mesocosm

python test_env.py                  # determinism + discrimination (must pass)
mesocosm validate benchanything.json

python adapter.py                   # terminal 1
mesocosm run local                  # terminal 2
```

## Showcase

```bash
python showcase/data/make_placeholder.py    # demoable data before a real run
# open showcase/index.html (works over file:// via replay.js)
```

The dashboard plots the hidden true demand curve (faint), the grid-capacity line, and
the noisy forecast points the model purchased (colored by tier), with a draggable
scrubber, play/pause, 0.5×–4× speed, episode rail, hover-to-inspect, and a live HUD
showing budget spent, the chosen action, and the model's reasoning per turn.

## Ship pipeline

1. Push this repo (**public**) — `sweccathon-2026`, with the manifest + `env.py` +
   `adapter.py` at the repo root.
2. `mesocosm auth login`
3. `mesocosm env submit --name "Long Horizon Grid Balancer" --github-url <repo-url> --solo`
   — wait for `ready`; note `domain_id` (`mesocosm env list`).
4. `mesocosm run create --domain <DOMAIN_ID> --vow-version 1.0.0 --model openai/gpt-4o --episodes 8 --visibility gallery_public --solo`
   — poll `mesocosm run get <RUN_ID>` until `completed` (lower `--episodes` to 4–6 on 429).
5. `mesocosm run export <RUN_ID> -o showcase/data/replay.json`, then regenerate
   `replay.js` as `window.REPLAY = <contents of replay.json>;`.
6. Enable GitHub Pages (build type = GitHub Actions). Live at
   `https://<user>.github.io/sweccathon-2026/` (Pages URL follows the repo name).
7. Update the env description to include the live Pages link.
