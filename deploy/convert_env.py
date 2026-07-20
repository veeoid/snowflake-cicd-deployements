"""Convert one env's SQL files to the next env, in place (the chain: DEV->TST->PRD).

    python3 deploy/convert_env.py --from dev --to tst
    python3 deploy/convert_env.py --from tst --to prd

Reads the <from> env folder, writes the <to> env folder, swapping the DB-name
env token _<FROM>_DB -> _<TO>_DB. Targeted so column names / comments that merely
contain the letters DEV/TST/PRD are left alone. The <to> folder is regenerated
from scratch each run so deletions propagate. GENERATED output - never hand-edit.
"""

import argparse
import pathlib
import re
import shutil

REPO_ROOT = pathlib.Path(__file__).parent.parent
OBJECT_BASES = ["MY_PROJECT_PREP", "MY_PROJECT_ANALYTICS"]


def env_top(base, env):
    return f"{base}_{env.upper()}"


def swap_env(text, from_env, to_env):
    pattern = re.compile(rf"_{from_env.upper()}_DB", re.IGNORECASE)
    return pattern.sub(f"_{to_env.upper()}_DB", text)


def convert(from_env, to_env):
    written = []
    for base in OBJECT_BASES:
        src_root = REPO_ROOT / env_top(base, from_env)
        dst_root = REPO_ROOT / env_top(base, to_env)
        if not src_root.exists():
            continue
        if dst_root.exists():
            shutil.rmtree(dst_root)
        for src in sorted(src_root.rglob("*.sql")):
            rel = src.relative_to(src_root)
            dst = dst_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            out = swap_env(src.read_text(), from_env, to_env)
            # also fix the leading "-- <path>" header comment folder name
            out = re.sub(
                rf"_{from_env.upper()}/",
                f"_{to_env.upper()}/",
                out,
            )
            if re.search(rf"_{from_env.upper()}_DB", out, re.IGNORECASE):
                raise SystemExit(f"{rel}: source env token survived conversion")
            dst.write_text(out)
            written.append(dst.relative_to(REPO_ROOT))
    return written


def main():
    p = argparse.ArgumentParser(description="Convert one env's files to the next")
    p.add_argument("--from", dest="from_env", required=True, choices=["dev", "tst"])
    p.add_argument("--to", dest="to_env", required=True, choices=["tst", "prd"])
    args = p.parse_args()
    if (args.from_env, args.to_env) not in {("dev", "tst"), ("tst", "prd")}:
        raise SystemExit("Only dev->tst and tst->prd are allowed.")
    written = convert(args.from_env, args.to_env)
    print(f"Converted {len(written)} files: {args.from_env} -> {args.to_env}")
    for w in written:
        print(f"  {w}")


if __name__ == "__main__":
    main()
