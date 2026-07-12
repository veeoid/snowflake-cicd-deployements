import hashlib
import os
import subprocess

import snowflake.connector


def connect(cfg):
    """Password auth from env var for local/trial use.

    Key-pair auth replaces this when CI arrives; only this
    function changes, nothing else in the engine.
    """
    return snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=cfg["role"],
        warehouse=cfg["warehouse"],
    )


def execute(conn, sql):
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()


def file_hash(rendered_sql):
    """Hash the RENDERED sql so config-driven changes also redeploy."""
    return hashlib.sha256(rendered_sql.encode()).hexdigest()


def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def history_table(cfg):
    return cfg["history_table"].replace("{env}", cfg["env"])


def get_last_hashes(conn, cfg):
    """Last successfully deployed hash per object in this env.

    Returns {object_name: file_hash}. Used for skip-unchanged.
    """
    table = history_table(cfg)
    sql = f"""
        SELECT OBJECT_NAME, FILE_HASH
        FROM {table}
        WHERE ENV = %s AND ACTION = 'DEPLOYED'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY OBJECT_NAME ORDER BY EXECUTED_AT DESC
        ) = 1
    """
    cur = conn.cursor()
    try:
        cur.execute(sql, (cfg["env"],))
        return {row[0]: row[1] for row in cur.fetchall()}
    except snowflake.connector.errors.ProgrammingError as e:
        raise SystemExit(
            f"Could not read history table {table}. "
            f"Create it first (see setup/history_table.sql). "
            f"Underlying error: {e}"
        )
    finally:
        cur.close()


def record_history(conn, cfg, obj_name, obj_type, file_path, sql_hash, sha, action):
    table = history_table(cfg)
    cur = conn.cursor()
    try:
        cur.execute(
            f"INSERT INTO {table} "
            "(OBJECT_NAME, OBJECT_TYPE, FILE_PATH, FILE_HASH, GIT_SHA, ENV, ACTION) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (obj_name, obj_type, file_path, sql_hash, sha, cfg["env"], action),
        )
    finally:
        cur.close()
