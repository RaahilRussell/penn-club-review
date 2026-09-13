import re
import unicodedata

from sqlalchemy.orm import validates

from extensions import db


def normalize_tag_name(name):
    return unicodedata.normalize("NFKC", name).strip().casefold()


def tag_objects(names):
    if not isinstance(names, list) or any(
        not isinstance(name, str) or not normalize_tag_name(name) for name in names
    ):
        raise ValueError("tags must be a list of non-empty strings.")
    display_names = {}
    for name in names:
        display_names.setdefault(
            normalize_tag_name(name), unicodedata.normalize("NFKC", name).strip()
        )
    existing = {
        tag.normalized_name: tag
        for tag in Tag.query.filter(Tag.normalized_name.in_(display_names)).all()
    }
    return [
        existing[key] if key in existing else Tag(name=name)
        for key, name in display_names.items()
    ]


club_tags = db.Table(
    "club_tags",
    db.Column("club_id", db.Integer, db.ForeignKey("club.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)

user_favorites = db.Table(
    "user_favorites",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("club_id", db.Integer, db.ForeignKey("club.id"), primary_key=True),
)


class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.relationship(
        "Tag", secondary=club_tags, back_populates="clubs", order_by="Tag.name"
    )

    @validates("code")
    def validate_code(self, _, code):
        if not isinstance(code, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", code.strip()
        ):
            raise ValueError(
                "code must contain 1–80 ASCII letters, digits, hyphens or underscores."
            )
        return code.strip()

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "tags": [tag.name for tag in self.tags],
        }


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    normalized_name = db.Column(db.Text, unique=True, nullable=False)
    clubs = db.relationship(
        "Club", secondary=club_tags, back_populates="tags", order_by="Club.code"
    )

    @validates("name")
    def validate_name(self, _, name):
        if not isinstance(name, str) or not normalize_tag_name(name):
            raise ValueError("Tag names must be non-empty strings.")
        self.normalized_name = normalize_tag_name(name)
        return unicodedata.normalize("NFKC", name).strip()

    def to_dict(self):
        return {
            "name": self.name,
            "club_count": len(self.clubs),
            "clubs": [{"code": club.code, "name": club.name} for club in self.clubs],
        }


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    favorites = db.relationship(
        "Club", secondary=user_favorites, backref="favorited_by", order_by="Club.code"
    )

    def to_dict(self):
        return {
            "username": self.username,
            "favorites": [club.to_dict() for club in self.favorites],
        }
