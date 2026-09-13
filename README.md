# Penn Club Review

## Overview

A small Flask/SQLAlchemy club directory with search, tags, and user favorites. The optional browser client uses the same API. Penn Club Review is a challenge submission inspired by Penn Clubs, not the official website.

For a quick tour, start with [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md).

## Installation

From the repository directory, with Python 3.12 and Poetry installed:

```sh
poetry env use python3.12
poetry install --no-root
```

The supplied dependency versions and lockfile are retained.

## Database Setup

```sh
poetry run python bootstrap.py
```

This **deletes and recreates** the configured SQLite database, loads all five records from `clubs.json`, and creates the user `josh`. Running it again discards edits and favorites. The default database is `instance/clubreview.db`; an optional `CLUBREVIEW_DATABASE_URI` overrides it. Bootstrap requires a file-backed SQLite URI and resolves the fixture relative to its source file.

## Running

```sh
poetry run flask --app app run
# Alternatively:
poetry run python app.py
```

Open http://127.0.0.1:5000. Stop with Ctrl+C. These are local development commands.

The browser supports search, club creation, description editing, and favorites for Josh. Full descriptions are visible. Tags are ranked by associated club count. There is no login: Josh is a demonstration user, not an authenticated identity. Name and tag edits are available through PATCH.

## Data Model

- `Club`: integer primary key, unique required code, required name and description.
- `Tag`: integer primary key, display name, and unique required `normalized_name`.
- `User`: integer primary key and unique required username. No speculative authentication fields.
- `club_tags`: club/tag foreign keys with a composite primary key.
- `user_favorites`: user/club foreign keys with a composite primary key.

```text
Club 1 -- many club_tags many -- 1 Tag
User 1 -- many user_favorites many -- 1 Club
```

Tags are reusable relational entities, allowing shared categories and accurate associations without repeated string blobs. Favorites likewise use database-enforced unique pairs. SQLite foreign keys are enabled on every SQLAlchemy connection. No entity-delete cascades are configured; PATCH removes tag links without deleting shared tags.

Tag identity is `NFKC(name).strip().casefold()`. Thus `École`, `ÉCOLE`, and decomposed `École` reuse one row. The first persisted spelling, normalized with NFKC and trimmed, remains the display name. Repeated tags within one request collapse to one link. The model sets canonical identity whenever its display name is assigned; the database enforces canonical uniqueness.

## API

Club JSON: `{"code":"robotics","name":"Robotics","description":"Build robots.","tags":["Technology"]}`.
User JSON: `{"username":"josh","favorites":[club, ...]}`.
Tag JSON: `{"name":"Technology","club_count":1,"clubs":[{"code":"robotics","name":"Robotics"}]}`.

| Method | Path | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| GET | `/` | None | 200, HTML browser client | — |
| GET | `/api` | None | 200, JSON welcome message | — |
| GET | `/api/clubs` | Optional `?search=text` | 200, array of clubs ordered by code | — |
| GET | `/api/tags` | None | 200, array of tags ordered by display name | — |
| GET | `/api/users/<username>` | None | 200, user and favorites | 404 missing user |
| POST | `/api/clubs` | JSON with code, name, description, tags | 201, created club | 400 invalid input; 409 duplicate/conflict |
| PATCH | `/api/clubs/<code>` | JSON with any of name, description, tags | 200, updated club | 400 invalid input; 404 missing club; 409 conflict |
| POST | `/api/clubs/<code>/favorites` | `{"username":"josh"}` | 200, user and favorites | 400 invalid input; 404 missing user/club; 409 conflict |

Validation and semantics:

- JSON bodies must be non-empty objects; unknown properties are rejected.
- Codes are trimmed, case-sensitive, and contain 1–80 ASCII letters, digits, hyphens, or underscores. Codes cannot be patched.
- Names, descriptions, and usernames must be non-empty strings after trimming.
- Tags must be an array of non-empty strings; `[]` is allowed. PATCH replaces the tag collection.
- Search trims surrounding whitespace and matches a literal substring after Unicode case folding. Percent signs, underscores, and slashes are literal characters. Empty/whitespace-only search returns all clubs.
- Repeated favorites return 200 with the existing relationship; they do not add another row.
- Errors use `{"error":"message"}`, including routing 404/405 responses. Database integrity conflicts roll back and return 409; clients can refresh and retry.

## Testing

```sh
poetry run python -m unittest discover -s tests -v
node --test tests/frontend.test.cjs
poetry run python tests/verify_isolation.py
```

Each backend test constructs its own application and temporary SQLite file. Cleanup disposes that engine and removes only the temporary directory. Tests never drop tables on the production application.

The isolation verification command deliberately recreates the development database first, imports the production app before test discovery, runs the full backend suite, then checks that every table and row remains unchanged.

The optional frontend tests use Node's built-in test runner (tested with Node 25.9.0), DOM doubles, and controlled responses to exercise the actual page script. They cover races, errors, encoding, ranking, and escaping; they are not visual browser tests. There is no frontend build or package installation step.

## Design Decisions

An application factory makes database configuration explicit before extension initialization. A small shared `extensions.py` avoids circular imports. Model validation centralizes tag/code policies; reusable serializers keep response shapes consistent. Select-in loading avoids relationship N+1 queries. A SQLite case-folding function supports Unicode search without changing user text or building a separate search index.

## Dependencies and Submission

No runtime dependencies were added. Python uses the original Poetry lock; the frontend uses vanilla JavaScript.

Include `app.py`, `extensions.py`, `models.py`, `bootstrap.py`, `clubs.json`, `templates/`, `tests/`, `README.md`, `REVIEWER_GUIDE.md`, `WRITEUP.md`, `pyproject.toml`, `poetry.lock`, and `.gitignore`. References and local requirement notes are private context and ignored. Do not include SQLite databases, environment files, caches, or virtual environments. When making a ZIP, select submission files explicitly: Git ignore rules alone do not exclude files from arbitrary ZIP tools.
