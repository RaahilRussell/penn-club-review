import json
from pathlib import Path

from app import app
from extensions import db
from models import Club, User, tag_objects


def create_user():
    if User.query.filter_by(username="josh").first() is None:
        db.session.add(User(username="josh"))
        db.session.commit()


def load_json(path=Path(__file__).with_name("clubs.json")):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_data(path=Path(__file__).with_name("clubs.json")):
    for club_data in load_json(path):
        club = Club(
            code=club_data["code"],
            name=club_data["name"],
            description=club_data["description"],
            tags=tag_objects(club_data["tags"]),
        )
        db.session.add(club)
    db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        if db.engine.dialect.name != "sqlite" or db.engine.url.database in (
            None,
            "",
            ":memory:",
        ):
            raise ValueError("Bootstrap requires a file-backed SQLite database.")
        # Dispose connections before replacing the configured SQLite file.
        database = Path(db.engine.url.database)
        db.session.remove()
        db.engine.dispose()
        database.unlink(missing_ok=True)
        db.create_all()
        create_user()
        load_data()
