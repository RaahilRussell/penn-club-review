# Open-Ended Questions

## 1. Authentication

A production signup would accept a unique username/email and a password over HTTPS, validate it, and store only a salted, slow password hash. Werkzeug's password helpers are appropriate for a Flask application; Argon2 or bcrypt would also be reasonable. A database compromise would expose hashes rather than plaintext passwords, though weak passwords could still be attacked offline.

Login would use generic failure messages and rate limiting. Flask-Login can manage the authenticated identity, but session storage and revocation need an explicit design: an opaque session ID in an HttpOnly, Secure, SameSite cookie would reference a server-side session with an expiry. Successful login regenerates the ID and invalidates the old session. Logout deletes that server record and clears the cookie, so a copied old cookie cannot restore access. Cookie-authenticated state changes also require CSRF protection. Signup, login, logout, and current-user routes would have separate responsibilities. Password reset tokens would be short-lived and single-use.

For Penn users, institutional OpenID Connect could avoid managing passwords locally. OpenID Connect supplies authentication on top of OAuth 2.0 authorization; OAuth alone is not a login protocol. Flask-Limiter could protect signup and login endpoints. Usernames/emails need database uniqueness constraints, while responses should avoid revealing whether an account exists.

## 2. Club Comments

Comments would be a table with `id`, `body`, `created_at`, `user_id`, `club_id`, and nullable `parent_id`. `user_id` references `User`, `club_id` references `Club`, and `parent_id` self-references `Comment`. Thus User and Club each have one-to-many comments, while a comment has many child replies. A top-level comment has `parent_id = NULL`; a reply stores its parent comment ID.

Creation would instantiate `Comment(body=body, user_id=user.id, club_id=club.id, parent_id=parent.id if parent else None)`, add it to the session, and commit. First verify that the user and club exist and any parent belongs to that same club. Enforced foreign keys support this validation. An adjacency list is preferable to putting a whole thread in JSON: rows remain queryable, independently editable, and indexable.

Deleting a comment should usually soft-delete its body while retaining the row, author relationship, and reply chain. If hard deletion is required, a deliberate cascade policy is needed. Large threads should use paginated children and controlled-depth recursion rather than loading an unbounded tree.

## 3. Route Caching

As traffic grows, public read-heavy routes such as `GET /api/clubs` and `GET /api/tags` could use Flask-Caching with Redis in production. Keys should include the route and meaningful query parameters normalized exactly like the implementation: a trimmed, case-folded search value. A modest TTL limits staleness.

Mutation responses should not generally be cached. After committing club or tag changes, invalidate club-list/search entries and the tag listing, whose counts and associated names may have changed. A conservative invalidation of those public route namespaces is simpler than complicated dependency tracking. I would leave `GET /api/users/<username>` uncached initially: its favorites and nested club information change after several kinds of write. Any later private cache needs identity-scoped keys and appropriate authorization; it must never reuse unsafe public keys.

This five-club SQLite fixture does not justify Redis's operational complexity. SQLite and direct queries are clearer here; caching becomes worthwhile only after measured read load and an agreed staleness policy.
