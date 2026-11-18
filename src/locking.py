"""
locking.py  —  the core reproduced method.

Reproduction of the central idea of
  "Concealing Exposed Circuit Features Through a MaxSAT-Based Logic Locking Method"

Idea reproduced:
  * An inserted XOR/XNOR key-gate leaves an *exposed feature*: if the locked
    wire's signal probability is skewed far from 0.5, a probability/structural
    attack (e.g. the SPS attack) can guess the key-bit polarity.  A wire whose
    probability is ~0.5 conceals the key bit.
  * We therefore choose *where* to place the K key-gates by solving a
    (weighted partial) MaxSAT problem:
        - decision var x_i  = "insert a key-gate on candidate wire i"
        - HARD: exactly K key-gates  (cardinality constraint)
        - SOFT: weight w_i on selecting wire i, where w_i rewards
                (a) concealment  = 1 - 2*|P(wire)-0.5|   (balanced => high)
                (b) corruptibility = |output cone| / |POs| (more reach => high)
    RC2 selects the K wires maximising total desirability => key-gates that are
    both well-concealed and high-impact.

A random-placement baseline (`lock_random`) is provided for comparison.
"""
from __future__ import annotations
import random
from pysat.formula import WCNF
from pysat.card import CardEnc, EncType
from pysat.examples.rc2 import RC2
from netlist import Netlist, Gate


# ---------- exposed-feature analysis ----------
def output_cones(nl: Netlist) -> dict:
    """For each wire (gate output), the set of primary outputs it can reach."""
    # build fanout adjacency
    fanout = {s: set() for s in list(nl.inputs) + list(nl.gates)}
    for name, g in nl.gates.items():
        for fi in g.fanin:
            fanout.setdefault(fi, set()).add(name)
    cones = {}
    for wire in nl.gates:
        seen, stack, outs = set(), [wire], set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur in nl.outputs:
                outs.add(cur)
            for nxt in fanout.get(cur, ()):
                stack.append(nxt)
        cones[wire] = outs
    return cones


def candidate_scores(nl: Netlist, n_samples: int = 4000, seed: int = 1,
                     alpha: float = 1.0, beta: float = 1.0) -> dict:
    """Per-candidate-wire desirability = alpha*concealment + beta*corruptibility."""
    probs = nl.signal_probabilities(n_samples=n_samples, seed=seed)
    cones = output_cones(nl)
    npo = max(len(nl.outputs), 1)
    scores, detail = {}, {}
    for wire in nl.gates:
        p = probs.get(wire, 0.5)
        concealment = 1.0 - 2.0 * abs(p - 0.5)          # in [0,1], 1 at p=0.5
        corrupt = len(cones[wire]) / npo                # in [0,1]
        scores[wire] = alpha * concealment + beta * corrupt
        detail[wire] = {"p": p, "exposure": abs(p - 0.5),
                        "concealment": concealment, "corruptibility": corrupt}
    return scores, detail


# ---------- MaxSAT selection ----------
def _ancestors(nl: Netlist, wire: str) -> set:
    """All wires in the transitive fan-in of `wire` (iterative DFS)."""
    anc, stack = set(), list(nl.gates[wire].fanin) if wire in nl.gates else []
    while stack:
        s = stack.pop()
        if s in anc:
            continue
        anc.add(s)
        if s in nl.gates:
            stack.extend(nl.gates[s].fanin)
    return anc


def maxsat_select(nl: Netlist, scores: dict, K: int, margin: int = 12) -> list:
    """
    Choose K key-gate wires by (weighted partial) MaxSAT.

    To keep the MaxSAT instance tractable we focus it on the top (K+margin)
    candidate wires by desirability, then solve:
        - HARD: at most K selected                       (cardinality)
        - HARD: not both wires of an ancestor/descendant pair  (spread the
                key-gates so they corrupt independent logic — this is what
                makes the choice a real optimisation, not a plain top-K sort)
        - SOFT: rank-based reward for selecting high-desirability wires
    RC2 returns the max-weight feasible set.  Rank weights (vs raw scores)
    keep the core-guided solver fast.
    """
    wires = list(scores.keys())
    n = len(wires)
    K = min(K, n)
    pool = sorted(wires, key=lambda w: -scores[w])[:min(n, K + margin)]
    m = len(pool)
    var = {w: i + 1 for i, w in enumerate(pool)}
    order = sorted(pool, key=lambda w: scores[w])
    rank = {w: i + 1 for i, w in enumerate(order)}   # small, distinct weights

    wcnf = WCNF()
    am = CardEnc.atmost(lits=[var[w] for w in pool], bound=K,
                        top_id=m, encoding=EncType.totalizer)
    for cl in am.clauses:
        wcnf.append(cl)
    poolset = set(pool)
    for w in pool:                                   # structural mutex
        for a in _ancestors(nl, w) & poolset:
            wcnf.append([-var[w], -var[a]])
    for w in pool:
        wcnf.append([var[w]], weight=rank[w])

    with RC2(wcnf) as solver:
        model = solver.compute()
    chosen = set(l for l in model if 0 < l <= m)
    selected = [w for w in pool if var[w] in chosen]

    # pad if the structural constraints left us short of K
    if len(selected) < K:
        for w in sorted(wires, key=lambda x: -scores[x]):
            if w not in selected:
                selected.append(w)
                if len(selected) == K:
                    break
    return selected[:K]


# ---------- key-gate insertion ----------
def _insert(nl: Netlist, wires: list, seed: int = 7) -> tuple:
    """Insert XOR/XNOR key-gates on the given wires. Returns (locked, correct_key)."""
    rng = random.Random(seed)
    locked = Netlist(inputs=list(nl.inputs), outputs=list(nl.outputs),
                     gates={k: Gate(g.name, g.gtype, list(g.fanin))
                            for k, g in nl.gates.items()})
    correct_key = {}
    for j, wire in enumerate(wires):
        keyname = f"keyinput{j}"
        locked.key_inputs.append(keyname)
        orig_src = f"{wire}__pre{j}"
        # rename the original driver to orig_src, keep its logic
        g = locked.gates.pop(wire)
        g.name = orig_src
        locked.gates[orig_src] = g
        # choose polarity: XOR (correct key 0) or XNOR (correct key 1)
        if rng.randint(0, 1) == 0:
            gtype, correct = "XOR", 0
        else:
            gtype, correct = "XNOR", 1
        locked.gates[wire] = Gate(wire, gtype, [orig_src, keyname],
                                  is_key=True, key_index=j)
        correct_key[keyname] = correct
    locked._topo_sort()
    return locked, correct_key


# ---------- public API ----------
def lock_maxsat(nl: Netlist, K: int, n_samples: int = 4000, seed: int = 1,
                alpha: float = 1.0, beta: float = 1.0) -> tuple:
    scores, detail = candidate_scores(nl, n_samples, seed, alpha, beta)
    wires = maxsat_select(nl, scores, K)
    locked, key = _insert(nl, wires, seed=seed + 7)
    info = {"method": "maxsat", "locked_wires": wires,
            "avg_exposure": sum(detail[w]["exposure"] for w in wires) / max(len(wires), 1),
            "avg_corruptibility": sum(detail[w]["corruptibility"] for w in wires) / max(len(wires), 1)}
    return locked, key, info


def lock_random(nl: Netlist, K: int, seed: int = 1) -> tuple:
    rng = random.Random(seed)
    wires = list(nl.gates.keys())
    rng.shuffle(wires)
    wires = wires[:min(K, len(wires))]
    _, detail = candidate_scores(nl, 2000, seed)
    locked, key = _insert(nl, wires, seed=seed + 7)
    info = {"method": "random", "locked_wires": wires,
            "avg_exposure": sum(detail[w]["exposure"] for w in wires) / max(len(wires), 1),
            "avg_corruptibility": sum(detail[w]["corruptibility"] for w in wires) / max(len(wires), 1)}
    return locked, key, info
