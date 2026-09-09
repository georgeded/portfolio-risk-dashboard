import config


def _score(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return float(min(100.0, max(0.0, (value - low) / (high - low) * 100)))


def risk_meter(volatility, max_drawdown, cvar, hhi, avg_correlation) -> dict:
    """Blend five 0 to 100 component scores into one level from Low to Very High."""
    inputs = {
        "volatility": ("Volatility", abs(volatility)),
        "max_drawdown": ("Max drawdown", abs(max_drawdown)),
        "cvar": ("Downside (CVaR 95)", abs(cvar)),
        "concentration": ("Concentration (HHI)", hhi),
        "correlation": ("Average correlation", avg_correlation),
    }
    components = []
    total = 0.0
    for key, (label, value) in inputs.items():
        spec = config.RISK_METER[key]
        s = _score(value, spec["low"], spec["high"])
        total += s * spec["weight"]
        components.append({"key": key, "name": label, "value": float(value), "score": round(s, 1),
                           "weight": spec["weight"]})
    level = next(name for cap, name in config.RISK_LEVELS if total < cap)
    return {"score": round(total, 1), "level": level, "components": components}
