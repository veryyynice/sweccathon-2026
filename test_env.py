"""Local sanity checks — run before submitting.

    python test_env.py

Asserts:
  1. Determinism: same (seed, action sequence) replays identically.
  2. Discrimination: a smart operator (forecast the evening, then dispatch at the
     true peak) scores much higher than a dumb operator (blind guess).
"""

from __future__ import annotations

import math
import random

from env import EVENING_WINDOW, HOURS, MAX_DISCHARGE_RATE, GridBalancerEnv


def run_episode(seed: int, policy) -> tuple[float, list]:
    """Drive an episode with a policy that maps observation -> action."""
    env = GridBalancerEnv()
    obs = env.reset(seed=seed)
    total = 0.0
    trace = []
    while True:
        action = policy(obs)
        result = env.step(action)
        total += result.reward
        trace.append((action.get("action"), round(result.reward, 2)))
        obs = result.observation
        if result.terminated or result.truncated:
            break
    return total, trace


def smart_policy_factory():
    """Forecast each candidate evening hour once (extreme = exact), then
    discharge exactly what the discovered peak needs."""
    state = {"phase": "scan", "idx": 0, "readings": {}}
    lo, hi = EVENING_WINDOW

    def policy(obs):
        # Use the forecast history the env echoes back to find the peak.
        for f in obs.get("forecasts_purchased", []):
            state["readings"][f["hour"]] = f["observed"]
        hours_to_scan = list(range(lo, hi + 1))
        if state["idx"] < len(hours_to_scan):
            h = hours_to_scan[state["idx"]]
            state["idx"] += 1
            return {"action": "forecast", "tier": "extreme", "target_hour": h}
        # All scanned → dispatch at the discovered peak.
        peak = max(state["readings"], key=state["readings"].get)
        required = state["readings"][peak] - obs["grid_capacity"]
        amount = max(0, min(MAX_DISCHARGE_RATE, int(math.ceil(required))))
        schedule = [0] * HOURS
        schedule[peak] = amount
        return {"action": "dispatch", "battery_schedule": schedule}

    return policy


def dumb_policy_factory(seed: int):
    """Buy one cheap noisy forecast at a random hour, then dispatch a random
    schedule with no real plan."""
    rng = random.Random(seed ^ 0xABCD)
    state = {"acted": False}

    def policy(obs):
        if not state["acted"]:
            state["acted"] = True
            return {"action": "forecast", "tier": "quick", "target_hour": rng.randint(0, HOURS - 1)}
        schedule = [rng.choice([0, 0, 0, 2, 5]) for _ in range(HOURS)]
        return {"action": "dispatch", "battery_schedule": schedule}

    return policy


def test_determinism() -> None:
    for seed in range(8):
        t1, tr1 = run_episode(seed, smart_policy_factory())
        t2, tr2 = run_episode(seed, smart_policy_factory())
        assert tr1 == tr2, f"seed {seed}: trace not deterministic"
        assert t1 == t2, f"seed {seed}: total reward not deterministic"
    print("✓ determinism: identical replays across 8 seeds")


def test_discrimination() -> None:
    seeds = range(12)
    smart = sum(run_episode(s, smart_policy_factory())[0] for s in seeds) / len(seeds)
    dumb = sum(run_episode(s, dumb_policy_factory(s))[0] for s in seeds) / len(seeds)
    print(f"  smart mean score = {smart:.2f}")
    print(f"  dumb  mean score = {dumb:.2f}")
    assert smart > dumb + 100, "env does not discriminate smart vs dumb operator"
    print("✓ discrimination: smart operator beats dumb operator")


if __name__ == "__main__":
    test_determinism()
    test_discrimination()
    print("\nAll checks passed.")
