"""Run the import-order regression against the normal bootstrapped database."""

import subprocess
import sys
import unittest
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    subprocess.run([sys.executable, str(root / "bootstrap.py")], check=True)

    # Production initialization must precede test discovery for this regression.
    from app import app
    from extensions import db
    from sqlalchemy import inspect, text

    def snapshot():
        with app.app_context():
            db.session.remove()
            tables = inspect(db.engine).get_table_names()
            data = {
                table.name: sorted(
                    tuple(row) for row in db.session.execute(table.select())
                )
                for table in db.metadata.sorted_tables
            }
            foreign_keys = db.session.execute(text("PRAGMA foreign_keys")).scalar()
            return tables, data, foreign_keys

    before = snapshot()
    result = unittest.TextTestRunner(verbosity=1).run(
        unittest.defaultTestLoader.discover(str(root / "tests"))
    )
    after = snapshot()
    if before != after or not result.wasSuccessful():
        raise SystemExit("FAILED: tests changed the development database or failed.")
    print("PASS: production imported first; all tables and rows unchanged.")
    print("Rows:", {table: len(rows) for table, rows in after[1].items()})
    print("PRAGMA foreign_keys:", after[2])


if __name__ == "__main__":
    main()
