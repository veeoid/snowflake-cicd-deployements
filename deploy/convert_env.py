"""Convert one env's SQL files to the next env (the chain: DEV -> TST -> PRD).

    python3 deploy/convert_env.py --from dev --to tst
    python3 deploy/convert_env.py --from tst --to prd

Naming convention: MY_PROJECT_<ENV>_<LAYER>_DB, and the folder name is the
database name. Because of that, ONE anchored pattern handles everything —
the CREATE statement, cross-database references, and the header comment path:

    MY_PROJECT_DEV_PREP_DB.BASE_MODEL.CUSTOMER      (qualified name)
    MY_PROJECT_DEV_PREP_DB/BASE_MODEL/tables/...    (header comment)

It never matches a column like IS_DEV_MODE or a comment mentioning DEV,
because the pattern requires the full PROJECT_ENV_LAYER_DB shape.

The <to> folder tree is rebuilt from scratch each run so deletions propagate.
GENERATED output — never hand-edit.
"""

import argparse
import re
import shutil

from manifest import LAYERS, PROJECT, REPO_ROOT, db_name


def db_pattern(env):
    """Matches MY_PROJECT_<ENV>_<ANYLAYER>_DB, capturing the layer."""
    return re.compile(
        rf"\b{PROJECT}_{env.upper()}_([A-Z0-9]+)_DB\b",
        re.IGNORECASE,
    )


def swap_env(text, from_env, to_env):
    return db_pattern(from_env).sub(
        lambda m: f"{PROJECT}_{to_env.upper()}_{m.group(1).upper()}_DB", text
    )


def convert(from_env, to_env):
    written = []
    for layer in LAYERS:
        src_root = REPO_ROOT / db_name(layer, from_env)
        dst_root = REPO_ROOT / db_name(layer, to_env)
        if not src_root.exists():
            continue
        if dst_root.exists():
            shutil.rmtree(dst_root)
        for src in sorted(src_root.rglob("*.sql")):
            rel = src.relative_to(src_root)
            dst = dst_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            out = swap_env(src.read_text(), from_env, to_env)
            if db_pattern(from_env).search(out):
                raise SystemExit(f"{rel}: source env DB name survived conversion")
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
