"""
migrate_sqlite_to_neon.py
=========================

One-time migration of the five legacy SQLite files into the Neon PostgreSQL
database. Each ``.db`` file becomes its own PostgreSQL schema (see ``db.py``).

    python migrate_sqlite_to_neon.py            # migrate
    python migrate_sqlite_to_neon.py --dry-run  # show what would happen
    python migrate_sqlite_to_neon.py --force    # wipe target schemas first

The script is idempotent: existing tables are created with ``IF NOT EXISTS``
semantics and rows are upserted, so re-running it will not duplicate data.
"""

import os
import re
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv()

import db  # noqa: E402  (imported after load_dotenv on purpose)

# SQLite file -> (schema, tables we expect to find)
SOURCES = {
    'patients.db': ['patients', 'patient_diagnoses'],
    'enhanced_auth.db': ['enhanced_users', 'user_sessions', 'diagnoses',
                         'appointments', 'prescriptions', 'reports', 'treatments'],
    'diagnosis.db': ['users', 'diagnosis_records', 'search_operations'],
    'fhir_data.db': ['fhir_bundles', 'fhir_resources'],
    'fhir_bundles.db': ['fhir_bundles'],
}

DRY_RUN = '--dry-run' in sys.argv
FORCE = '--force' in sys.argv


def sqlite_tables(path):
    """Return {table_name: [column_names]} for a SQLite file."""
    if not os.path.exists(path):
        return {}
    conn = sqlite3.connect(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = {}
        for name in names:
            cols = [(r[1], (r[2] or '').upper()) for r in conn.execute(f'PRAGMA table_info("{name}")')]
            out[name] = cols
        return out
    finally:
        conn.close()


def sqlite_ddl(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def coerce(value):
    """sqlite returns bytes for BLOB columns; Postgres text columns want str."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode('utf-8', 'replace')
    return value


def postgres_column_types(conn, schema, table):
    """Return {column: postgres type} for an existing table."""
    cur = conn.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def coerce_for(value, pg_type):
    """Adapt a SQLite value to what the PostgreSQL column expects."""
    if value is None or pg_type is None:
        return value

    if pg_type == 'boolean':
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode('utf-8', 'replace')
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 't', 'yes', 'y')
        return bool(value)

    if pg_type in ('smallint', 'integer', 'bigint'):
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode('utf-8', 'replace')
        if isinstance(value, str):
            value = value.strip()
            return int(value) if value else None
        return int(value) if value is not None else None

    if pg_type in ('numeric', 'real', 'double precision'):
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode('utf-8', 'replace')
        if isinstance(value, str):
            value = value.strip()
            return float(value) if value else None
        return float(value) if value is not None else None

    return coerce(value)


def realign_identity(conn, schema, table):
    """Advance an identity sequence past the ids we just copied in.

    Copying explicit ``id`` values does not move the sequence, so the next
    INSERT would collide with a row that already exists.
    """
    cur = conn.execute(
        "SELECT pg_get_serial_sequence(%s, 'id')",
        (f'"{schema}"."{table}"',),
    )
    seq = cur.fetchone()[0]
    if not seq:
        return
    cur = conn.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{schema}"."{table}"')
    next_id = cur.fetchone()[0] + 1
    conn.execute('SELECT setval(%s, %s, false)', (seq, next_id))
    conn.commit()


def migrate_table(sqlite_path, table, columns, schema):
    """Create the table on Postgres and copy every row across."""
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
    src.close()

    # Build the CREATE TABLE from the SQLite schema, translated by db.translate_sql.
    src = sqlite3.connect(sqlite_path)
    ddl = sqlite_ddl(src, table)
    src.close()

    # SQLite strips "IF NOT EXISTS" when it persists the DDL in sqlite_master,
    # so put it back to keep this script re-runnable.
    if ddl:
        ddl = re.sub(r'^\s*CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)',
                     'CREATE TABLE IF NOT EXISTS ', ddl, count=1, flags=re.IGNORECASE)
    translated = db.translate_sql(ddl)

    # NOTE: the table is created even when it holds zero rows. Skipping the DDL
    # for empty tables left whole tables missing from Neon (diagnosis_records,
    # fhir_bundles, fhir_resources, ...), because the app only creates them when
    # the corresponding code path runs - so a query for an untouched table failed
    # with "relation does not exist".
    if not ddl:
        print(f'    {table:<22} no DDL in sqlite_master, skipped')
        return 0

    conn = db.connect(sqlite_path)
    try:
        for stmt in db._split_statements(translated):
            conn.execute(stmt)
        conn.commit()

        if not rows:
            print(f'    {table:<22} table created, 0 row(s) to copy')
            return 0

        if DRY_RUN:
            print(f'    {table:<22} would copy {len(rows)} row(s)')
            return 0

        col_types = postgres_column_types(conn, schema, table)
        col_names = [c for c, _t in columns]
        placeholders = ', '.join(['%s'] * len(col_names))
        collist = ', '.join(f'"{c}"' for c in col_names)
        sql = f'INSERT INTO "{table}" ({collist}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        # ``ON CONFLICT DO NOTHING`` drops conflicting rows *silently*, which
        # previously made this script report a full copy even when rows were
        # discarded. That is how two real user accounts went missing: leftover
        # test rows in Neon already owned their ``id`` and ``patient_id``.
        # db.Connection.execute() appends ``RETURNING id`` to INSERTs, so a
        # skipped row comes back with lastrowid None and can be reported.
        inserted, skipped = 0, []
        for row in rows:
            values = [
                coerce_for(row[c], col_types.get(c))
                for c in col_names
            ]
            if conn.execute(sql, values).lastrowid is None:
                skipped.append(row)
            else:
                inserted += 1
        conn.commit()

        realign_identity(conn, schema, table)

        print(f'    {table:<22} copied {inserted} row(s)')
        if skipped:
            print(f'    {"":<22} !! {len(skipped)} row(s) SKIPPED - '
                  f'already present or unique-constraint conflict:')
            for row in skipped:
                label = row['email'] if 'email' in row.keys() else (
                    row['patient_id'] if 'patient_id' in row.keys() else None)
                ident = f' (id={row["id"]})' if 'id' in row.keys() else ''
                print(f'    {"":<26} - {label}{ident}')
        return inserted
    except Exception as exc:
        conn.rollback()
        print(f'    {table:<22} FAILED: {exc}')
        return 0
    finally:
        conn.close()


def main():
    if not db.is_postgres():
        print('DATABASE_URL is not set (or HB_DB_BACKEND=sqlite).')
        print('Set DATABASE_URL in .env before running this migration.')
        return 1

    print(f'Target : {db.DATABASE_URL.split("@")[-1]}')
    print(f'Mode   : {"DRY RUN" if DRY_RUN else "LIVE"}{" (wiping schemas)" if FORCE else ""}')
    print()

    total = 0
    for sqlite_name, expected in SOURCES.items():
        schema = db.SCHEMA_MAP[sqlite_name]
        print(f'[{sqlite_name} -> schema "{schema}"]')

        if not os.path.exists(sqlite_name):
            print('    file not found, skipped')
            print()
            continue

        present = sqlite_tables(sqlite_name)
        if not present:
            print('    no tables in file')
            print()
            continue

        if FORCE and not DRY_RUN:
            conn = db.connect(sqlite_name)
            for table in present:
                conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            conn.commit()
            conn.close()
            print('    (dropped existing tables)')

        for table in expected:
            if table not in present:
                print(f'    {table:<22} not in sqlite file, skipped')
                continue
            total += migrate_table(sqlite_name, table, present[table], schema)

        extra = [t for t in present if t not in expected]
        for table in extra:
            print(f'    {table:<22} (unexpected table, migrating anyway)')
            total += migrate_table(sqlite_name, table, present[table], schema)

        print()

    print(f'Total rows copied: {total}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
