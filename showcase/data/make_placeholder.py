"""Generate placeholder replay data so the showcase works before a real run.

    python showcase/data/make_placeholder.py

Writes showcase/data/replay.json and showcase/data/replay.js in the SAME schema
`mesocosm run export` produces:

    { run: {scores}, episodes: [...], replay: { <episodeId>: [turns] } }

Each turn: { step, observation, reasoning, action, reward, terminated,
             truncated, info }  (info values are strings, like the platform).

Replace with a real run via:
    mesocosm run export <RUN_ID> -o showcase/data/replay.json
then regenerate replay.js as `window.REPLAY = <contents of replay.json>;`.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from env import EVENING_WINDOW, HOURS, MAX_DISCHARGE_RATE, GridBalancerEnv  # noqa: E402


def build_episode(seed: int, scan_tier: str) -> list[dict]:
    """A demo operator: scan the evening window at `scan_tier`, then dispatch
    at the discovered peak. Mixed tiers across episodes make the scatter vary."""
    env = GridBalancerEnv()
    obs = env.reset(seed=seed)
    turns: list[dict] = []
    lo, hi = EVENING_WINDOW
    scan_hours = list(range(lo, hi + 1))
    readings: dict[int, float] = {}
    step = 0

    def record(action, reasoning):
        nonlocal obs, step
        step += 1
        result = env.step(action)
        turns.append({
            "step": step,
            "observation": obs,
            "reasoning": reasoning,
            "action": action,
            "reward": result.reward,
            "terminated": result.terminated,
            "truncated": result.truncated,
            "info": result.info,
        })
        obs = result.observation
        return result

    for h in scan_hours:
        reasoning = (
            f"I don't yet know where the evening spike sits. Probing hour {h} with a "
            f"'{scan_tier}' forecast (cost {obs['forecast_tiers'][scan_tier]['cost']}, "
            f"noise σ={obs['forecast_tiers'][scan_tier]['noise_std']}) to map the "
            f"{lo}:00–{hi}:00 window before committing my {obs['battery_reserve']}-unit reserve."
        )
        record({"action": "forecast", "tier": scan_tier, "target_hour": h}, reasoning)
        for f in obs["forecasts_purchased"]:
            readings[f["hour"]] = f["observed"]

    peak = max(readings, key=readings.get)
    est_required = readings[peak] - obs["grid_capacity"]
    amount = max(0, min(MAX_DISCHARGE_RATE, int(math.ceil(est_required))))
    schedule = [0] * HOURS
    schedule[peak] = amount
    reasoning = (
        f"Scan done. The peak reads highest at hour {peak} (~{readings[peak]:.0f}), "
        f"about {est_required:.0f} over the {obs['grid_capacity']:.0f} capacity. "
        f"Concentrating {amount} units of discharge at hour {peak} and leaving the rest "
        f"idle — spreading the reserve would leave the peak underserved."
    )
    record({"action": "dispatch", "battery_schedule": schedule}, reasoning)
    return turns


def main() -> None:
    rng = random.Random(7)
    tiers = ["standard", "precision", "quick", "standard", "precision", "extreme"]
    seeds = [rng.randint(0, 10_000) for _ in tiers]

    replay: dict[str, list[dict]] = {}
    episodes: list[dict] = []
    score_sum = 0.0
    success = 0

    for i, (seed, tier) in enumerate(zip(seeds, tiers)):
        ep_id = f"placeholder-ep-{i:02d}"
        turns = build_episode(seed, tier)
        replay[ep_id] = turns
        total = sum(t["reward"] for t in turns)
        score_sum += total
        last = turns[-1]["info"]
        won = last.get("success") == "true"
        success += int(won)
        episodes.append({
            "episode_id": ep_id,
            "seed": seed,
            "steps": len(turns),
            "total_reward": round(total, 2),
            "outcome": "prevented" if won else last.get("dispatch_reason", "failed"),
        })

    export = {
        "schema_version": "1",
        "placeholder": True,
        "run": {
            "scores": {
                "mean_score": round(score_sum / len(seeds), 2),
                "success_rate": round(success / len(seeds), 3),
            }
        },
        "episodes": episodes,
        "replay": replay,
    }

    out_dir = Path(__file__).resolve().parent
    (out_dir / "replay.json").write_text(json.dumps(export, indent=2), encoding="utf-8")
    (out_dir / "replay.js").write_text(
        "window.REPLAY = " + json.dumps(export, indent=2) + ";\n", encoding="utf-8"
    )
    print(f"wrote {out_dir / 'replay.json'}")
    print(f"wrote {out_dir / 'replay.js'}")


if __name__ == "__main__":
    main()
