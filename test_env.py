"""Local sanity checks — run before submitting.

    python test_env.py

Asserts two things the platform cares about:
  1. Determinism: same (seed, actions) replays identically.
  2. Discrimination: a smart policy and a dumb policy get DIFFERENT scores,
     so the env actually measures something.
"""

from __future__ import annotations

import random

from env import ACTIONS, GridRunnerEnv


def _rollout(seed: int, policy) -> tuple[list[float], list[str]]:
    """Run one episode under `policy`, returning (rewards, action-trace)."""
    env = GridRunnerEnv()
    obs = env.reset(seed=seed)
    rewards: list[float] = []
    actions: list[str] = []
    while True:
        action = policy(obs, seed=seed, step=len(actions))
        result = env.step(action)
        actions.append(str(action))
        rewards.append(result.reward)
        obs = result.observation
        if result.terminated or result.truncated:
            break
    return rewards, actions


def smart_policy(obs, **_):
    """Greedy: step toward the goal, preferring the larger axis gap."""
    ar, ac = obs["agent"]
    gr, gc = obs["goal"]
    dr, dc = gr - ar, gc - ac
    if abs(dr) >= abs(dc) and dr != 0:
        return "down" if dr > 0 else "up"
    if dc != 0:
        return "right" if dc > 0 else "left"
    return "down" if dr > 0 else "up"


def dumb_policy(obs, *, seed: int, step: int, **_):
    """Deterministic-but-uninformed: a fixed pseudo-random walk."""
    rng = random.Random((seed << 8) ^ step)
    return rng.choice(ACTIONS)


def test_determinism() -> None:
    for seed in range(8):
        r1, a1 = _rollout(seed, smart_policy)
        r2, a2 = _rollout(seed, smart_policy)
        assert a1 == a2, f"seed {seed}: action trace not deterministic"
        assert r1 == r2, f"seed {seed}: reward trace not deterministic"
    print("✓ determinism: identical replays across 8 seeds")


def test_discrimination() -> None:
    smart_total = sum(sum(_rollout(s, smart_policy)[0]) for s in range(8))
    dumb_total = sum(sum(_rollout(s, dumb_policy)[0]) for s in range(8))
    smart_mean = smart_total / 8
    dumb_mean = dumb_total / 8
    print(f"  smart mean reward = {smart_mean:.2f}")
    print(f"  dumb  mean reward = {dumb_mean:.2f}")
    assert smart_mean > dumb_mean, "env does not discriminate smart vs dumb policy"
    print("✓ discrimination: smart policy beats dumb policy")


if __name__ == "__main__":
    test_determinism()
    test_discrimination()
    print("\nAll checks passed.")
