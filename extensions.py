import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def configure_sqlite(connection, _):
    if isinstance(connection, sqlite3.Connection):
        connection.create_function(
            "casefold",
            1,
            lambda value: value.casefold() if value is not None else None,
            deterministic=True,
        )
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
