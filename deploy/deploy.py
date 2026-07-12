import argparse
import os
import pathlib
import sys

import jinja2
import snowflake.connector
import yaml

REPO_ROOT = pathlib.Path(__file__).parent.parent
OBJECT_DIRS = ["MY_PROJECT_PREP", "MY_PROJECT_ANALYTICS"]


def load_config(env):
    cfg = yaml.safe_load((REPO_ROOT / "config" / "base.yml").read_text())
    cfg.update(yaml.safe_load((REPO_ROOT / "config" / f"{env}.yml").read_text()))
    return cfg


def build_manifest(cfg):
    files = []
    for obj_type in cfg["deploy_order"]:  # tables, then views
        for top in OBJECT_DIRS:
            base = REPO_ROOT / top
            if base.exists():
                files.extend(sorted(base.rglob(f"{obj_type}/*.sql")))
    return files


def render(path, cfg):
    template = jinja2.Template(path.read_text(), undefined=jinja2.StrictUndefined)
    return template.render(env=cfg["env"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["dev", "tst", "prd"])
    args = parser.parse_args()

    cfg = load_config(args.env)
    manifest = build_manifest(cfg)
    if not manifest:
        sys.exit("No SQL files found. Check folder names.")

    print(f"Deploying {len(manifest)} objects to {cfg['env']}\n")

    conn = snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=cfg["role"],
        warehouse=cfg["warehouse"],
    )
    cur = conn.cursor()
    try:
        for path in manifest:
            rel = path.relative_to(REPO_ROOT)
            sql = render(path, cfg)
            print(f"  deploying {rel} ... ", end="")
            cur.execute(sql)
            print("ok")
    finally:
        cur.close()
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
