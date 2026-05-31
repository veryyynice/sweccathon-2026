"""Efficient Scientific Discovery benchmark environment."""

from __future__ import annotations

import json
import math
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

LAW_FAMILIES = ("linear", "quadratic", "exponential", "periodic", "piecewise")
PRECISION_SETTINGS = {
    "cheap": {"cost": 1.0, "noise_std": 2.5},
    "standard": {"cost": 3.0, "noise_std": 1.0},
    "high": {"cost": 7.0, "noise_std": 0.25},
}


class MyEnv(BaseEnv):
    def __init__(self) -> None:
        self._rng = random.Random()
        self._budget_start = 20.0
        self._max_steps = 15
        self._x_min = -8.0
        self._x_max = 8.0
        self._steps = 0
        self._done = False
        self._budget_remaining = self._budget_start
        self._history: list[dict[str, Any]] = []
        self._law_family = "linear"
        self._law_params: dict[str, float] = {}

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng.seed(seed)
        self._steps = 0
        self._done = False
        self._budget_remaining = self._budget_start
        self._history = []
        self._law_family = self._rng.choice(LAW_FAMILIES)
        self._law_params = self._sample_law_params(self._law_family)
        return self._make_observation(last_result="episode_started")

    def step(self, action: Any) -> StepResult:
        if self._done:
            raise RuntimeError("Episode already ended. Call reset() for a new episode.")

        self._steps += 1
        parsed_action = self._parse_action(action)

        if parsed_action is None:
            result = StepResult(
                observation=self._make_observation(last_result="invalid_action"),
                reward=-2.0,
                terminated=False,
                truncated=False,
                info={"error": "Action must be valid JSON or dict."},
            )
            return self._apply_step_limit(result)

        action_type = parsed_action.get("type")
        if action_type == "experiment":
            result = self._handle_experiment(parsed_action)
            return self._apply_step_limit(result)
        if action_type == "submit":
            result = self._handle_submit(parsed_action)
            return self._apply_step_limit(result)

        result = StepResult(
            observation=self._make_observation(last_result="invalid_action_type"),
            reward=-2.0,
            terminated=False,
            truncated=False,
            info={"error": "type must be experiment or submit."},
        )
        return self._apply_step_limit(result)

    def _parse_action(self, action: Any) -> dict[str, Any] | None:
        if isinstance(action, dict):
            return action
        if isinstance(action, str):
            try:
                parsed = json.loads(action)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                return parsed
        return None

    def _handle_experiment(self, action: dict[str, Any]) -> StepResult:
        precision = str(action.get("precision", "")).lower()
        if precision not in PRECISION_SETTINGS:
            return StepResult(
                observation=self._make_observation(last_result="invalid_precision"),
                reward=-1.5,
                terminated=False,
                truncated=False,
                info={"error": "precision must be cheap, standard, or high."},
            )

        x_value = action.get("x")
        try:
            x = float(x_value)
        except (TypeError, ValueError):
            return StepResult(
                observation=self._make_observation(last_result="invalid_x"),
                reward=-1.5,
                terminated=False,
                truncated=False,
                info={"error": "x must be a numeric value."},
            )

        if x < self._x_min or x > self._x_max:
            return StepResult(
                observation=self._make_observation(last_result="x_out_of_range"),
                reward=-1.0,
                terminated=False,
                truncated=False,
                info={"error": f"x must be between {self._x_min} and {self._x_max}."},
            )

        cost = PRECISION_SETTINGS[precision]["cost"]
        if self._budget_remaining < cost:
            return StepResult(
                observation=self._make_observation(last_result="insufficient_budget"),
                reward=-1.0,
                terminated=False,
                truncated=False,
                info={"error": "Not enough budget for requested precision."},
            )

        noise_std = PRECISION_SETTINGS[precision]["noise_std"]
        clean_y = self._evaluate_law(x)
        noisy_y = clean_y + self._rng.gauss(0.0, noise_std)

        self._budget_remaining -= cost
        self._history.append(
            {
                "step": self._steps,
                "x": round(x, 4),
                "precision": precision,
                "cost": cost,
                "observed_y": round(noisy_y, 4),
            }
        )

        terminated = self._budget_remaining < min(p["cost"] for p in PRECISION_SETTINGS.values())
        reward = -cost
        if terminated:
            self._done = True
            reward -= 5.0

        return StepResult(
            observation=self._make_observation(last_result="experiment_recorded"),
            reward=reward,
            terminated=terminated,
            truncated=False,
            info={
                "last_x": str(round(x, 4)),
                "last_observed_y": str(round(noisy_y, 4)),
                "last_precision": precision,
                "hidden_family": self._law_family if terminated else "hidden",
            },
        )

    def _handle_submit(self, action: dict[str, Any]) -> StepResult:
        guess = str(action.get("law", "")).lower().strip()
        correct = guess == self._law_family
        self._done = True

        correctness_bonus = 80.0 if correct else -30.0
        reward = correctness_bonus + self._budget_remaining

        return StepResult(
            observation=self._make_observation(last_result="submitted", reveal_law=True),
            reward=reward,
            terminated=True,
            truncated=False,
            info={
                "correct": str(correct),
                "submitted_law": guess,
                "true_law": self._law_family,
                "budget_remaining": str(round(self._budget_remaining, 2)),
            },
        )

    def _make_observation(self, last_result: str, reveal_law: bool = False) -> dict[str, Any]:
        return {
            "task": "Identify the hidden law family under budget and noise constraints.",
            "law_families": list(LAW_FAMILIES),
            "action_format": {
                "experiment": {
                    "type": "experiment",
                    "x": "float between -8 and 8",
                    "precision": "cheap|standard|high",
                },
                "submit": {"type": "submit", "law": "one of law_families"},
            },
            "budget_remaining": round(self._budget_remaining, 2),
            "step": self._steps,
            "max_steps": self._max_steps,
            "history": self._history,
            "last_result": last_result,
            "hidden_law": self._law_family if reveal_law else "hidden",
        }

    def _apply_step_limit(self, result: StepResult) -> StepResult:
        if result.terminated:
            return result
        if self._steps >= self._max_steps:
            self._done = True
            return StepResult(
                observation=self._make_observation(last_result="step_limit_reached", reveal_law=True),
                reward=result.reward - 10.0,
                terminated=False,
                truncated=True,
                info={"true_law": self._law_family, "reason": "max_steps_reached"},
            )
        return result

    def _sample_law_params(self, family: str) -> dict[str, float]:
        if family == "linear":
            return {
                "a": self._rng.uniform(0.5, 3.0) * self._rng.choice((-1.0, 1.0)),
                "b": self._rng.uniform(-4.0, 4.0),
            }
        if family == "quadratic":
            return {
                "a": self._rng.uniform(0.4, 1.6),
                "b": self._rng.uniform(-2.0, 2.0),
                "c": self._rng.uniform(-4.0, 4.0),
            }
        if family == "exponential":
            return {
                "a": self._rng.uniform(0.6, 2.0),
                "b": self._rng.uniform(0.2, 0.5),
                "c": self._rng.uniform(-3.0, 3.0),
            }
        if family == "periodic":
            return {
                "a": self._rng.uniform(2.0, 6.0),
                "w": self._rng.uniform(0.6, 1.4),
                "phi": self._rng.uniform(-math.pi / 2.0, math.pi / 2.0),
                "c": self._rng.uniform(-2.0, 2.0),
            }
        return {
            "left_m": self._rng.uniform(-2.5, -0.5),
            "left_b": self._rng.uniform(-4.0, 2.0),
            "right_m": self._rng.uniform(0.5, 2.5),
            "right_b": self._rng.uniform(-2.0, 4.0),
        }

    def _evaluate_law(self, x: float) -> float:
        p = self._law_params
        if self._law_family == "linear":
            return p["a"] * x + p["b"]
        if self._law_family == "quadratic":
            return p["a"] * (x**2) + p["b"] * x + p["c"]
        if self._law_family == "exponential":
            return p["a"] * math.exp(p["b"] * x) + p["c"]
        if self._law_family == "periodic":
            return p["a"] * math.sin(p["w"] * x + p["phi"]) + p["c"]
        if x < 0:
            return p["left_m"] * x + p["left_b"]
        return p["right_m"] * x + p["right_b"]
