"""Long Horizon Grid Balancer — a Mesocosm environment.

You are a Grid Operator. A hidden evening demand spike threatens grid failure.
You hold a limited battery reserve. Each turn you may either:

  1. Buy a FORECAST of the hidden net load at one hour, at a chosen precision
     tier (cost vs. noise trade-off), or
  2. Submit a final 24-hour battery DISPATCH schedule and end the episode.

Final Score = (1000 if the dispatch prevents grid failure at the true hidden
evening peak, else 0) - total_cost_of_forecasts.

Hard constraints honored here:
  - Determinism: ALL randomness goes through self._rng (random.Random(seed)).
  - info: every value is a string (json.dumps for lists/objects).
  - Intermediate (forecast) steps return reward 0; the score lands on the final
    dispatch (or on timeout).
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

# --- World constants ---------------------------------------------------------
HOURS = 24
GRID_CAPACITY = 100.0          # net load above this at the peak hour = grid failure
BATTERY_RESERVE = 70           # total dischargeable energy across the day
MAX_DISCHARGE_RATE = 70        # per-hour battery limit (charge or discharge)
EVENING_WINDOW = (16, 22)      # the spike hides somewhere in here
PEAK_HOURS = [17, 18, 19, 20]  # candidate true-peak hours
SUCCESS_BONUS = 1000.0
MAX_STEPS = 30                 # <= 35

# Forecast tiers: exact costs + noise (std dev of Gaussian error).
FORECAST_TIERS: dict[str, dict[str, float]] = {
    "quick":     {"cost": 1.0,  "noise": 25.0},  # High noise
    "standard":  {"cost": 3.0,  "noise": 12.0},  # Medium noise
    "precision": {"cost": 7.0,  "noise": 4.0},   # Low noise
    "extreme":   {"cost": 10.0, "noise": 0.0},   # Zero noise
}


class GridBalancerEnv(BaseEnv):
    def __init__(self) -> None:
        self._rng = random.Random()
        self._demand: list[float] = []
        self._peak_hour = 0
        self._required = 0.0
        self._budget_spent = 0.0
        self._forecasts: list[dict[str, Any]] = []
        self._steps = 0
        self._done = False

    # -- lifecycle ------------------------------------------------------------
    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng = random.Random(seed)

        # Smooth daily baseline, all comfortably below grid capacity.
        base = [50.0 + 15.0 * math.sin(2 * math.pi * (h - 9) / HOURS) for h in range(HOURS)]
        demand = [b + self._rng.uniform(-5.0, 5.0) for b in base]

        # Hide an evening spike that exceeds capacity.
        self._peak_hour = self._rng.choice(PEAK_HOURS)
        spike = self._rng.uniform(30.0, 60.0)
        demand[self._peak_hour] = GRID_CAPACITY + spike
        self._demand = [round(d, 2) for d in demand]
        self._required = round(self._demand[self._peak_hour] - GRID_CAPACITY, 2)

        self._budget_spent = 0.0
        self._forecasts = []
        self._steps = 0
        self._done = False
        return self._observation(forecast_result=None, target_hour=None)

    def step(self, action: Any) -> StepResult:
        if self._done:
            raise RuntimeError("Episode finished — call reset() before step().")

        self._steps += 1
        act = self._coerce(action)
        kind = str(act.get("action", "")).strip().lower()

        if kind == "forecast":
            return self._do_forecast(act)
        if kind == "dispatch":
            return self._do_dispatch(act)
        return self._do_invalid(act)

    # -- action handlers ------------------------------------------------------
    def _do_forecast(self, act: dict[str, Any]) -> StepResult:
        tier = str(act.get("tier", "quick")).strip().lower()
        if tier not in FORECAST_TIERS:
            tier = "quick"
        try:
            target = int(act.get("target_hour", 0))
        except (TypeError, ValueError):
            target = 0
        target = max(0, min(HOURS - 1, target))

        cost = FORECAST_TIERS[tier]["cost"]
        noise_std = FORECAST_TIERS[tier]["noise"]
        self._budget_spent += cost

        true_val = self._demand[target]
        noise = self._rng.gauss(0.0, noise_std) if noise_std > 0 else 0.0
        observed = round(true_val + noise, 2)
        self._forecasts.append({"hour": target, "tier": tier, "observed": observed})

        truncated = self._steps >= MAX_STEPS
        reward = 0.0
        event = "forecast"
        if truncated:
            # Ran out of steps without dispatching → no bonus, pay the bills.
            reward = -self._budget_spent
            event = "timeout"
            self._done = True

        info = self._info(
            event=event,
            target_hour=target,
            forecast_result=observed,
            noise_applied=noise_std,
            success=False,
            score=reward if truncated else 0.0,
        )
        return StepResult(
            observation=self._observation(forecast_result=observed, target_hour=target),
            reward=reward,
            terminated=False,
            truncated=truncated,
            info=info,
        )

    def _do_dispatch(self, act: dict[str, Any]) -> StepResult:
        schedule = act.get("battery_schedule", [])
        success, reason = self._evaluate(schedule)
        score = (SUCCESS_BONUS if success else 0.0) - self._budget_spent
        self._done = True

        info = self._info(
            event="dispatch",
            target_hour=None,
            forecast_result=None,
            noise_applied=0.0,
            success=success,
            score=score,
            dispatch_reason=reason,
            schedule=schedule,
        )
        return StepResult(
            observation=self._observation(forecast_result=None, target_hour=None),
            reward=score,
            terminated=True,
            truncated=False,
            info=info,
        )

    def _do_invalid(self, act: dict[str, Any]) -> StepResult:
        truncated = self._steps >= MAX_STEPS
        reward = 0.0
        event = "invalid_action"
        if truncated:
            reward = -self._budget_spent
            event = "timeout"
            self._done = True
        info = self._info(
            event=event,
            target_hour=None,
            forecast_result=None,
            noise_applied=0.0,
            success=False,
            score=reward if truncated else 0.0,
        )
        return StepResult(
            observation=self._observation(forecast_result=None, target_hour=None),
            reward=reward,
            terminated=False,
            truncated=truncated,
            info=info,
        )

    # -- evaluation -----------------------------------------------------------
    def _evaluate(self, schedule: Any) -> tuple[bool, str]:
        if not isinstance(schedule, list) or len(schedule) != HOURS:
            return False, "bad_length"
        try:
            sched = [int(round(float(s))) for s in schedule]
        except (TypeError, ValueError):
            return False, "non_numeric"
        if any(abs(s) > MAX_DISCHARGE_RATE for s in sched):
            return False, "rate_exceeded"
        total_discharge = sum(s for s in sched if s > 0)
        if total_discharge > BATTERY_RESERVE:
            return False, "reserve_exceeded"
        if sched[self._peak_hour] >= self._required:
            return True, "prevented"
        return False, "peak_overload"

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _coerce(action: Any) -> dict[str, Any]:
        if isinstance(action, dict):
            return action
        if isinstance(action, str):
            try:
                parsed = json.loads(action)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {}

    def _observation(self, *, forecast_result: float | None, target_hour: int | None) -> dict[str, Any]:
        return {
            "role": "Grid Operator — prevent the hidden evening peak from overloading the grid.",
            "horizon_hours": HOURS,
            "grid_capacity": GRID_CAPACITY,
            "battery_reserve": BATTERY_RESERVE,
            "max_discharge_rate": MAX_DISCHARGE_RATE,
            "evening_window": list(EVENING_WINDOW),
            "forecast_tiers": {
                t: {"cost": v["cost"], "noise_std": v["noise"]} for t, v in FORECAST_TIERS.items()
            },
            "budget_spent": round(self._budget_spent, 2),
            "steps_taken": self._steps,
            "max_steps": MAX_STEPS,
            "forecasts_purchased": list(self._forecasts),
            "last_forecast": (
                None if forecast_result is None else {"hour": target_hour, "observed": forecast_result}
            ),
            "action_schema": {
                "forecast": {"action": "forecast", "tier": "quick|standard|precision|extreme", "target_hour": "int 0-23"},
                "dispatch": {"action": "dispatch", "battery_schedule": "list of 24 ints (+discharge / -charge)"},
            },
        }

    def _info(
        self,
        *,
        event: str,
        target_hour: int | None,
        forecast_result: float | None,
        noise_applied: float,
        success: bool,
        score: float,
        dispatch_reason: str = "",
        schedule: Any = None,
    ) -> dict[str, str]:
        # EVERY value is a string — json.dumps anything structured.
        return {
            "event": event,
            "total_budget_spent": str(round(self._budget_spent, 2)),
            "current_noise_applied": str(noise_applied),
            "this_turn_target_hour": "" if target_hour is None else str(target_hour),
            "this_turn_forecast_result": "" if forecast_result is None else str(forecast_result),
            "true_demand_curve": json.dumps(self._demand),
            "true_peak_hour": str(self._peak_hour),
            "required_discharge": str(self._required),
            "grid_capacity": str(GRID_CAPACITY),
            "forecasts_purchased": json.dumps(self._forecasts),
            "step": str(self._steps),
            "success": "true" if success else "false",
            "dispatch_success": "1" if success else "0",
            "score": str(round(score, 2)),
            "dispatch_reason": dispatch_reason,
            "submitted_schedule": "" if schedule is None else json.dumps(schedule),
        }
