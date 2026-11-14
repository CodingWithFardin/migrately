# migrately

Schema migrations for SQLite: numbered files, a checksum ledger, transactions per
migration, and rollback scripts that are checked before they are used.

The failure this is built to prevent is the quiet one: a migration edited after it
ran somewhere. Every applied migration stores a sha256 of its text, and the runner
refuses to continue when the file no longer matches the ledger.

## Install

Python 3.11+, stdlib only.

```
git clone https://github.com/CodingWithFardin/migrately.git
cd migrately
python -m unittest discover -s tests -t .
```

## Layout

```
migrations/
  0001_users.sql
  0001_users.down.sql
  0002_posts.sql
```

`NNNN_name.sql` is the forward migration, `NNNN_name.down.sql` is the rollback.
Order is by the numeric prefix, not by filename.

## Use

```python
import sqlite3
from migrately import Runner, load_migrations

db = sqlite3.connect("app.db")
runner = Runner(db, load_migrations("migrations"))
runner.up()            # everything pending
runner.up("0002")      # stop after 0002
runner.down(1)         # undo the last one
```

## Rules

- Each migration runs in its own transaction; a failing statement rolls back the
  whole migration, including the ledger row.
- `down` refuses to run when the matching `.down.sql` is missing, rather than
  silently marking the migration unapplied.
- `verify()` raises if an applied migration's checksum changed.
- Statements are split on semicolons outside single quotes and line comments, so
  `'a;b'` stays in one statement.

## Files

- `migrately/runner.py` - ledger, ordering, checksums, up/down.
- `tests/` - ordering, rollback, tampering and partial-failure behaviour.

MIT, 2026.
