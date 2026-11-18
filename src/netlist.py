"""
netlist.py  —  gate-level combinational netlist: .bench parser, simulator,
signal-probability estimation, and Tseitin CNF encoding (for the SAT attack).

Part of the LockForge reproduction of:
  "Concealing Exposed Circuit Features Through a MaxSAT-Based Logic Locking Method"

A netlist is a DAG of gates. Supported gate types (ISCAS .bench):
  AND OR NAND NOR NOT/BUF(F) XOR XNOR  and the locking gate types we add.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

GATE_TYPES = {"AND", "OR", "NAND", "NOR", "NOT", "BUF", "BUFF", "XOR", "XNOR"}


@dataclass
class Gate:
    name: str                 # output signal name
    gtype: str                # gate type
    fanin: list               # list of input signal names
    is_key: bool = False      # True if this is an inserted key-gate
    key_index: int | None = None   # which key bit controls it


@dataclass
class Netlist:
    inputs: list = field(default_factory=list)      # primary input names
    outputs: list = field(default_factory=list)     # primary output names
    gates: dict = field(default_factory=dict)       # name -> Gate
    key_inputs: list = field(default_factory=list)  # key input names (locking)
    order: list = field(default_factory=list)       # topologically sorted gate names

    # ---------- parsing ----------
    @classmethod
    def from_bench(cls, path: str) -> "Netlist":
        nl = cls()
        with open(path) as f:
            for raw in f:
                line = raw.split("#")[0].strip()
                if not line:
                    continue
                up = line.upper()
                if up.startswith("INPUT("):
                    nl.inputs.append(line[line.find("(") + 1:line.rfind(")")].strip())
                elif up.startswith("OUTPUT("):
                    nl.outputs.append(line[line.find("(") + 1:line.rfind(")")].strip())
                elif "=" in line:
                    lhs, rhs = line.split("=", 1)
                    out = lhs.strip()
                    gtype = rhs[:rhs.find("(")].strip().upper()
                    args = rhs[rhs.find("(") + 1:rhs.rfind(")")]
                    fanin = [a.strip() for a in args.split(",") if a.strip()]
                    nl.gates[out] = Gate(out, gtype, fanin)
        nl._topo_sort()
        return nl

    def _topo_sort(self):
        self.order = []
        ready = set(self.inputs) | set(self.key_inputs)
        pending = dict(self.gates)
        # iterative Kahn-style ordering
        progress = True
        while pending and progress:
            progress = False
            for name in list(pending):
                g = pending[name]
                if all(fi in ready for fi in g.fanin):
                    self.order.append(name)
                    ready.add(name)
                    del pending[name]
                    progress = True
        if pending:
            # remaining (possibly cyclic or dangling) — append as-is
            self.order.extend(pending.keys())

    # ---------- simulation ----------
    @staticmethod
    def _eval(gtype: str, vals: list) -> int:
        if gtype in ("BUF", "BUFF"):
            return vals[0]
        if gtype == "NOT":
            return 1 - vals[0]
        if gtype == "AND":
            return int(all(vals))
        if gtype == "NAND":
            return 1 - int(all(vals))
        if gtype == "OR":
            return int(any(vals))
        if gtype == "NOR":
            return 1 - int(any(vals))
        if gtype == "XOR":
            x = 0
            for v in vals:
                x ^= v
            return x
        if gtype == "XNOR":
            x = 0
            for v in vals:
                x ^= v
            return 1 - x
        raise ValueError(f"unknown gate type {gtype}")

    def simulate(self, input_assign: dict, key_assign: dict | None = None) -> dict:
        """Evaluate every signal. input_assign: PI->0/1, key_assign: key->0/1."""
        val = dict(input_assign)
        if key_assign:
            val.update(key_assign)
        for name in self.order:
            g = self.gates[name]
            val[name] = self._eval(g.gtype, [val[fi] for fi in g.fanin])
        return val

    def eval_outputs(self, input_assign: dict, key_assign: dict | None = None) -> dict:
        v = self.simulate(input_assign, key_assign)
        return {o: v[o] for o in self.outputs}

    # ---------- signal probability (Monte-Carlo) ----------
    def signal_probabilities(self, n_samples: int = 4000, seed: int = 1,
                             key_assign: dict | None = None) -> dict:
        """P(signal = 1) estimated over random primary-input vectors."""
        rng = random.Random(seed)
        counts = {s: 0 for s in list(self.inputs) + list(self.gates)}
        for _ in range(n_samples):
            ia = {pi: rng.randint(0, 1) for pi in self.inputs}
            v = self.simulate(ia, key_assign)
            for s in counts:
                counts[s] += v.get(s, 0)
        return {s: counts[s] / n_samples for s in counts}

    # ---------- Tseitin CNF encoding (for SAT attack) ----------
    def to_cnf(self, var_of: dict | None = None, suffix: str = "") -> tuple:
        """
        Encode this (possibly locked) netlist into CNF.
        Returns (clauses, var_of) where var_of maps 'signal'+suffix -> int var id.
        Key inputs and primary inputs get fresh vars; gates are Tseitin-encoded.
        """
        if var_of is None:
            var_of = {}
        nxt = [max(var_of.values(), default=0) + 1]

        def v(sig):
            k = sig + suffix
            if k not in var_of:
                var_of[k] = nxt[0]
                nxt[0] += 1
            return var_of[k]

        clauses = []
        for s in list(self.inputs) + list(self.key_inputs):
            v(s)  # allocate
        for name in self.order:
            g = self.gates[name]
            o = v(name)
            ins = [v(fi) for fi in g.fanin]
            clauses.extend(_tseitin(g.gtype, o, ins))
        return clauses, var_of


def _tseitin(gtype, o, ins):
    """CNF clauses enforcing o = gtype(ins)."""
    c = []
    if gtype in ("BUF", "BUFF"):
        a = ins[0]
        c += [[-o, a], [o, -a]]
    elif gtype == "NOT":
        a = ins[0]
        c += [[-o, -a], [o, a]]
    elif gtype in ("AND", "NAND"):
        # t = AND(ins); for NAND o = -t
        t = o if gtype == "AND" else None
        if gtype == "AND":
            for a in ins:
                c.append([-o, a])
            c.append([o] + [-a for a in ins])
        else:  # NAND
            for a in ins:
                c.append([o, a])            # if any input 0 -> o=1
            c.append([-o] + [-a for a in ins])
    elif gtype in ("OR", "NOR"):
        if gtype == "OR":
            for a in ins:
                c.append([o, -a])
            c.append([-o] + ins)
        else:  # NOR
            for a in ins:
                c.append([-o, -a])
            c.append([o] + ins)
    elif gtype in ("XOR", "XNOR"):
        # only support 2-input here (key-gates and typical benches)
        assert len(ins) == 2, "XOR/XNOR CNF supports 2 inputs"
        a, b = ins
        if gtype == "XOR":
            c += [[-o, -a, -b], [-o, a, b], [o, -a, b], [o, a, -b]]
        else:  # XNOR
            c += [[o, -a, -b], [o, a, b], [-o, -a, b], [-o, a, -b]]
    else:
        raise ValueError(f"no CNF for {gtype}")
    return c
