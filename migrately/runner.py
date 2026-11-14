"""Migration runner.

A migration is a named set of statements with an optional rollback. The runner records
which ones have run, applies the rest in order inside a transaction, and refuses to
continue if the ledger does not match the source directory.
"""
import hashlib
import os
import re

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    checksum   TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

FILE_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class Migration:
    __slots__ = ("version", "name", "up", "down", "checksum")

    def __init__(self, version, name, up, down=""):
        self.version = version
        self.name = name
        self.up = up
        self.down = down
        self.checksum = hashlib.sha256((up + "\x00" + down).encode()).hexdigest()

    def __repr__(self):
        return "Migration(%s_%s)" % (self.version, self.name)


def split_sql(text):
    """Split on semicolons outside single quotes and line comments."""
    out, buf, quote = [], [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        for ch in line:
            if ch == "'":
                quote = not quote
            if ch == ";" and not quote:
                statement = "".join(buf).strip()
                if statement:
                    out.append(statement)
                buf = []
                continue
            buf.append(ch)
        buf.append("\n")
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def load_migrations(directory):
    """Read every NNNN_name.sql file. A matching NNNN_name.down.sql is the rollback."""
    migrations = []
    for name in sorted(os.listdir(directory)):
        match = FILE_PATTERN.match(name)
        if not match:
            continue
        version, label = match.groups()
        up = open(os.path.join(directory, name), encoding="utf-8").read()
        down_path = os.path.join(directory, "%s_%s.down.sql" % (version, label))
        down = open(down_path, encoding="utf-8").read() if os.path.exists(down_path) else ""
        migrations.append(Migration(version, label, up, down))
    return migrations


class Runner:
    def __init__(self, connection, migrations):
        self.db = connection
        self.migrations = sorted(migrations, key=lambda m: m.version)
        self.db.executescript(LEDGER)
        self.db.commit()

    def applied(self):
        rows = self.db.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
        return {version: checksum for version, checksum in rows}

    def pending(self):
        done = self.applied()
        return [m for m in self.migrations if m.version not in done]

    def verify(self):
        """Raise if an applied migration was edited after it ran."""
        done = self.applied()
        for migration in self.migrations:
            known = done.get(migration.version)
            if known and known != migration.checksum:
                raise RuntimeError(
                    "migration %s changed after it was applied" % migration.version)

    def up(self, target=None):
        self.verify()
        count = 0
        for migration in self.pending():
            if target and migration.version > target:
                break
            self.db.execute("BEGIN")
            try:
                for statement in split_sql(migration.up):
                    self.db.execute(statement)
                self.db.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)",
                    (migration.version, migration.checksum))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            count += 1
        return count

    def down(self, steps=1):
        done = list(self.applied())
        for version in reversed(done[-steps:]):
            migration = next(m for m in self.migrations if m.version == version)
            if not migration.down.strip():
                raise RuntimeError("migration %s has no rollback" % version)
            self.db.execute("BEGIN")
            try:
                for statement in split_sql(migration.down):
                    self.db.execute(statement)
                self.db.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return min(steps, len(done))
