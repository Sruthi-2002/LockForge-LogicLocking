# Reproduction Notes

## Source paper
**"Concealing Exposed Circuit Features Through a MaxSAT-Based Logic Locking Method"**
(Logic-Locking sheet, paper #8).

The IEEE full text is paywalled and the landing page is served behind a WAF, so the exact
MaxSAT encoding from the paper could not be read directly. This reproduction therefore
implements the paper's **described methodology** — using MaxSAT to place logic-locking
key-gates so as to conceal the circuit's *exposed features* — reconstructed from the title
and the established logic-locking literature (signal-probability-skew / SPS attacks, the
oracle-guided SAT attack, and standard XOR/XNOR key-gate locking).

## Method mapping (paper concept -> our implementation)

| Paper concept | Implementation |
|---|---|
| Exposed circuit feature | Signal-probability skew `|P(wire)-0.5|` (`src/metrics.py`, `src/locking.py`) |
| Conceal the feature | Prefer wires with skew ≈ 0 (balanced probability) |
| MaxSAT formulation | Weighted-partial MaxSAT via RC2 (`maxsat_select`): at-most-K hard cardinality + ancestor/descendant mutual-exclusion hard constraints + rank-weighted soft rewards |
| Locking primitive | XOR/XNOR key-gates, random polarity, recorded correct key (`_insert`) |
| Security evaluation | Oracle-guided SAT attack (`src/sat_attack.py`); SPS-exposure, corruption, overhead metrics |

## Deliberate simplifications / assumptions
- **Signal probability** is estimated by Monte-Carlo simulation (4000 random vectors), not
  by exact BDD/analytic computation. This is enough to rank candidate wires.
- **Candidate pool.** The MaxSAT instance is focused on the top `K + margin` wires by
  desirability, so the core-guided solver stays fast. For the additive part of the objective
  this gives the same optimum as a global solve; the structural mutex is enforced exactly on
  the pool.
- **Benchmarks.** `c17` is the real ISCAS-85 circuit; `synth_{s,m,l}` are seeded synthetic
  circuits used to show the trend across sizes. The method accepts any `.bench` file.
- **Scope.** Per the assignment, we reproduce the *core methodology and a key experiment*
  (exposed-feature concealment vs a baseline, + SAT-attack evaluation), not every table in
  the paper.

## Known limitations
- Plain XOR/XNOR key-gates remain SAT-attackable (shown in the results); concealing the SPS
  exposed feature is orthogonal to SAT resistance, which is consistent with the locking
  literature.
- The exact numeric thresholds and the precise MaxSAT clause structure of the original paper
  may differ from this reconstruction.
