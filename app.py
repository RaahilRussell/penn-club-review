import os

from flask import Flask, jsonify, render_template, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import HTTPException

from extensions import db
from models import Club, Tag, User, tag_objects

DB_FILE = "clubreview.db"


def create_app(config_override=None):
    application = Flask(__name__)
    application.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "CLUBREVIEW_DATABASE_URI", f"sqlite:///{DB_FILE}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    application.config.update(config_override or {})
    db.init_app(application)
    application.add_url_rule("/", view_func=main)
    application.add_url_rule("/api", view_func=api)
    application.add_url_rule("/api/clubs", view_func=clubs, methods=["GET", "POST"])
    application.add_url_rule("/api/tags", view_func=get_tags)
    application.add_url_rule("/api/users/<username>", view_func=get_user)
    application.add_url_rule(
        "/api/clubs/<code>", view_func=update_club, methods=["PATCH"]
    )
    application.add_url_rule(
        "/api/clubs/<code>/favorites", view_func=favorite_club, methods=["POST"]
    )
    application.register_error_handler(ValueError, invalid_input)
    application.register_error_handler(IntegrityError, integrity_conflict)
    application.register_error_handler(HTTPException, http_error)
    return application


def invalid_input(error):
    db.session.rollback()
    return jsonify(error=str(error)), 400


def integrity_conflict(error):
    db.session.rollback()
    return (
        jsonify(error="The request conflicts with existing data. Refresh and retry."),
        409,
    )


def http_error(error):
    response = error.get_response()
    response.data = jsonify(error=error.description).get_data()
    response.content_type = "application/json"
    return response


def json_object(allowed):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Request body must be a non-empty JSON object.")
    unknown = set(payload) - set(allowed)
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}.")
    return payload


def club_fields(payload):
    fields = {}
    for field in ("name", "description"):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string.")
            fields[field] = value.strip()
    if "tags" in payload:
        fields["tags"] = tag_objects(payload["tags"])
    return fields


def main():
    return render_template("index.html")


def api():
    return jsonify(message="Welcome to the Penn Club Review API!")


def clubs():
    if request.method == "GET":
        search = request.args.get("search", "").strip()
        query = Club.query.options(selectinload(Club.tags))
        if search:
            query = query.filter(
                func.casefold(Club.name).contains(search.casefold(), autoescape=True)
            )
        return jsonify([club.to_dict() for club in query.order_by(Club.code).all()])
    required = {"code", "name", "description", "tags"}
    payload = json_object(required)
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}.")
    club = Club(code=payload["code"])
    if Club.query.filter_by(code=club.code).first() is not None:
        return jsonify(error="A club with that code already exists."), 409
    for field, value in club_fields(payload).items():
        setattr(club, field, value)
    db.session.add(club)
    db.session.commit()
    return jsonify(club.to_dict()), 201


def get_user(username):
    user = (
        User.query.options(selectinload(User.favorites).selectinload(Club.tags))
        .filter_by(username=username)
        .first()
    )
    if user is None:
        return jsonify(error="User not found."), 404
    return jsonify(user.to_dict())


def get_tags():
    tags = Tag.query.options(selectinload(Tag.clubs)).order_by(Tag.name).all()
    return jsonify([tag.to_dict() for tag in tags])


def update_club(code):
    club = Club.query.filter_by(code=code).first()
    if club is None:
        return jsonify(error="Club not found."), 404
    fields = club_fields(json_object({"name", "description", "tags"}))
    for field, value in fields.items():
        setattr(club, field, value)
    db.session.commit()
    return jsonify(club.to_dict())


def favorite_club(code):
    club = Club.query.filter_by(code=code).first()
    if club is None:
        return jsonify(error="Club not found."), 404
    username = json_object({"username"}).get("username")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a non-empty string.")
    user = User.query.filter_by(username=username.strip()).first()
    if user is None:
        return jsonify(error="User not found."), 404
    if club not in user.favorites:
        user.favorites.append(club)
        db.session.commit()
    return jsonify(user.to_dict())


app = create_app()

if __name__ == "__main__":
    app.run()
