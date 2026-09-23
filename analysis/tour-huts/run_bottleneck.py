"""Runs the tour bottleneck-hut study; writes bottleneck-results.json, bottleneck-candidates.csv and plots."""
from __future__ import annotations

import numpy as np
import pandas as pd

import bottleneck_steps as bs
import bottleneck_tours as bt
import common
import did
import fetch_tours
import stats
import tour_bottleneck as tb

N_BOOT = 2000
N_PLACEBO = 200
CAPS_KM = (15, 25, 40)
PUBLIC = common.ROOT / "huts" / "public" / "data"


def load_inputs():
    huts = common.read_json(common.OUT / "huts.json")["huts"]
    days = pd.read_csv(common.OUT / "hut-days.csv", parse_dates=["date"])
    raw = fetch_tours.parse_tours(common.read_json(common.OUT / "raw" / "tours.json")["body"])
    return huts, days, bt.load_tours(raw, huts)


def order_validation(tours: list[dict]) -> list[dict]:
    pipeline_tours = common.read_json(PUBLIC / "tours.json")
    hut_ids = common.read_json(PUBLIC / "hut-edge-payload.json")["hut_ids"]
    return bt.validate_orders(tours, pipeline_tours, hut_ids)


def season_results(season: int, tours: list[dict], bottlenecks: dict[str, int], huts: list[dict],
                   days: pd.DataFrame) -> dict:
    table = tb.hut_table(huts, days, season)
    hd = tb.hut_day_index(days, season)
    circular = {t["name"]: t["circular"] for t in tours}
    units, info = tb.tour_units(tours, bottlenecks, table, hd)
    out: dict = {"n_units": len(units), **info, "controls_km": tb.controls_km(units)}
    # The pre-defined test: power is computed before the coefficient inside primary_test.
    out["primary"] = bs.primary_test(units, hd, n_boot=N_BOOT)
    panel = tb.build_panel(units, hd, tb.aligned_treatment)
    tour_rows = panel[panel.tour == 1]
    out["ceiling"] = {
        "own_sold_out_share": float(tour_rows.own_sold_out.mean()) if len(tour_rows) else None,
        "did": did.fit_did(panel[~panel.own_sold_out])}
    out["cuts"] = {"fri_sun": did.fit_did(panel[panel.date.dt.dayofweek >= 4]),
                   "jul_aug": did.fit_did(panel[panel.date.dt.month.isin([7, 8])])}
    out["radius_km"] = {}
    for cap in CAPS_KM:
        u, _ = tb.tour_units(tours, bottlenecks, table, hd, cap_km=cap)
        out["radius_km"][cap] = did.fit_did(tb.build_panel(u, hd, tb.aligned_treatment))
    u_near, _ = tb.tour_units(tours, bottlenecks, table, hd, col="sold_out_near")
    out["sold_out_near"] = did.fit_did(tb.build_panel(u_near, hd, tb.aligned_treatment))
    out["offsets"] = bs.offset_profile([u for u in units if not circular[u["tour"]]], hd)
    out["per_tour"] = bs.per_tour(units, hd)
    effects = {t["name"]: bs.effect_by_a(t, table, hd) for t in tours if t["name"] in bottlenecks}
    out["effects_by_a"] = {t: {str(a): c for a, c in e.items()} for t, e in effects.items()}
    out["rank_test"] = bs.rank_test(effects, bottlenecks)
    placebo_units = []
    in_table = set(table.ohrs_id)
    for t in tours:
        a = bottlenecks.get(t["name"])
        if a is None or a not in in_table:
            continue
        p = tb.pick_placebo_a(a, table)
        if p is not None and p in hd:
            u, _ = tb.make_units(t, p, table, tb.a_full_series(hd[p]), ref_id=a)
            placebo_units += u
    out["placebo_a"] = bs.primary_test(placebo_units, hd)
    out["placebo_dates"] = bs.placebo_dates(units, hd, n=N_PLACEBO)
    return out


def plots(results: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = common.OUT / "plots"
    out.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for season, color in (("2025", "#345"), ("2026", "#b63")):
        prof = {int(k): v for k, v in results["seasons"][season]["offsets"].items() if "coef" in v}
        ks = sorted(prof)
        ax.errorbar(np.array(ks) + (0.08 if season == "2026" else 0), [prof[k]["coef"] for k in ks],
                    yerr=[[prof[k]["coef"] - prof[k]["lo"] for k in ks],
                          [prof[k]["hi"] - prof[k]["coef"] for k in ks]],
                    fmt="o-", color=color, capsize=2, label=season)
    ax.axhline(0, color="#888", lw=1)
    ax.set_xlabel("offset k (nights): treatment = bottleneck sold out on day d - k")
    ax.set_ylabel("tour x sold-out effect on occupancy")
    ax.legend()
    fig.savefig(out / "bottleneck-offsets.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    pt = {t: r for t, r in results["seasons"]["2025"]["per_tour"].items() if "coef" in r}
    fig, ax = plt.subplots(figsize=(6, 0.35 * len(pt) + 1))
    for y, (t, r) in enumerate(sorted(pt.items())):
        ax.plot([r["lo"], r["hi"]], [y, y], color="#345")
        ax.plot(r["coef"], y, "o", color="#345")
    ax.axvline(0, color="#888", lw=1)
    ax.set_yticks(range(len(pt)), sorted(pt), fontsize=7)
    ax.set_xlabel("per-tour effect, 2025 (exploratory, cluster SE)")
    fig.savefig(out / "bottleneck-tours.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    huts, days, tours = load_inputs()
    validation = order_validation(tours)
    results: dict = {"order_validation": validation,
                     "order_agreeing": sum(r["verdict"] in ("same", "reversed") for r in validation),
                     "predefined_test": "seasons.2025.primary; everything else is exploratory"}
    if not bt.orders_validated(validation):
        common.write_json(common.OUT / "bottleneck-results.json", results)
        raise SystemExit(f"order validation failed, re-decide the order source: {validation}")
    table25 = tb.hut_table(huts, days, 2025)
    cand = tb.candidate_table(tours, table25)
    cand.to_csv(common.OUT / "bottleneck-candidates.csv", index=False)
    bottlenecks = tb.bottleneck_ids(cand)
    results.update(candidates=cand.to_dict("records"), n_tours=len(cand), n_with_bottleneck=len(bottlenecks))
    results["seasons"] = {str(s): season_results(s, tours, bottlenecks, huts, days) for s in (2025, 2026)}
    r25, r26 = (results["seasons"][s]["primary"] for s in ("2025", "2026"))
    if "bootstrap" in r25 and "bootstrap" in r26:
        as_ci = lambda r: {"coef": r["did"]["coef"], "lo": r["bootstrap"]["lo"], "hi": r["bootstrap"]["hi"]}
        results["replicated"] = stats.replicated(as_ci(r25), as_ci(r26))
    common.write_json(common.OUT / "bottleneck-results.json", results)
    plots(results)
    print("tours with bottleneck:", len(bottlenecks), "of", len(cand))
    print("2025 primary:", r25)
    print("2026 primary:", r26)
    print("replicated:", results.get("replicated"))


if __name__ == "__main__":
    main()
