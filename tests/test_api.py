import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app import app as production_app, create_app
from bootstrap import create_user, load_data, load_json
from extensions import db
from models import Club, Tag, User, club_tags, normalize_tag_name, user_favorites

ROOT = Path(__file__).resolve().parents[1]


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.application = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.directory.name}/test.db",
            }
        )
        self.client = self.application.test_client()
        with self.application.app_context():
            db.create_all()
            create_user()
            load_data()

    def tearDown(self):
        with self.application.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def payload(self, **changes):
        return (
            dict(
                code="new-club",
                name="New Club",
                description="Description",
                tags=["Technology"],
            )
            | changes
        )

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertIsInstance(response.json["error"], str)

    def test_fixture_matches_database(self):
        fixture = load_json()
        with self.application.app_context():
            self.assertEqual(User.query.one().username, "josh")
            create_user()
            self.assertEqual(User.query.count(), 1)
            self.assertEqual(Club.query.count(), len(fixture))
            self.assertEqual(
                Tag.query.count(),
                len({normalize_tag_name(t) for c in fixture for t in c["tags"]}),
            )
            self.assertEqual(
                db.session.execute(text("select count(*) from club_tags")).scalar(), 12
            )
            for record in fixture:
                actual = Club.query.filter_by(code=record["code"]).one().to_dict()
                self.assertEqual(
                    actual | {"tags": sorted(actual["tags"])},
                    record | {"tags": sorted(record["tags"])},
                )
            self.assertEqual(
                len(Tag.query.filter_by(name="Undergraduate").one().clubs), 4
            )

    def test_list(self):
        response = self.client.get("/api/clubs")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json, list)
        self.assertEqual(len(response.json), 5)
        self.assertEqual(set(response.json[0]), {"code", "name", "description", "tags"})

    def test_search_literal_and_case(self):
        self.client.post("/api/clubs", json=self.payload(name="100%_done /"))
        for query, expected in [
            ("MEMES", 1),
            ("locust", 1),
            ("missing", 0),
            ("%", 1),
            ("_", 1),
            ("/", 1),
            ("", 6),
            ("  ", 6),
        ]:
            with self.subTest(query=query):
                result = self.client.get("/api/clubs", query_string={"search": query})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(len(result.json), expected)

    def test_unicode_search_case(self):
        self.client.post("/api/clubs", json=self.payload(name="École Straße"))
        for search in ("ÉCOLE", "école", "STRASSE"):
            response = self.client.get("/api/clubs", query_string={"search": search})
            self.assertEqual(len(response.json), 1)

    def test_user(self):
        self.assertEqual(
            self.client.get("/api/users/josh").json,
            {"username": "josh", "favorites": []},
        )
        self.assert_error(self.client.get("/api/users/missing"), 404)

    def test_tags(self):
        response = self.client.get("/api/tags")
        self.assertEqual(response.status_code, 200)
        tag = next(t for t in response.json if t["name"] == "Undergraduate")
        self.assertEqual(tag["club_count"], 4)
        self.assertEqual(
            {c["code"] for c in tag["clubs"]},
            {"pppjo", "pppp", "locustlabs", "lorem-ipsum"},
        )

    def test_create_and_duplicate(self):
        response = self.client.post("/api/clubs", json=self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json, self.payload())
        self.assert_error(self.client.post("/api/clubs", json=self.payload()), 409)
        with self.application.app_context():
            self.assertEqual(Club.query.filter_by(code="new-club").count(), 1)
            self.assertEqual(Tag.query.filter_by(name="Technology").count(), 1)

    def test_code_contract(self):
        for code in ["a/b", "a?b", "a#b", " ", "a b", "é", "a" * 81, None, 123]:
            with self.subTest(code=code):
                self.assert_error(
                    self.client.post("/api/clubs", json=self.payload(code=code)), 400
                )
        for code in ["valid-hyphen", "valid_underscore", " Mixed_123 "]:
            self.assertEqual(
                self.client.post(
                    "/api/clubs", json=self.payload(code=code)
                ).status_code,
                201,
            )

    def test_unicode_tag_reuse(self):
        for index, name in enumerate([" École ", "ÉCOLE", "E\u0301cole", "École"]):
            response = self.client.post(
                "/api/clubs",
                json=self.payload(code=f"unicode-{index}", tags=[name, name]),
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["tags"], ["École"])
        with self.application.app_context():
            tag = Tag.query.filter_by(normalized_name="école").one()
            self.assertEqual(len(tag.clubs), 4)
            self.assertEqual(Tag.query.count(), 8)

    def test_duplicate_tags_and_compatibility_normalization(self):
        response = self.client.post(
            "/api/clubs",
            json=self.payload(tags=[" Technology ", "TECHNOLOGY", "Ｔｅｃｈｎｏｌｏｇｙ"]),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["tags"], ["Technology"])

    def test_invalid_create_fields(self):
        for changes in [
            {"name": ""},
            {"description": " "},
            {"name": 4},
            {"description": None},
            {"tags": None},
            {"tags": "tag"},
            {"tags": [" "]},
            {"tags": [1]},
            {"extra": True},
        ]:
            with self.subTest(changes=changes):
                self.assert_error(
                    self.client.post("/api/clubs", json=self.payload(**changes)), 400
                )
        for field in self.payload():
            payload = self.payload()
            del payload[field]
            self.assert_error(self.client.post("/api/clubs", json=payload), 400)

    def test_invalid_bodies_for_all_mutations(self):
        for method, path in [
            ("POST", "/api/clubs"),
            ("PATCH", "/api/clubs/pppjo"),
            ("POST", "/api/clubs/pppjo/favorites"),
        ]:
            for options in [
                {},
                {"data": "{", "content_type": "application/json"},
                {"json": []},
                {"json": {}},
                {"data": "null", "content_type": "application/json"},
            ]:
                with self.subTest(method=method, options=options):
                    self.assert_error(
                        self.client.open(path, method=method, **options), 400
                    )

    def test_patch_persists_fields_and_tags(self):
        self.client.post("/api/clubs", json=self.payload(tags=["École"]))
        response = self.client.patch(
            "/api/clubs/pppjo",
            json={
                "name": "Changed",
                "description": "New description",
                "tags": ["ÉCOLE", " New "],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json["tags"]), {"École", "New"})
        with self.application.app_context():
            club = Club.query.filter_by(code="pppjo").one()
            self.assertEqual(club.name, "Changed")
            self.assertEqual(club.description, "New description")
            self.assertEqual(
                len(Tag.query.filter_by(normalized_name="école").one().clubs), 2
            )
        self.assertEqual(
            self.client.patch("/api/clubs/pppjo", json={"tags": []}).json["tags"], []
        )

    def test_invalid_patch_is_atomic(self):
        before = self.client.get("/api/clubs").json
        for changes in [
            {"name": ""},
            {"description": []},
            {"code": "new"},
            {"tags": [None]},
            {"name": "Changed", "tags": ["new-tag", ""]},
        ]:
            self.assert_error(self.client.patch("/api/clubs/pppjo", json=changes), 400)
        self.assertEqual(self.client.get("/api/clubs").json, before)
        self.assert_error(
            self.client.patch("/api/clubs/missing", json={"name": "x"}), 404
        )

    def test_favorite_is_idempotent(self):
        for _ in range(2):
            response = self.client.post(
                "/api/clubs/pppjo/favorites", json={"username": "josh"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual([c["code"] for c in response.json["favorites"]], ["pppjo"])
        with self.application.app_context():
            self.assertEqual(
                db.session.execute(
                    text("select count(*) from user_favorites")
                ).scalar(),
                1,
            )
        self.assertEqual(len(self.client.get("/api/users/josh").json["favorites"]), 1)

    def test_invalid_favorites(self):
        for username in [None, [], 1, " "]:
            self.assert_error(
                self.client.post(
                    "/api/clubs/pppjo/favorites", json={"username": username}
                ),
                400,
            )
        self.assert_error(
            self.client.post(
                "/api/clubs/pppjo/favorites", json={"username": "missing"}
            ),
            404,
        )
        self.assert_error(
            self.client.post("/api/clubs/missing/favorites", json={"username": "josh"}),
            404,
        )

    def test_foreign_keys_on_new_connections(self):
        with self.application.app_context():
            for _ in range(2):
                db.session.remove()
                db.engine.dispose()
                self.assertEqual(
                    db.session.execute(text("PRAGMA foreign_keys")).scalar(), 1
                )
                for table, values in [
                    (club_tags, dict(club_id=99999, tag_id=99999)),
                    (user_favorites, dict(user_id=99999, club_id=99999)),
                ]:
                    with self.assertRaises(IntegrityError):
                        db.session.execute(table.insert().values(**values))
                        db.session.commit()
                    db.session.rollback()

    def test_composite_and_canonical_uniqueness(self):
        self.client.post("/api/clubs/pppjo/favorites", json={"username": "josh"})
        with self.application.app_context():
            for table in (club_tags, user_favorites):
                values = dict(db.session.execute(table.select()).mappings().first())
                with self.assertRaises(IntegrityError):
                    db.session.execute(table.insert().values(**values))
                    db.session.commit()
                db.session.rollback()
            db.session.add(Tag(name="TECHNOLOGY"))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_integrity_conflict_rolls_back(self):
        with patch(
            "app.db.session.commit",
            side_effect=IntegrityError("insert", {}, Exception()),
        ):
            self.assert_error(self.client.post("/api/clubs", json=self.payload()), 409)
        with self.application.app_context():
            self.assertEqual(Club.query.count(), 5)
        self.assertEqual(
            self.client.post("/api/clubs", json=self.payload()).status_code, 201
        )

    def test_relationship_query_counts(self):
        with self.application.app_context():
            statements = []

            def count(*args):
                statements.append(args[2])

            event.listen(db.engine, "before_cursor_execute", count)
            try:
                for path in ("/api/clubs", "/api/tags"):
                    statements.clear()
                    self.assertEqual(self.client.get(path).status_code, 200)
                    self.assertEqual(len(statements), 2)
            finally:
                event.remove(db.engine, "before_cursor_execute", count)

    def test_application_engines_are_distinct(self):
        with production_app.app_context():
            production_engine = db.engine
        with self.application.app_context():
            self.assertIsNot(db.engine, production_engine)
            self.assertEqual(
                Path(db.engine.url.database).parent, Path(self.directory.name)
            )

    def test_bootstrap_cli_repeated_and_imports(self):
        env = os.environ | {
            "CLUBREVIEW_DATABASE_URI": f"sqlite:///{self.directory.name}/bootstrap.db"
        }
        for _ in range(2):
            subprocess.run(
                [sys.executable, "bootstrap.py"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )
        application = create_app(
            {"SQLALCHEMY_DATABASE_URI": env["CLUBREVIEW_DATABASE_URI"]}
        )
        with application.app_context():
            self.assertEqual(Club.query.count(), 5)
            self.assertEqual(Tag.query.count(), 7)
            self.assertEqual(User.query.one().username, "josh")
            db.session.remove()
            db.engine.dispose()
        subprocess.run(
            [sys.executable, "-c", "import models; import app"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )

    def test_home_and_http_errors(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Penn Club Review", response.data)
        self.assertNotIn(b"Penn Clubs", response.data)
        self.assert_error(self.client.get("/api/unknown"), 404)
        self.assert_error(self.client.delete("/api/clubs"), 405)


if __name__ == "__main__":
    unittest.main()
