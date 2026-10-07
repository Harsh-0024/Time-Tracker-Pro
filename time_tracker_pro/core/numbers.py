from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: float, ndigits: int) -> float:
    """Round like the browser's Number.toFixed (halves away from zero).

    Python's round() rounds halves to even, so 3.25h (a 15-minute multiple)
    became 3.2h on the server but 3.3h in the JS-rendered views.
    """
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return number
    quantum = Decimal(1).scaleb(-int(ndigits))
    return float(Decimal(repr(number)).quantize(quantum, rounding=ROUND_HALF_UP))
