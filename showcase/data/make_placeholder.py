"""Generate a placeholder replay so the showcase works before a real run.

    python showcase/data/make_placeholder.py

Writes showcase/data/replay.json and showcase/data/replay.js in the SAME
schema that `mesocosm run export` produces, so the showcase renders identically
whether it's reading placeholder data or a real exported run:

    { run: {scores}, episodes: [...], replay: { <episodeId>: [turns] } }

Each turn: { step, observation, reasoning, action, reward, terminated,
             truncated, info }  (info values are strings, like the platform).

Once you have a real run, replace these files via:
    mesocosm run export <RUN_ID> -o showcase/data/replay.json
(and regenerate replay.js from it — see the bottom of this file).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Make the repo root importable so we can drive the real env.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from env import ACTIONS, GridRunnerEnv  # noqa: E402


def smart(obs):
    ar, ac = obs["agent"]
    gr, gc = obs["goal"]
    dr, dc = gr - ar, gc - ac
    if abs(dr) >= abs(dc) and dr != 0:
        return ("down" if dr > 0 else "up"), dr, dc
    if dc != 0:
        return ("right" if dc > 0 else "left"), dr, dc
    return ("down" if dr > 0 else "up"), dr, dc


def reasoning_for(obs, action, dr, dc) -> str:
    return (
        f"Agent at {obs['agent']}, goal at {obs['goal']} "
        f"(Δrow={dr}, Δcol={dc}). {len(obs['hazards'])} hazards on the board. "
        f"Closing the larger gap first → moving {action}."
    )


def build_episode(seed: int) -> list[dict]:
    env = GridRunnerEnv()
    obs = env.reset(seed=seed)
    turns: list[dict] = []
    step = 0
    while True:
        step += 1
        action, dr, dc = smart(obs)
        reasoning = reasoning_for(obs, action, dr, dc)
        result = env.step(action)
        turns.append(
            {
                "step": step,
                "observation": obs,
                "reasoning": reasoning,
                "action": action,
                "reward": result.reward,
                "terminated": result.terminated,
                "truncated": result.truncated,
                "info": result.info,
            }
        )
        obs = result.observation
        if result.terminated or result.truncated:
            break
    return turns


def main() -> None:
    rng = random.Random(0)
    seeds = [rng.randint(0, 10_000) for _ in range(6)]

    replay: dict[str, list[dict]] = {}
    episodes: list[dict] = []
    rewards_sum = 0.0
    successes = 0

    for i, seed in enumerate(seeds):
        ep_id = f"placeholder-ep-{i:02d}"
        turns = build_episode(seed)
        replay[ep_id] = turns
        total = sum(t["reward"] for t in turns)
        rewards_sum += total
        last = turns[-1]
        reached = last["info"].get("event") == "goal"
        successes += int(reached)
        episodes.append(
            {
                "episode_id": ep_id,
                "seed": seed,
                "steps": len(turns),
                "total_reward": round(total, 3),
                "outcome": "goal" if reached else last["info"].get("event", "truncated"),
            }
        )

    export = {
        "schema_version": "1",
        "placeholder": True,
        "run": {
            "scores": {
                "mean_reward": round(rewards_sum / len(seeds), 3),
                "success_rate": round(successes / len(seeds), 3),
            }
        },
        "episodes": episodes,
        "replay": replay,
    }

    out_dir = Path(__file__).resolve().parent
    (out_dir / "replay.json").write_text(json.dumps(export, indent=2), encoding="utf-8")
    js = "window.REPLAY = " + json.dumps(export, indent=2) + ";\n"
    (out_dir / "replay.js").write_text(js, encoding="utf-8")
    print(f"wrote {out_dir/'replay.json'}")
    print(f"wrote {out_dir/'replay.js'}")


if __name__ == "__main__":
    main()
