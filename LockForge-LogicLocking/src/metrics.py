"""
metrics.py  —  logic-locking quality metrics.

  * output_corruption: avg fraction of flipped outputs under a WRONG key
    (a good locking corrupts ~50% of outputs for wrong keys).
  * sps_exposure: max signal-probability skew over the locked wires
    (the 'exposed feature' the paper conceals; lower = better concealment).
  * overhead: #key-gates (area added).
"""
from __future__ import annotations
import random
from netlist import Netlist


def output_corruption(locked: Netlist, oracle: Netlist, correct_key: dict,
                      n_inputs: int = 400, n_keys: int = 40, seed: int = 5) -> float:
    rng = random.Random(seed)
    keys = list(locked.key_inputs)
    npo = max(len(oracle.outputs), 1)
    total, count = 0.0, 0
    for _ in range(n_keys):
        wrong = {k: rng.randint(0, 1) for k in keys}
        if wrong == correct_key:                      # ensure it is wrong
            flip = rng.choice(keys)
            wrong[flip] ^= 1
        for _ in range(n_inputs):
            ia = {pi: rng.randint(0, 1) for pi in oracle.inputs}
            ref = oracle.eval_outputs(ia)
            got = locked.eval_outputs(ia, wrong)
            diff = sum(1 for o in oracle.outputs if ref[o] != got[o])
            total += diff / npo
            count += 1
    return total / max(count, 1)


def sps_exposure(nl_before: Netlist, locked_wires: list,
                 n_samples: int = 4000, seed: int = 1) -> dict:
    """Signal-probability skew of the locked wires in the ORIGINAL circuit."""
    probs = nl_before.signal_probabilities(n_samples=n_samples, seed=seed)
    skews = [abs(probs.get(w, 0.5) - 0.5) for w in locked_wires]
    return {"max_skew": max(skews) if skews else 0.0,
            "avg_skew": sum(skews) / len(skews) if skews else 0.0}


def overhead(locked: Netlist) -> dict:
    return {"key_gates": len(locked.key_inputs),
            "total_gates": len(locked.gates)}
