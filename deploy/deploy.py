import argparse
import pathlib
import sys

import yaml

import executor
import manifest
import renderer

REPO_ROOT = pathlib.Path(__file__).parent.parent


def load_config(env):
    cfg = yaml.safe_load((REPO_ROOT / "config" / "base.yml").read_text()) or {}
    cfg.update(yaml.safe_load((REPO_ROOT / "config" / f"{env}.yml").read_text()) or {})
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Deploy Snowflake objects")
    parser.add_argument("--env", required=True, choices=["dev", "tst", "prd"])
    parser.add_argument(
        "--target",
        help="Optional path substring to scope the deploy "
        "(e.g. MY_PROJECT_PREP). Use sparingly.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deploy even if hash matches last deployed version",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and render without connecting to Snowflake",
    )
    args = parser.parse_args()

    cfg = load_config(args.env)
    files = manifest.build_manifest(cfg, target=args.target)
    if not files:
        sys.exit("No SQL files found. Check folder names or --target.")

    # Phase 1: validate and render EVERYTHING before touching Snowflake.
    rendered = {}
    for path in files:
        raw = path.read_text()
        manifest.validate_no_literal_env(path, raw)
        sql = renderer.render(path, cfg)
        manifest.validate_file(path, sql, cfg["env"])
        rendered[path] = sql

    print(f"Validated {len(files)} objects. Deploying to {cfg['env']}\n")
    if args.validate_only:
        print(f"Validated {len(files)} objects for {cfg['env']}. No deploy.")
        return

    # Phase 2: execute in order, skip unchanged, record everything.
    conn = executor.connect(cfg)
    sha = executor.git_sha()
    deployed = skipped = 0
    try:
        last_hashes = executor.get_last_hashes(conn, cfg)

        for path, sql in rendered.items():
            rel = str(path.relative_to(REPO_ROOT))
            obj_name = manifest.extract_object_name(sql)
            obj_type = manifest.object_type(path)
            h = executor.file_hash(sql)

            if not args.force and last_hashes.get(obj_name) == h:
                executor.record_history(
                    conn, cfg, obj_name, obj_type, rel, h, sha, "SKIPPED"
                )
                print(f"  skipping  {rel} (unchanged)")
                skipped += 1
                continue

            print(f"  deploying {rel} ... ", end="", flush=True)
            try:
                executor.execute(conn, sql)
            except Exception:
                executor.record_history(
                    conn, cfg, obj_name, obj_type, rel, h, sha, "FAILED"
                )
                print("FAILED")
                raise  # stop on first failure; rerun after fixing
            executor.record_history(
                conn, cfg, obj_name, obj_type, rel, h, sha, "DEPLOYED"
            )
            print("ok")
            deployed += 1
    finally:
        conn.close()

    print(f"\nDone. {deployed} deployed, {skipped} skipped.")


if __name__ == "__main__":
    main()
