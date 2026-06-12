"""Read an active-low float switch through Linux GPIO character devices."""

import statistics
import time
from datetime import timedelta


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

