"""Read an active-low float switch through Linux GPIO character devices."""

import statistics
import time
from datetime import timedelta


class FloatSwitchStateMonitor:
    """Confirm float transitions after consecutive stable samples."""

    def __init__(
        self,
        low_water_confirmations=3,
        water_ok_confirmations=10,
        initial_state=None,
    ):
        self.confirmations = {
            "low_water": max(1, int(low_water_confirmations)),
            "water_ok": max(1, int(water_ok_confirmations)),
        }
        self.confirmed_state = (
            initial_state if initial_state in {"low_water", "water_ok"} else None
        )
        self.candidate_state = None
        self.candidate_count = 0

    def observe(self, triggered):
        if triggered is None:
            self.candidate_state = None
            self.candidate_count = 0
            return None

        observed_state = "low_water" if triggered else "water_ok"
        if observed_state == self.confirmed_state:
            self.candidate_state = None
            self.candidate_count = 0
            return None

        if observed_state == self.candidate_state:
            self.candidate_count += 1
        else:
            self.candidate_state = observed_state
            self.candidate_count = 1

        if self.candidate_count < self.confirmations[observed_state]:
            return None

        previous_state = self.confirmed_state
        self.confirmed_state = observed_state
        self.candidate_state = None
        self.candidate_count = 0

        if previous_state is None and observed_state == "water_ok":
            return None
        return observed_state


def majority_triggered(samples) -> bool:
    values = [bool(value) for value in samples]
    if not values:
        raise ValueError("at least one float switch sample is required")
    return statistics.median(values) == 1


def read_triggered(
    gpio: int = 17,
    chip: str = "/dev/gpiochip0",
    samples: int = 5,
    interval_seconds: float = 0.05,
) -> bool:
    import gpiod
    from gpiod.line import Bias, Direction, Value

    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        bias=Bias.PULL_UP,
        active_low=True,
        debounce_period=timedelta(milliseconds=20),
    )
    results = []
    with gpiod.request_lines(
        chip,
        consumer="plant-float-switch",
        config={gpio: settings},
    ) as request:
        for index in range(max(1, samples)):
            results.append(request.get_value(gpio) == Value.ACTIVE)
            if index + 1 < samples:
                time.sleep(max(0.0, interval_seconds))
    return majority_triggered(results)
