# AI-Agent Interaction Log

This reproduction was produced with an AI coding agent (LockForge workflow). Below is an
organized record of the prompts given, the errors encountered, and the refinements made —
as required by the assignment. It is a faithful account of how the implementation was
actually built, including the dead-ends.

**Model / interaction:** conversational AI coding agent driving a Python implementation,
iterating against a Linux shell (run code → read error → fix → re-run).

---

## Stage 1 — Understand the target and scope

**Prompt (intent).** "The paper 'Concealing Exposed Circuit Features Through a MaxSAT-Based
Logic Locking Method' is IEEE-paywalled and blocked by a WAF. From the title and the
logic-locking literature, define a faithful, CPU-only reproduction of its *core method* and
a key experiment I can run."

**Agent output.** Identified the reproducible core: (1) the "exposed feature" is a wire's
**signal-probability skew**, which SPS/structural attacks exploit; (2) the method uses
**MaxSAT** to place key-gates on wires that conceal this feature (skew ≈ 0) while maximising
output corruption; (3) evaluate vs a random baseline and an oracle-guided **SAT attack**.
Decided deliverables: `netlist`, `locking`, `sat_attack`, `metrics`, benchmarks, experiment
runner, docs.

## Stage 2 — Infrastructure

**Prompt.** "Implement a gate-level netlist: .bench parser, simulator, Monte-Carlo signal
probability, and Tseitin CNF encoding for the SAT attack."

**Agent output.** `src/netlist.py` with `Netlist.from_bench`, `simulate`,
`signal_probabilities`, and `to_cnf`/`_tseitin`. Added the real ISCAS-85 `c17.bench` and a
seeded synthetic-benchmark generator (`experiments/gen_benchmarks.py`).

## Stage 3 — Core method (MaxSAT locking)

**Prompt.** "Implement the MaxSAT key-gate placement: score candidate wires by concealment
(low skew) + corruptibility (output-cone size), and use weighted-partial MaxSAT to select K."

**Agent output.** `src/locking.py` — `candidate_scores`, `maxsat_select` (RC2), `_insert`
(XOR/XNOR key-gates with recorded correct key), plus a `lock_random` baseline.

### ❗ Error 1 — RC2 MaxSAT hangs

**Symptom.** `lock_maxsat` ran on the tiny c17 (6 candidate wires) but **hung (>120 s)** on
`synth_s` (25 wires). Isolating the sub-steps showed `candidate_scores` was fast (0.03 s)
but `maxsat_select`'s **RC2 solve never returned**.

**Diagnosis.** Two compounding causes:
1. **Large, finely-varied soft weights.** The initial code used `weight = score*1000`
   (values ~1000–3000). RC2 is core-guided and its weight-stratification exploded. A control
   test with small weights (`10+i`) on 25 vars solved in 1.2 s; the real weights hung.
2. **Dropping many soft clauses.** "Select *at most K of n*, maximise weight" forces RC2 to
   violate `n−K` soft clauses. Tests showed cost scales with the number dropped: `pool=50,
   K=44` (drop 6) solved in 0.05 s, but `pool=36, K=12` (drop 24) hung.

**Refinements applied.**
- Replaced raw-score weights with **rank-based integer weights (1..n)** — same optimum for
  the additive objective, but small/well-separated so RC2 stays fast.
- **Focused the MaxSAT instance** on the top `K + margin` candidate wires by score, so RC2
  only ever drops ~`margin` clauses (fast), instead of all `n` wires.
- First tried the exactly-K encoding (`atmost` + `atleast`) — removed it; `atmost-K` plus
  positive soft weights already yields exactly K. Switched the cardinality encoding from
  `seqcounter` to `totalizer`.

After the fix, locking runs in **0.01–0.15 s** on all benchmarks (c17 → synth_l).

### Refinement — make the MaxSAT do real work

**Prompt.** "With a purely additive objective, MaxSAT just reproduces a top-K sort. Add a
real constraint so the optimisation is meaningful."

**Agent output.** Added a **structural mutual-exclusion** hard constraint: never place two
key-gates on an ancestor/descendant wire pair (spreads key-gates so they corrupt independent
logic). Now the selection is a genuine constrained optimisation, with a greedy pad-to-K
fallback if the structure over-constrains the pool.

## Stage 4 — Security evaluation (SAT attack)

**Prompt.** "Implement the oracle-guided SAT attack (Subramanyan et al., HOST'15) to measure
how many DIPs are needed to recover the key."

**Agent output.** `src/sat_attack.py` — miter of two key copies sharing primary inputs,
Glucose3 to find DIPs, oracle queries, growing I/O constraints, DIP-iteration count, plus a
`key_correct` functional check (a recovered key may differ yet be equivalent).

## Stage 5 — Experiments and results

**Prompt.** "Run maxsat vs random across all benchmarks; report SPS exposure, corruption,
overhead, SAT iterations; write CSV + a plot."

**Agent output.** `experiments/run_experiments.py` → `results/results.csv`,
`results/plot.png`. Whole suite runs in ~7 s.

**Observations fed back into the writeup.**
- MaxSAT max-skew ≈ 0 everywhere; random up to **0.5** → the core claim reproduced.
- Random sometimes locks a **redundant wire** (synth_s: skew 0.5 ⇒ constant ⇒ 0 % corruption,
  SAT attack finds 0 DIPs) — a concretely useless lock the MaxSAT method avoids.
- Both schemes fall to the SAT attack in a few iterations (expected for plain XOR/XNOR
  locking) — documented honestly as a separate attack surface from the exposed-feature one.

## Stage 6 — Documentation

Wrote `README.md`, this log, and `docs/reproduction_notes.md` (method mapping, assumptions,
and limitations — including that the paywalled text was reconstructed from its methodology).
