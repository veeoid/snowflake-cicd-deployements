import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).parent.parent
OBJECT_DIRS = ["MY_PROJECT_PREP", "MY_PROJECT_ANALYTICS"]

LITERAL_ENV = re.compile(r"_(DEV|TST|PRD)_", re.IGNORECASE)
CREATE_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Z0-9_.]+)",
    re.IGNORECASE,
)


def build_manifest(cfg, target=None):
    """Walk object dirs and return files in deploy order.

    Order: object type per deploy_order (tables before views),
    then top dir, then schema, then filename.
    Optional target substring filters paths (scoped deploys).
    """
    files = []
    for obj_type in cfg["deploy_order"]:
        for top in OBJECT_DIRS:
            base = REPO_ROOT / top
            if base.exists():
                files.extend(sorted(base.rglob(f"{obj_type}/*.sql")))
    if target:
        files = [f for f in files if target in str(f.relative_to(REPO_ROOT))]
    return files


def validate_no_literal_env(path, raw_text):
    """Repo files must be tokenized. Literal env names are forbidden."""
    if LITERAL_ENV.search(raw_text):
        raise ValueError(
            f"{path.relative_to(REPO_ROOT)}: contains a literal environment "
            f"name (_DEV_/_TST_/_PRD_). Use {{{{ env }}}} instead."
        )


def extract_object_name(rendered_sql):
    """Pull the fully qualified object name out of the CREATE statement."""
    m = CREATE_RE.search(rendered_sql)
    if not m:
        raise ValueError("No CREATE TABLE/VIEW statement found")
    return m.group(1).upper()


def object_type(path):
    """The object-type folder the file sits in: 'tables' or 'views'."""
    return path.parent.name


def derive_expected_name(path, env):
    """Path is load-bearing: derive the fully qualified name it implies.

    MY_PROJECT_PREP/BASE_MODEL/tables/customer.sql + DEV
    -> MY_PROJECT_PREP_DEV_DB.BASE_MODEL.CUSTOMER
    """
    parts = path.relative_to(REPO_ROOT).parts
    if len(parts) != 4:
        raise ValueError(
            f"{path.relative_to(REPO_ROOT)}: expected "
            f"TOPDIR/SCHEMA/TYPE/name.sql structure"
        )
    top, schema, _obj_type, filename = parts
    object_name = pathlib.Path(filename).stem.upper()
    return f"{top}_{env}_DB.{schema}.{object_name}"


def validate_file(path, rendered_sql, env):
    """Rendered DDL must create exactly what the path implies."""
    expected = derive_expected_name(path, env)
    actual = extract_object_name(rendered_sql)
    if actual != expected:
        raise ValueError(
            f"{path.relative_to(REPO_ROOT)}: DDL creates {actual} "
            f"but path implies {expected}"
        )
