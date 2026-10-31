# /// script
# requires-python = ">=3.10"
# ///
"""Split a DecompileAll output into functions; list those calling given names, or print one."""
import argparse
import re


def load(path):
    funcs, cur, buf = {}, None, []
    for line in open(path):
        m = re.match(r"// ==== (\S+) @ (\S+)", line)
        if m:
            if cur:
                funcs[cur] = "".join(buf)
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur:
        funcs[cur] = "".join(buf)
    return funcs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--calls", nargs="*", default=[], help="list functions whose body calls any of these")
    ap.add_argument("--show", nargs="*", default=[], help="print these functions")
    ap.add_argument("--sizes", action="store_true", help="list functions by line count")
    a = ap.parse_args()
    f = load(a.file)
    if a.calls:
        for name, body in f.items():
            hits = [c for c in a.calls if re.search(r"\b%s\s*\(" % re.escape(c), body) and not body.lstrip().startswith(f"/* {c}")]
            if hits:
                print(name, body.count("\n"), hits)
    if a.sizes:
        for name, body in sorted(f.items(), key=lambda kv: -kv[1].count("\n"))[:60]:
            print(body.count("\n"), name)
    for s in a.show:
        print(f"// ==== {s}\n{f[s]}")
