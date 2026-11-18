"""
run_experiments.py  —  reproduce the key experiment.

For each benchmark we lock it two ways at the same key size K:
  * maxsat : the reproduced MaxSAT placement (conceals exposed features)
  * random : baseline random key-gate placement
and report, for each:
  * SPS exposure (max / avg signal-probability skew of locked wires)  <- the
    'exposed feature' the paper conceals; LOWER is better concealment
  * output corruption under wrong keys
  * key-gate overhead
  * oracle-guided SAT-attack iterations (secondary security check)

Writes results/results.csv and results/plot.png.

Run:  python3 experiments/run_experiments.py
"""
import os, sys, csv, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from netlist import Netlist
from locking import lock_maxsat, lock_random
from sat_attack import sat_attack, key_correct
from metrics import output_corruption, sps_exposure, overhead

BENCH = os.path.join(HERE, "..", "benchmarks")
RESDIR = os.path.join(HERE, "..", "results")
os.makedirs(RESDIR, exist_ok=True)

# (benchmark, key size K)
JOBS = [("c17", 2), ("synth_s", 4), ("synth_m", 8), ("synth_l", 12)]
SEED = 1


def run_one(name, K):
    nl = Netlist.from_bench(os.path.join(BENCH, name + ".bench"))
    rows = []
    for method in ("maxsat", "random"):
        if method == "maxsat":
            locked, key, info = lock_maxsat(nl, K=K, n_samples=4000, seed=SEED,
                                            alpha=2.0, beta=1.0)
        else:
            locked, key, info = lock_random(nl, K=K, seed=SEED)
        sps = sps_exposure(nl, info["locked_wires"], n_samples=4000, seed=SEED)
        corr = output_corruption(locked, nl, key, n_inputs=300, n_keys=30, seed=5)
        ovh = overhead(locked)
        atk = sat_attack(locked, nl, max_iter=300, time_budget=25.0)
        broken = key_correct(atk["recovered_key"], key, locked, nl) if atk["recovered_key"] else False
        rows.append({
            "benchmark": name, "gates": len(nl.gates), "method": method,
            "key_bits": K,
            "max_skew": round(sps["max_skew"], 4),
            "avg_skew": round(sps["avg_skew"], 4),
            "corruption": round(corr, 4),
            "key_gates": ovh["key_gates"],
            "sat_iters": atk["iterations"],
            "sat_status": atk["status"],
            "sat_time_s": atk["time_s"],
            "key_recovered": broken,
        })
        print(f"  [{name:8s} {method:6s}] max_skew={sps['max_skew']:.3f} "
              f"avg_skew={sps['avg_skew']:.3f} corruption={corr:.3f} "
              f"SATiters={atk['iterations']} ({atk['status']}) broken={broken}")
    return rows


def main():
    t0 = time.time()
    all_rows = []
    for name, K in JOBS:
        print(f"[{name}] K={K} ...")
        all_rows.extend(run_one(name, K))

    csv_path = os.path.join(RESDIR, "results.csv")
    cols = ["benchmark", "gates", "method", "key_bits", "max_skew", "avg_skew",
            "corruption", "key_gates", "sat_iters", "sat_status", "sat_time_s",
            "key_recovered"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)
    print("\nwrote", os.path.relpath(csv_path))

    # ---- plot: max SPS skew, maxsat vs random ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        names = [n for n, _ in JOBS]
        mx = {r["benchmark"]: r["max_skew"] for r in all_rows if r["method"] == "maxsat"}
        rx = {r["benchmark"]: r["max_skew"] for r in all_rows if r["method"] == "random"}
        import numpy as np
        x = np.arange(len(names)); wq = 0.38
        fig, ax = plt.subplots(figsize=(7.5, 4))
        ax.bar(x - wq/2, [mx[n] for n in names], wq, label="MaxSAT (reproduced)", color="#2b8a6f")
        ax.bar(x + wq/2, [rx[n] for n in names], wq, label="Random baseline", color="#c45b4c")
        ax.set_ylabel("Max signal-probability skew\n(exposed feature — lower = better)")
        ax.set_xlabel("Benchmark")
        ax.set_title("MaxSAT locking conceals the exposed feature better than random")
        ax.set_xticks(x); ax.set_xticklabels(names)
        ax.legend(); ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        p = os.path.join(RESDIR, "plot.png")
        fig.savefig(p, dpi=130)
        print("wrote", os.path.relpath(p))
    except Exception as e:
        print("plot skipped:", e)

    print(f"\ntotal time {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
