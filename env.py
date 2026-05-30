"""Mesocosm environment — implement reset() and step().

==============================================================================
THIS IS A SKELETON.  Swap the gridworld below for your real env idea.
The structure (seeded RNG, string-only info, shaped scalar reward, discrete
actions, max_steps guard) is the part you want to KEEP — it satisfies the
hard constraints the platform enforces. Replace the *game logic* only.
==============================================================================

Hard constraints baked into this skeleton (do not break these):
  - Determinism: ALL randomness goes through self._rng (random.Random(seed)).
    Never use the global `random`, never use time / os.urandom. Same
    (seed, actions) MUST replay identically.
  - info: EVERY value in the info dict is a string (json.dumps lists/objects).
    Put everything the showcase needs to render a turn into info.
  - Episode length is capped (see MAX_STEPS, must stay <= 35 in the manifest).
"""

from __future__ import annotations

import json
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

# --- Tunables (skeleton placeholder: a small gridworld) ----------------------
GRID_SIZE = 6
N_HAZARDS = 4
MAX_STEPS = 30  # keep <= 35

ACTIONS = ["up", "down", "left", "right"]
_DELTAS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

# Reward shaping (non-binary: scales up for good moves, down for bad ones).
GOAL_REWARD = 10.0
HAZARD_REWARD = -10.0
STEP_TOWARD = 1.0
STEP_AWAY = -1.0
STEP_WALL = -1.5


class GridRunnerEnv(BaseEnv):
    """Navigate a grid from the top-left to a goal cell while avoiding hazards.

    Replace this class body with your own env — keep the reset()/step() shape.
    """

    def __init__(self) -> None:
        self._rng = random.Random()
        self._size = GRID_SIZE
        self._agent: tuple[int, int] = (0, 0)
        self._goal: tuple[int, int] = (0, 0)
        self._hazards: set[tuple[int, int]] = set()
        self._steps = 0
        self._done = False

    # -- lifecycle ------------------------------------------------------------
    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng = random.Random(seed)
        size = int(params.get("grid_size", GRID_SIZE))
        self._size = size

        self._agent = (0, 0)

        # Goal: anywhere except the start corner.
        cells = [
            (r, c)
            for r in range(size)
            for c in range(size)
            if (r, c) != (0, 0)
        ]
        self._goal = self._rng.choice(cells)

        # Hazards: distinct cells, never on start or goal.
        forbidden = {(0, 0), self._goal}
        candidates = [c for c in cells if c not in forbidden]
        n_haz = min(int(params.get("n_hazards", N_HAZARDS)), len(candidates))
        self._hazards = set(self._rng.sample(candidates, n_haz))

        self._steps = 0
        self._done = False
        return self._observation()

    def step(self, action: Any) -> StepResult:
        if self._done:
            raise RuntimeError("Episode finished — call reset() before step().")

        move = self._parse_action(action)
        self._steps += 1

        prev_dist = self._manhattan(self._agent, self._goal)
        event = "move"
        reward = 0.0

        if move is None:
            event = "invalid_action"
            reward = STEP_WALL
            new_pos = self._agent
        else:
            dr, dc = _DELTAS[move]
            r, c = self._agent
            nr, nc = r + dr, c + dc
            if not (0 <= nr < self._size and 0 <= nc < self._size):
                event = "wall"
                reward = STEP_WALL
                new_pos = self._agent
            else:
                new_pos = (nr, nc)

        self._agent = new_pos
        new_dist = self._manhattan(self._agent, self._goal)

        terminated = False
        if event == "move":
            if self._agent == self._goal:
                event = "goal"
                reward = GOAL_REWARD
                terminated = True
            elif self._agent in self._hazards:
                event = "hazard"
                reward = HAZARD_REWARD
                terminated = True
            elif new_dist < prev_dist:
                reward = STEP_TOWARD
            else:
                reward = STEP_AWAY

        truncated = (not terminated) and self._steps >= MAX_STEPS
        self._done = terminated or truncated

        return StepResult(
            observation=self._observation(),
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            info=self._info(event=event, last_action=move, distance=new_dist),
        )

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _parse_action(action: Any) -> str | None:
        text = str(action).strip().lower()
        return text if text in _DELTAS else None

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _observation(self) -> dict[str, Any]:
        return {
            "grid_size": self._size,
            "agent": list(self._agent),
            "goal": list(self._goal),
            "hazards": [list(h) for h in sorted(self._hazards)],
            "steps": self._steps,
            "legal_actions": ACTIONS,
        }

    def _info(self, *, event: str, last_action: str | None, distance: int) -> dict[str, str]:
        # EVERY value must be a string — json.dumps anything structured.
        return {
            "event": event,
            "last_action": str(last_action),
            "distance_to_goal": str(distance),
            "step": str(self._steps),
            "grid_size": str(self._size),
            "agent": json.dumps(list(self._agent)),
            "goal": json.dumps(list(self._goal)),
            "hazards": json.dumps([list(h) for h in sorted(self._hazards)]),
        }
