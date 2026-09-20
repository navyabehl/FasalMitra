"""
FasalMitra - Decision logic (v2 — percentile / volatility / trend model)

The original version compared today's price to a flat 30-day average
with a fixed -3% threshold and a two-point (day-1 vs day-7) trend
check. That was almost never triggering WAIT because:
  - a fixed % threshold means something very different for a low-
    volatility crop (wheat, ~6% swings) than a high-volatility one
    (tomato, ~30% swings) — the same 3% is a real signal for one and
    pure noise for the other
  - comparing two single days for "trend" is extremely noisy
  - 30 days isn't long enough to see a real seasonal glut-and-recovery
    pattern in most crops

This version fixes all four things:
  1. PERCENTILE RANK: where does today's price fall within the last
     ~90 days, not just "above/below a flat average"? Being in the
     bottom quartile of 90 days is a much stronger "this is genuinely
     a low point" signal than a fixed percentage.
  2. VOLATILITY-NORMALIZED (z-score): how many standard deviations
     below the window's mean is today's price, using THIS crop's own
     historical volatility — fixes the wheat-vs-tomato asymmetry.
  3. REGRESSION TREND: a proper least-squares slope over the most
     recent ~21 days instead of a two-point comparison — much less
     noisy.
  4. LONGER WINDOW: up to 90 days (see utils/data.py) instead of 30,
     so 1-3 above actually have enough history to mean something.

No new dependency is needed — mean/percentile/stdev/regression are
all implemented with Python's stdlib `statistics` module and plain
arithmetic (ordinary least squares), which also keeps the method
transparent and easy to explain in a project write-up.
"""

import statistics
from .data import CROPS


def _ols_slope(values: list) -> float:
    """Ordinary least-squares slope of `values` against 0..n-1 (i.e.
    price change per day). Standard formula:
        slope = (n*Sum(xy) - Sum(x)*Sum(y)) / (n*Sum(x^2) - (Sum(x))^2)
    Returns 0.0 for fewer than 2 points (no meaningful trend).
    """
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x ** 2
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def analyze(crop: str, prices: list, quantity_quintals: float, facilities: list):
    values = [p["price"] for p in prices]
    n = len(values)
    today_price = values[-1]
    avg_price = statistics.mean(values)
    std_price = statistics.pstdev(values) if n > 1 else 0.0

    # 1. Percentile rank of today's price within the whole window
    #    (0 = lowest price seen, 100 = highest).
    #    Uses strict less-than so a price equal to the median scores ~50,
    #    not 100 (self-inclusive counting inflates the rank when tied values
    #    exist — especially on simulated or low-resolution series).
    percentile_rank = (sum(1 for v in values if v < today_price) / n) * 100

    # 2. Volatility-normalized deviation (z-score). 0 when the window
    #    is flat (std=0) so a truly flat series never falsely triggers.
    z_score = (today_price - avg_price) / std_price if std_price > 0 else 0.0

    # 3. Regression trend over the most recent ~21 days (or the whole
    #    window if shorter), in Rs/quintal per day.
    trend_window = values[-min(21, n):]
    trend_slope = _ols_slope(trend_window)

    pct_vs_avg = (today_price - avg_price) / avg_price * 100
    spoilage_days = CROPS[crop]["spoilage_days"]

    # A "genuine low point worth waiting out": bottom quartile of the
    # window AND at least half a standard deviation below the mean AND
    # the recent trend is actually recovering (positive slope) — all
    # three have to agree, not just one noisy signal.
    is_low_point = percentile_rank <= 25
    is_significant_dip = z_score <= -0.5
    is_recovering = trend_slope > 0

    if is_low_point and is_significant_dip and is_recovering:
        # How many days to suggest waiting scales with how deep into
        # low territory we are — deeper dip, longer suggested wait,
        # capped well inside the crop's safe spoilage window.
        # min(..., 3) ensures at least 3 days so the gate below is always met.
        deficit = 25 - percentile_rank  # 0-25, bigger = lower percentile
        suggested_days = min(max(int(deficit * 0.7), 3), spoilage_days // 2)

        # Project the price forward using the regression slope, but
        # cap the projection at the window's 75th percentile — don't
        # let a steep recent slope extrapolate to an unrealistic
        # price the window itself never actually reached.
        sorted_vals = sorted(values)
        p75 = sorted_vals[int(0.75 * (n - 1))]
        naive_projection = today_price + trend_slope * suggested_days
        projected_price = min(naive_projection, max(p75, today_price))
    else:
        suggested_days = 0
        projected_price = today_price

    potential_gain = (projected_price - today_price) * quantity_quintals

    avg_rate = (
        sum(f["rate_per_qtl_day"] for f in facilities) / len(facilities)
        if facilities else 1.15
    )
    storage_cost = avg_rate * quantity_quintals * suggested_days
    net_benefit = potential_gain - storage_cost

    # suggested_days is always >= 3 when is_low_point/dip/recovering all hold,
    # so the redundant `suggested_days > 0` guard has been removed.
    should_wait = (
        is_low_point and is_significant_dip and is_recovering
        and net_benefit > 0
        and suggested_days <= spoilage_days
    )

    return {
        "today_price": round(today_price),
        "avg_price": round(avg_price),
        "pct_vs_avg": round(pct_vs_avg, 1),
        "percentile_rank": round(percentile_rank, 1),
        "z_score": round(z_score, 2),
        "trend_slope": round(trend_slope, 2),
        "trend_direction": 1 if trend_slope > 0 else -1,
        "should_wait": should_wait,
        "suggested_days": suggested_days,
        "projected_price": round(projected_price),
        "potential_gain": round(potential_gain),
        "storage_cost": round(storage_cost),
        "net_benefit": round(net_benefit),
        "spoilage_days": spoilage_days,
        "window_days": n,
    }
