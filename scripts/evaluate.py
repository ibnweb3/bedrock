"""Evaluate baselines vs graph signals as pre-registered in docs/BACKTEST_DESIGN.md.

    python scripts/evaluate.py --t0 20201231 [--boot 300]

Reads data/staging/features_<T0>.jsonl (produced by compute_features.py: every signal is a Cypher
query in FalkorDB) and does only metric arithmetic here: ranking, average precision, recall@k,
leave-one-venue-out and a venue-clustered bootstrap. No model is fitted.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ["b_venue_count", "b_venue_rate", "b_cites_asof", "b_author_prior"]
GRAPH = ["g_contam1", "g_contam2", "g_coauth1", "g_coupled_n", "g_coupled_w", "g_comm_rate", "g_comm_ret"]
G_COMP_PARTS = ["g_contam1", "g_contam2", "g_coauth1", "g_coupled_w", "g_comm_rate"]
COMBINED_PARTS = ["b_venue_count"] + G_COMP_PARTS


def pct_rank(values: list[float]) -> list[float]:
    """Percentile rank in (0,1], ties share the average rank."""
    n = len(values)
    idx = sorted(range(n), key=values.__getitem__)
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[idx[j + 1]] == values[idx[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[idx[k]] = avg / n
        i = j + 1
    return out


def weighted_metrics(ov, oy, W, total_n, total_pos):
    """AP, recall@1%, recall@5% for one ranking (ov = venue idx per ranked item, oy = labels)."""
    k1, k5 = max(1, math.ceil(0.01 * total_n)), max(1, math.ceil(0.05 * total_n))
    cum_n = cum_p = r1 = r5 = 0
    ap = 0.0
    for v, y in zip(ov, oy):
        w = W[v]
        if not w:
            continue
        if y:
            for _ in range(w):
                cum_n += 1
                cum_p += 1
                ap += cum_p / cum_n
                if cum_n <= k1:
                    r1 += 1
                if cum_n <= k5:
                    r5 += 1
        else:
            cum_n += w
    return ap / total_pos, r1 / total_pos, r5 / total_pos


class Subset:
    def __init__(self, rows: list[dict], name: str):
        self.name, self.rows = name, rows
        self.y = [r["y"] for r in rows]
        vs = sorted({r["venue"] for r in rows})
        self.vidx = {v: i for i, v in enumerate(vs)}
        self.venue_ids = vs
        self.v = [self.vidx[r["venue"]] for r in rows]
        self.nv = Counter(self.v)
        self.pv = Counter(v for v, y in zip(self.v, self.y) if y)
        self.n, self.pos = len(rows), sum(self.y)
        s = {}
        for k in BASELINES + GRAPH:
            s[k] = [float(r[k]) for r in rows]
        s["G_COMP"] = self._mean_rank(s, G_COMP_PARTS)
        s["COMBINED"] = self._mean_rank(s, COMBINED_PARTS)
        self.scores = s

    @staticmethod
    def _mean_rank(s, parts):
        ranks = [pct_rank(s[p]) for p in parts]
        return [sum(col) / len(parts) for col in zip(*ranks)]

    def order(self, scores, seed):
        rnd = random.Random(seed)
        tb = [rnd.random() for _ in range(self.n)]
        idx = sorted(range(self.n), key=lambda i: (-scores[i], tb[i]))
        return [self.v[i] for i in idx], [self.y[i] for i in idx]

    def point(self, scores, seeds=5):
        W = [1] * len(self.venue_ids)
        res = [weighted_metrics(*self.order(scores, sd), W, self.n, self.pos) for sd in range(seeds)]
        return tuple(sum(c) / seeds for c in zip(*res))


def load(t0: int) -> list[dict]:
    p = ROOT / "data" / "staging" / f"features_{t0}.jsonl"
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def fmt(m):
    return f"AP {m[0]:.4f} | rec@1% {m[1]:.3f} (lift {m[1]/0.01:5.1f}x) | rec@5% {m[2]:.3f}"


def run_subset(sub: Subset, boot: int, do_boot: bool) -> dict:
    out = {"name": sub.name, "n": sub.n, "positives": sub.pos, "base_rate": sub.pos / sub.n,
           "venues": len(sub.venue_ids), "venues_with_positives": len(sub.pv)}
    top = sub.pv.most_common(5)
    out["top_positive_venues"] = [(sub.venue_ids[v], c) for v, c in top]
    print(f"\n=== subset {sub.name}: {sub.n:,} candidates, {sub.pos} positives (base rate {sub.pos/sub.n:.3%}), "
          f"{len(sub.venue_ids)} venues, positives in {len(sub.pv)} venues; top venue holds "
          f"{(top[0][1] / sub.pos if top else 0):.0%}")
    if sub.pos == 0:
        print("   no positives - nothing to rank")
        return out

    scores = dict(sub.scores)
    scores["random"] = [0.0] * sub.n
    scores["oracle"] = [float(y) for y in sub.y]
    pts = {k: sub.point(sc) for k, sc in scores.items()}
    base_best = max(BASELINES, key=lambda k: pts[k][0])
    scores["BASE_BEST"], pts["BASE_BEST"] = scores[base_best], pts[base_best]
    out["base_best"] = base_best
    out["point"] = {k: list(v) for k, v in pts.items()}

    print(f"   best single baseline on this subset: {base_best}")
    for group, names in (("controls", ["random", "oracle"]), ("baselines", BASELINES + ["BASE_BEST"]),
                         ("graph signals", GRAPH), ("composites", ["G_COMP", "COMBINED"])):
        print(f"   -- {group}")
        for k in names:
            print(f"      {k:<16}{fmt(pts[k])}")

    # leave-one-venue-out for the venues with the most positives
    print("   -- AP after dropping one venue (the venue's positives and negatives both removed)")
    lov = {}
    for v, c in top:
        W = [1] * len(sub.venue_ids)
        W[v] = 0
        tn = sub.n - sub.nv[v]
        tp = sub.pos - c
        if tp <= 0:
            continue
        row = {}
        for k in ("BASE_BEST", "b_venue_count", "G_COMP", "COMBINED"):
            ov, oy = sub.order(scores[k], 0)
            row[k] = weighted_metrics(ov, oy, W, tn, tp)[0]
        lov[sub.venue_ids[v]] = row
        print(f"      drop {sub.venue_ids[v]} ({c} pos): " + " | ".join(f"{k} {a:.4f}" for k, a in row.items()))
    out["leave_one_venue_out_AP"] = lov

    if do_boot:
        rnd = random.Random(2026)
        keys = ["BASE_BEST", "b_venue_count", "g_contam1", "g_coauth1", "g_coupled_w", "g_comm_rate", "G_COMP", "COMBINED", "random"]
        pre = {k: sub.order(scores[k], 0) for k in keys}
        nvenue = len(sub.venue_ids)
        samples = defaultdict(list)
        diffs = defaultdict(list)
        for _ in range(boot):
            W = [0] * nvenue
            for _ in range(nvenue):
                W[rnd.randrange(nvenue)] += 1
            tn = sum(W[i] * sub.nv[i] for i in range(nvenue))
            tp = sum(W[i] * sub.pv.get(i, 0) for i in range(nvenue))
            if tp == 0:
                continue
            res = {k: weighted_metrics(*pre[k], W, tn, tp) for k in keys}
            for k, m in res.items():
                samples[k].append(m[0])
            diffs["COMBINED - BASE_BEST"].append(res["COMBINED"][0] - res["BASE_BEST"][0])
            diffs["G_COMP - BASE_BEST"].append(res["G_COMP"][0] - res["BASE_BEST"][0])
            diffs["COMBINED - b_venue_count"].append(res["COMBINED"][0] - res["b_venue_count"][0])

        def ci(xs):
            xs = sorted(xs)
            return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]

        print(f"   -- venue-clustered bootstrap, B={len(samples['random'])} resamples of {nvenue} venues: AP 95% interval")
        out["bootstrap_AP"] = {}
        for k in keys:
            lo, hi = ci(samples[k])
            out["bootstrap_AP"][k] = [lo, hi]
            print(f"      {k:<16}[{lo:.4f}, {hi:.4f}]   point {pts[k][0]:.4f}")
        print("   -- paired difference in AP (same resamples), 95% interval")
        out["bootstrap_diff"] = {}
        for k, xs in diffs.items():
            lo, hi = ci(xs)
            verdict = "excludes 0" if (lo > 0 or hi < 0) else "includes 0"
            out["bootstrap_diff"][k] = [lo, hi]
            print(f"      {k:<26}[{lo:+.4f}, {hi:+.4f}]  ({verdict})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", type=int, required=True)
    ap.add_argument("--boot", type=int, default=300)
    args = ap.parse_args()
    rows = load(args.t0)
    results = {"t0": args.t0}
    H = [r for r in rows if r["stratum"] == "H"]
    subs = [("H", H, True), ("pooled", rows, False)]
    pos_by_venue = Counter(r["venue"] for r in H if r["y"])
    if pos_by_venue:
        top_venue = pos_by_venue.most_common(1)[0][0]
        subs.append((f"H_excluding_top_venue({top_venue})", [r for r in H if r["venue"] != top_venue], True))
    for name, rs, do_boot in subs:
        results[name] = run_subset(Subset(rs, name), args.boot, do_boot)
    p = ROOT / "data" / "staging" / f"results_{args.t0}.json"
    p.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\nsaved", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
