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


def _flag(level, code, title, message, value, threshold):
    return {"level": level, "code": code, "title": title, "message": message,
            "value": float(value), "threshold": float(threshold)}


def warnings(summary, downside, conc, corr, contributions, positions) -> list[dict]:
    t = config.THRESHOLDS
    out = []

    top = conc["top_position"]
    if top["weight"] > t["max_position_weight"]:
        out.append(_flag("warning", "position_weight", "Single position is large",
                         f"{top['ticker']} is {top['weight']:.0%} of the book, above {t['max_position_weight']:.0%}.",
                         top["weight"], t["max_position_weight"]))

    if conc["top3_weight"] > t["top3_weight"]:
        out.append(_flag("warning", "top3_weight", "Top three positions dominate",
                         f"The three largest positions are {conc['top3_weight']:.0%} of the book, above {t['top3_weight']:.0%}.",
                         conc["top3_weight"], t["top3_weight"]))

    sector = conc["largest_sector"]
    if sector and sector["weight"] > t["max_sector_weight"]:
        out.append(_flag("warning", "sector_weight", "Sector concentration",
                         f"{sector['sector']} is {sector['weight']:.0%} of the book, above {t['max_sector_weight']:.0%}.",
                         sector["weight"], t["max_sector_weight"]))

    if conc["effective_positions"] < t["min_effective_positions"]:
        out.append(_flag("warning", "effective_positions", "Few effective positions",
                         f"Weights behave like {conc['effective_positions']:.1f} equal positions, below {t['min_effective_positions']}.",
                         conc["effective_positions"], t["min_effective_positions"]))

    if summary["annualized_volatility"] > t["annualized_volatility"]:
        out.append(_flag("warning", "volatility", "High volatility",
                         f"Annualized volatility is {summary['annualized_volatility']:.1%}, above {t['annualized_volatility']:.0%}.",
                         summary["annualized_volatility"], t["annualized_volatility"]))

    if summary["max_drawdown"] < t["max_drawdown"]:
        out.append(_flag("critical", "max_drawdown", "Deep drawdown",
                         f"The book fell {summary['max_drawdown']:.1%} from its peak, past {t['max_drawdown']:.0%}.",
                         summary["max_drawdown"], t["max_drawdown"]))

    if downside["cvar_historical"] < t["cvar_95_daily"]:
        out.append(_flag("critical", "cvar", "Heavy downside tail",
                         f"Average loss on the worst 5% of days is {downside['cvar_historical']:.2%}, past {t['cvar_95_daily']:.0%}.",
                         downside["cvar_historical"], t["cvar_95_daily"]))

    if corr["average_pairwise"] > t["average_correlation"]:
        out.append(_flag("warning", "correlation", "Positions move together",
                         f"Average pairwise correlation is {corr['average_pairwise']:.2f}, above {t['average_correlation']:.2f}.",
                         corr["average_pairwise"], t["average_correlation"]))

    if summary["beta"] > t["beta"]:
        out.append(_flag("warning", "beta", "High market beta",
                         f"Beta to {summary['benchmark']} is {summary['beta']:.2f}, above {t['beta']:.2f}.",
                         summary["beta"], t["beta"]))

    for row in contributions:
        if row["weight"] > 0 and row["share"] / row["weight"] > t["risk_share_vs_weight"]:
            out.append(_flag("info", "risk_vs_weight", "Position carries outsized risk",
                             f"{row['ticker']} is {row['weight']:.0%} of the book but {row['share']:.0%} of its risk.",
                             row["share"] / row["weight"], t["risk_share_vs_weight"]))

    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda w: order[w["level"]])
    return out
