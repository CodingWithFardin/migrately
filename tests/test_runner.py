import sqlite3
import unittest

from migrately.runner import Migration, Runner, split_sql


def make(*migrations):
    db = sqlite3.connect(":memory:")
    return db, Runner(db, list(migrations))


class SplitTest(unittest.TestCase):
    def test_semicolons_in_strings_are_kept(self):
        statements = split_sql("INSERT INTO t VALUES ('a;b'); SELECT 1;")
        self.assertEqual(len(statements), 2)

    def test_comments_are_dropped(self):
        self.assertEqual(split_sql("-- hi\nSELECT 1;"), ["SELECT 1"])

    def test_trailing_statement_without_semicolon(self):
        self.assertEqual(split_sql("SELECT 1"), ["SELECT 1"])


class RunnerTest(unittest.TestCase):
    def test_applies_in_order_once(self):
        m1 = Migration("0001", "users", "CREATE TABLE users (id INTEGER);")
        m2 = Migration("0002", "posts", "CREATE TABLE posts (id INTEGER);")
        db, runner = make(m2, m1)
        self.assertEqual(runner.up(), 2)
        self.assertEqual(runner.pending(), [])
        self.assertEqual(runner.up(), 0)

    def test_rollback_removes_object_and_ledger_row(self):
        m1 = Migration("0001", "users", "CREATE TABLE users (id INTEGER);",
                       "DROP TABLE users;")
        db, runner = make(m1)
        runner.up()
        runner.down(1)
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertNotIn("users", tables)
        self.assertEqual(runner.applied(), {})

    def test_edited_migration_is_refused(self):
        m1 = Migration("0001", "users", "CREATE TABLE users (id INTEGER);")
        db, runner = make(m1)
        runner.up()
        edited = Migration("0001", "users", "CREATE TABLE users (id INTEGER, name TEXT);")
        runner2 = Runner(db, [edited])
        with self.assertRaises(RuntimeError):
            runner2.up()

    def test_rollback_without_script_is_refused(self):
        m1 = Migration("0001", "users", "CREATE TABLE users (id INTEGER);")
        db, runner = make(m1)
        runner.up()
        with self.assertRaises(RuntimeError):
            runner.down(1)

    def test_failed_migration_rolls_back(self):
        bad = Migration("0001", "bad", "CREATE TABLE ok (id INTEGER); SELECT nope;")
        db, runner = make(bad)
        with self.assertRaises(sqlite3.Error):
            runner.up()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertNotIn("ok", tables)
        self.assertEqual(runner.applied(), {})


if __name__ == "__main__":
    unittest.main()
