"""Capture Snowflake objects from DEV into repo files.

For DEs who develop in Snowsight: build the object in DEV, then run
this to turn it into a tokenized repo file, ready for a PR.

    python3 capture.py --objects MY_PROJECT_PREP_DEV_DB.BASE_MODEL.ORDERS

DEV ONLY. Capturing from TST/PRD would legitimise a manual change in a
locked environment and invert the source-of-truth rule.
"""

import argparse
import re
import sys

import yaml

import executor
import manifest
from deploy import load_config, REPO_ROOT

# GET_DDL emits CREATE OR REPLACE TABLE, which drops data on redeploy.
# Rewrite it to the safe verb before the file ever lands in the repo.
REPLACE_TABLE = re.compile(r"CREATE\s+OR\s+REPLACE\s+TABLE", re.IGNORECASE)

TYPE_FOLDER = {"TABLE": "tables", "VIEW": "views"}

IDENT = re.compile(r"^[A-Z0-9_]+$")  # near the other regexes at top of file


def object_type_of(conn, object_name):
    """Ask Snowflake whether this is a TABLE or a VIEW."""
    db, schema, name = object_name.upper().split(".")
    for part in (db, schema, name):
        if not IDENT.match(part):
            raise SystemExit(f"{object_name}: invalid identifier {part!r}")
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT TABLE_TYPE FROM {db}.INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (schema, name),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"{object_name}: not found in {db}")
        return "VIEW" if row[0].upper() == "VIEW" else "TABLE"
    finally:
        cur.close()


def envify(ddl, env):
    """Replace the literal env in object names with the {{ env }} token."""
    return re.sub(rf"_{env}_DB", "_{{ env }}_DB", ddl, flags=re.IGNORECASE)


def fix_table_verb(ddl):
    return REPLACE_TABLE.sub("CREATE OR ALTER TABLE", ddl)


# def object_type_of(conn, object_name):
#     """Ask Snowflake whether this is a TABLE or a VIEW."""
#     db, schema, name = object_name.upper().split(".")
#     cur = conn.cursor()
#     try:
#         cur.execute(
#             "SELECT TABLE_TYPE FROM IDENTIFIER(%s).INFORMATION_SCHEMA.TABLES "
#             "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
#             (db, schema, name),
#         )
#         row = cur.fetchone()
#         if not row:
#             raise SystemExit(f"{object_name}: not found in {db}")
#         # Snowflake reports 'BASE TABLE' or 'VIEW'
#         return "VIEW" if row[0].upper() == "VIEW" else "TABLE"
#     finally:
#         cur.close()


def get_ddl(conn, object_type, object_name):
    cur = conn.cursor()
    try:
        cur.execute("SELECT GET_DDL(%s, %s, TRUE)", (object_type, object_name))
        return cur.fetchone()[0]
    finally:
        cur.close()


def capture(conn, cfg, object_name):
    env = cfg["env"]
    obj_type = object_type_of(conn, object_name)
    ddl = get_ddl(conn, obj_type, object_name)

    ddl = envify(ddl, env)
    if obj_type == "TABLE":
        ddl = fix_table_verb(ddl)

    path = manifest.derive_path_from_name(object_name, env, TYPE_FOLDER[obj_type])
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"-- {path.relative_to(REPO_ROOT)}\n"
    path.write_text(header + ddl.strip() + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description="Capture DEV objects into the repo")
    parser.add_argument(
        "--objects",
        nargs="+",
        required=True,
        help="Fully qualified object names, e.g. MY_PROJECT_PREP_DEV_DB.BASE_MODEL.ORDERS",
    )
    args = parser.parse_args()

    cfg = load_config("dev")  # DEV only, deliberately not a parameter

    conn = executor.connect(cfg)
    written = []
    try:
        for object_name in args.objects:
            if object_name.count(".") != 2:
                sys.exit(f"{object_name}: need DB.SCHEMA.OBJECT")
            path = capture(conn, cfg, object_name)
            written.append(path)
            print(f"  captured {object_name}")
            print(f"        -> {path.relative_to(REPO_ROOT)}")
    finally:
        conn.close()

    print("\nNext steps:")
    print("  1. Review the files above (GET_DDL output is ugly; tidy if needed)")
    print("  2. python3 deploy/deploy.py --env dev --validate-only")
    print("  3. git checkout -b feature/<name>, commit, push, open a PR")


if __name__ == "__main__":
    main()
