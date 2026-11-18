"""Generate reproducible synthetic combinational benchmarks (various sizes)."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def gen(name, n_in, n_gates, n_out, seed):
    rng = random.Random(seed)
    g2 = ["AND", "OR", "NAND", "NOR", "XOR", "XNOR"]
    lines, sigs = [], [f"n{i}" for i in range(n_in)]
    inputs = list(sigs)
    gi = 0
    while gi < n_gates:
        t = rng.choice(g2 + ["NOT"])
        out = f"g{gi}"
        if t == "NOT":
            a = rng.choice(sigs); fin = [a]
        else:
            a, b = rng.choice(sigs), rng.choice(sigs)
            fin = [a, b]
        lines.append(f"{out} = {t}({', '.join(fin)})")
        sigs.append(out); gi += 1
    outs = rng.sample([s for s in sigs if s.startswith("g")], min(n_out, gi))
    path = os.path.join(os.path.dirname(__file__), "..", "benchmarks", name + ".bench")
    with open(path, "w") as f:
        f.write(f"# synthetic benchmark {name}: {n_in} inputs, {n_gates} gates, {len(outs)} outputs\n")
        for s in inputs: f.write(f"INPUT({s})\n")
        for o in outs: f.write(f"OUTPUT({o})\n")
        for l in lines: f.write(l + "\n")
    print("wrote", name, f"({n_in} in, {n_gates} gates, {len(outs)} out)")

if __name__ == "__main__":
    gen("synth_s", 8, 25, 4, 11)
    gen("synth_m", 12, 60, 6, 22)
    gen("synth_l", 16, 120, 8, 33)
