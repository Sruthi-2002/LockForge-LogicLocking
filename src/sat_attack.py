"""
sat_attack.py  —  oracle-guided SAT attack on a locked netlist
(Subramanyan et al., "Evaluating the Security of Logic Encryption Algorithms",
HOST 2015).  Used here to *evaluate* how much the reproduced MaxSAT locking
resists key recovery: we count the number of Distinguishing Input Patterns
(DIPs / iterations) the attack needs — more iterations = stronger locking.

The attack treats the original (unlocked) circuit as an oracle and never sees
the real key.
"""
from __future__ import annotations
import time
from pysat.solvers import Glucose3
from netlist import Netlist, _tseitin


class _Alloc:
    def __init__(self):
        self.n = 0

    def new(self):
        self.n += 1
        return self.n


def _instance(nl: Netlist, alloc: _Alloc, key_vars: dict,
              pi_vars: dict | None = None):
    """
    One CNF copy of the locked netlist sharing `key_vars` (dict key->var).
    If pi_vars is None, fresh PI vars are allocated and returned.
    Returns (clauses, pi_vars, out_vars).
    """
    var = {}
    if pi_vars is None:
        pi_vars = {pi: alloc.new() for pi in nl.inputs}
    for pi, vv in pi_vars.items():
        var[pi] = vv
    for k, vv in key_vars.items():
        var[k] = vv
    clauses = []

    def getv(sig):
        if sig not in var:
            var[sig] = alloc.new()
        return var[sig]

    for pi in nl.inputs:
        getv(pi)
    for k in nl.key_inputs:
        getv(k)
    for name in nl.order:
        g = nl.gates[name]
        o = getv(name)
        ins = [getv(fi) for fi in g.fanin]
        clauses.extend(_tseitin(g.gtype, o, ins))
    out_vars = {o: var[o] for o in nl.outputs}
    return clauses, pi_vars, out_vars


def _xor_clauses(o, a, b):
    return [[-o, -a, -b], [-o, a, b], [o, -a, b], [o, a, -b]]


def sat_attack(locked: Netlist, oracle: Netlist, max_iter: int = 300,
               time_budget: float = 60.0) -> dict:
    """Run the attack. Returns stats incl. #iterations (DIPs) and recovered key."""
    alloc = _Alloc()
    keyA = {k: alloc.new() for k in locked.key_inputs}
    keyB = {k: alloc.new() for k in locked.key_inputs}
    constraints = []          # persistent clauses over keyA/keyB (I/O conditions)
    t0 = time.time()
    iterations = 0
    status = "completed"

    while True:
        if iterations >= max_iter:
            status = "max_iter"
            break
        if time.time() - t0 > time_budget:
            status = "timeout"
            break

        # ---- find a Distinguishing Input Pattern ----
        clA, pi, outA = _instance(locked, alloc, keyA)
        clB, _, outB = _instance(locked, alloc, keyB, pi_vars=pi)
        diff = []
        diff_lits = []
        for o in locked.outputs:
            d = alloc.new()
            diff += _xor_clauses(d, outA[o], outB[o])
            diff_lits.append(d)
        miter = constraints + clA + clB + diff + [diff_lits]  # >=1 output differs

        with Glucose3(bootstrap_with=miter) as s:
            sat = s.solve()
            model = s.get_model() if sat else None
        if not sat:
            break  # no more DIPs -> key class pinned

        mset = set(model)
        dip = {pi_name: (1 if pi[pi_name] in mset else 0) for pi_name in locked.inputs}

        # ---- query oracle ----
        y = oracle.eval_outputs(dip)

        # ---- add I/O constraint for both key copies ----
        for kv in (keyA, keyB):
            cl, pifix, ov = _instance(locked, alloc, kv)
            # fix PIs to the DIP
            for pi_name, val in dip.items():
                cl.append([pifix[pi_name] if val else -pifix[pi_name]])
            # fix outputs to oracle response
            for o, val in y.items():
                cl.append([ov[o] if val else -ov[o]])
            constraints += cl
        iterations += 1

    # ---- recover a key consistent with all constraints ----
    recovered = {}
    with Glucose3(bootstrap_with=constraints if constraints else [[1], [-1]]) as s:
        if s.solve():
            m = set(s.get_model())
            recovered = {k: (1 if keyA[k] in m else 0) for k in locked.key_inputs}

    return {"iterations": iterations, "status": status,
            "time_s": round(time.time() - t0, 3),
            "recovered_key": recovered, "key_bits": len(locked.key_inputs)}


def key_correct(recovered: dict, correct: dict, locked: Netlist, oracle: Netlist,
                n_check: int = 500, seed: int = 99) -> bool:
    """A recovered key is 'correct' if the locked circuit with it matches the
    oracle on random inputs (keys can differ yet be functionally equivalent)."""
    import random
    rng = random.Random(seed)
    for _ in range(n_check):
        ia = {pi: rng.randint(0, 1) for pi in oracle.inputs}
        if locked.eval_outputs(ia, recovered) != oracle.eval_outputs(ia):
            return False
    return True
