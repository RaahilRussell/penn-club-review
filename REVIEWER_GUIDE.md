# Penn Club Review — Reviewer Guide

## What this is

Penn Club Review is a Penn Labs Backend Challenge submission built with Flask and SQLAlchemy. It loads the supplied Penn Clubs fixture into SQLite and exposes a REST API for club discovery, editing, and favorites. The backend is the core challenge; a lightweight frontend provides an integration demo using the same API.

## Quick Start

With Python 3.12 and Poetry installed, run from the repository root:

```bash
poetry install --no-root
poetry run python bootstrap.py
poetry run flask --app app run
```

Open http://127.0.0.1:5000. Bootstrap recreates the local database, so running it again discards edits and favorites. Stop Flask with Ctrl+C.

Run the backend tests:

```bash
poetry run python -m unittest discover -s tests -v
```

Optional frontend behavior tests require Node:

```bash
node --test tests/frontend.test.cjs
```

## What to Look At

- `models.py` — relational models, tag identity, and JSON serialization.
- `bootstrap.py` — fixture loading and creation of username `josh`.
- `app.py` — application factory, resource routes, and input validation.
- `extensions.py` — shared database extension and SQLite connection setup.
- `templates/index.html` — integrated HTML/CSS/JavaScript frontend.
- `tests/` — API behavior, database integrity, isolation, and frontend regressions.
- `WRITEUP.md` — the three open-ended design answers.
- `README.md` — complete setup, API contract, and design documentation.

## Architecture

```text
clubs.json -> bootstrap.py -> SQLAlchemy <-> SQLite
                                  ^
                                  |
                                Flask
                                  |
                                  v
                               REST API
                                  |
                                  v
                         lightweight frontend

Club <--- M:N via club_tags ---> Tag
User <--- M:N via user_favorites ---> Club
```

## Key Design Decisions

Tags have a reusable display name and a unique Unicode-normalized, case-folded identity. Association tables prevent duplicate club/tag and user/favorite pairs; SQLite enforces their foreign keys. The minimal User model contains only an ID and username because authentication is not implemented.

Small `to_dict()` methods define predictable JSON without recursive relationships. Resource-oriented routes use JSON bodies for mutations, validation errors return 400, missing resources return 404, and conflicts return 409. Creating a club returns 201; repeating a favorite returns the existing relationship. The application factory lets tests select a temporary database before SQLAlchemy initializes.

## API Snapshot

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Integrated frontend |
| GET | `/api` | API welcome message |
| GET | `/api/clubs` | All clubs; explicitly required Penn Labs route; optional name search |
| POST | `/api/clubs` | Create a club with tags |
| PATCH | `/api/clubs/<code>` | Update name, description, or tags |
| GET | `/api/tags` | Tags, club counts, and associated clubs |
| GET | `/api/users/<username>` | User and favorite clubs |
| POST | `/api/clubs/<code>/favorites` | Add a favorite for a user |

## Verification

The backend suite verifies fixture values, Josh creation, the JSON club array, validation and missing-resource errors, Unicode tag reuse, foreign keys, and unique relationships. Tests use dedicated temporary SQLite files. A separate isolation check verifies that importing the development app before test discovery does not change its data. Frontend tests exercise request ordering, favorites, errors, and escaping using DOM doubles; they do not establish visual browser coverage.

## Scope / Non-goals

This is intentionally a compact technical-challenge backend, not a production Penn Clubs deployment. Josh is a demonstration identity. Production authentication, threaded comments, and distributed caching are discussed in `WRITEUP.md`; they are not implemented. The frontend has no separate build system or duplicate fixture dataset.

## Reviewer Shortcut

If you only have five minutes, read `models.py`, `app.py`, `tests/test_api.py`, and `WRITEUP.md`, then run the backend test command above.
