# Codebase Map


## File Summary 

### `app.py` -- Flask App and DB setup 

This file serves as the entry point for the application. It exposes a single public function, `create_app()`, which sets up the Flask app and configures our SQLite database via SQLAlchemy.

It registers four core blueprints, each mounted to a dedicated URL prefix:

- `/songs`

- `/playlists`

- `/users`

- `/feed`

To make sure the database is ready at startup, the factory runs `db.create_all()` inside an app context. Note that because this is an API-only backend, we deliberately didn't include a root route (/), meaning a GET / request will return a 404 by design.

### `models.py` -- Defines SQLAlchemy database schema

`models.py` declares all the database tables/entities and their relationships, using UUID strings as primary keys (via `generate_uuid()`).


| Model   | Purpose |
| ------- | ------- |
| **User** | app users. Tracks `listening_streak` and `last_listened_at`. Has relationships to songs they've shared, ratings they've made, listening events, notifications, playlists they created, and a self-referential friends list via the friendships table. `to_dict()` serializes basic public fields. |
| **Tag** | simple named tag (e.g. genre/mood labels) attachable to songs. |
| **Song** | a shared song (title/artist/album/genre), tied to the User who shared it, with an optional `share_note`. Has ratings, listening events, and tags. `to_dict()` includes tag names. |
| **ListeningEvent** | a log entry recording that a user listened to a song at a given time (used for streaks/history). |
| **Rating** | a user's 1–5 score for a song, with a unique constraint ensuring one rating per user per song. |
| **Playlist** | a named, optionally collaborative playlist created by a user, containing songs via `playlist_entries`. |
| **Notification** | per-user notifications (type, body, read/unread status). |


### `seed_data.py` -- Populates the database with realistic test data

This script is a standalone utility (run via `python seed_data.py`) that wipes and repopulates the database with a consistent set of sample data for local development and testing. It exposes a single function, `seed()`, which does the following:

- **Resets the schema**: drops and recreates all tables via `db.drop_all()` / `db.create_all()`, so each run starts from a clean slate.
- **Creates users and friendships**: adds 5 users with varying `listening_streak` values and wires up bidirectional friendships between several of them via the `friendships` association table.
- **Creates tags**: adds 10 genre/mood tags (e.g. "rap", "lo-fi", "jazz").
- **Creates songs**: adds 13 songs shared by different users, split into three groups to exercise different tagging scenarios — songs with 0 tags, 1 tag, and 3+ tags (the multi-tag group specifically exists to expose "Issue #3").
- **Creates listening events**: adds a few very recent events (within the last 30 minutes, meant to show up in a "listening now" feature) and a batch of older events (1–14 days old, meant to be excluded from "listening now"). It also manually sets `last_listened_at` on a few users to simulate active streaks.
- **Creates playlists**: adds 3 playlists (each created by a different user) and populates each with overlapping subsets of the seeded songs via the `playlist_entries` table.
- **Creates a notification**: adds one `song_added_to_playlist` notification as a reference example of the correct notification pattern (relevant to "Issue #4").
- **Commits and logs a summary**: commits the session and prints counts of users, songs, playlists, and tags created.

The script runs `seed()` automatically when executed directly (`if __name__ == "__main__"`).

### Services files defined 

#### `streak_service.py`

Handles listening-streak logic for users. A streak increments when a user listens on consecutive calendar days, and resets to 1 if a day is skipped.

- **`record_listening_event(user_id, song_id)`** — Looks up the user, creates a `ListeningEvent` for the given song at the current UTC time, calls `update_listening_streak()` to update the user's streak, commits, and returns the new event.
- **`update_listening_streak(user, now)`** — Applies the streak rules: if the user has never listened before, sets streak to 1; if they already listened today, does nothing; if their last listen was yesterday, increments the streak by 1; otherwise (a gap of more than one day) resets the streak to 1. Updates `last_listened_at` accordingly.
- **`get_streak(user_id)`** — Looks up the user and returns their current `listening_streak` value.

#### `feed_service.py`

Handles the "Friends Listening Now" feed and a general friend activity feed.

- **`get_friends_listening_now(user_id)`** — Finds the current user's friends, queries `ListeningEvent`s from those friends within the last 24 hours, and returns one entry per friend (their most recent recent listen), each with `friend`, `song`, and `listened_at`, ordered most-recent-first.
- **`get_activity_feed(user_id, limit=20)`** — Similar to above but not restricted to a recency window; returns the most recent `limit` listening events across all of the user's friends (can include multiple events per friend), each with `friend`, `song`, and `listened_at`.

#### `search_service.py`

Handles song search and lookup.

- **`search_songs(query)`** — Case-insensitively searches songs whose `title` or `artist` contains the query string (joins in tags), returning a list of song dicts (each including its tags).
- **`get_song(song_id)`** — Looks up a single song by ID and returns its dict representation, raising `ValueError` if it doesn't exist.

#### `notification_service.py`

Handles creating and retrieving notifications, which are generated when friends interact with a user's shared songs (e.g. adding to a playlist, rating).

- **`create_notification(user_id, notification_type, body)`** — Creates and commits a `Notification` record for the given user with a type string and message body.
- **`add_to_playlist(playlist_id, song_id, added_by_user_id)`** — Adds a song to a playlist (if not already present) and, if the adder isn't the original sharer of the song, creates a `song_added_to_playlist` notification for the song's original sharer.
- **`rate_song(user_id, song_id, score)`** — Validates the score is between 1–5, then creates a new `Rating` or updates the user's existing rating for that song, and commits.
- **`get_notifications(user_id, unread_only=False)`** — Returns a user's notifications ordered by most recent first, optionally filtered to only unread ones.
- **`mark_as_read(notification_id)`** — Marks a single notification as read and commits.

#### `playlist_service.py`

Handles playlist creation and retrieval logic.

- **`create_playlist(name, created_by_user_id, is_collaborative=True)`** — Validates the creating user exists, then creates and commits a new `Playlist`.
- **`get_playlist_songs(playlist_id)`** — Returns the songs in a playlist ordered by their position (ascending). Note: as written, this slices off the *last* song in the list (`songs[:-1]`), so it does not actually return all songs in the playlist — likely a bug worth flagging.
- **`get_playlist(playlist_id)`** — Returns a playlist's own metadata (not its songs) as a dict.
- **`get_user_playlists(user_id)`** — Returns all playlists created by a given user.


### Route Files Defined

#### `feed.py`

Exposes HTTP endpoints (blueprint `feed_bp`) for the friend activity feed, delegating all logic to `feed_service`.

- **`GET /<user_id>/listening-now`** — Calls `get_friends_listening_now(user_id)` and returns `{"feed": ..., "count": ...}`; returns 404 with an error message if the user doesn't exist.
- **`GET /<user_id>/activity`** — Calls `get_activity_feed(user_id)` and returns `{"feed": ..., "count": ...}`; returns 404 on a `ValueError` (e.g. unknown user).

#### `playlists.py`

Exposes HTTP endpoints (blueprint `playlists_bp`) for creating and reading playlists, and adding songs to them.

- **`POST /`** — Reads `name`, `created_by`, and optional `is_collaborative` from the JSON body; 400s if `name`/`created_by` are missing; otherwise calls `create_playlist(...)` and returns the new playlist as JSON with status 201 (400 on `ValueError`).
- **`GET /<playlist_id>`** — Calls `get_playlist(playlist_id)` and returns its metadata; 404 if not found.
- **`GET /<playlist_id>/songs`** — Calls `get_playlist_songs(playlist_id)` and returns `{"songs": ..., "count": ...}`; 404 if the playlist doesn't exist.
- **`POST /<playlist_id>/songs`** — Reads `song_id` and `added_by` from the JSON body; 400s if either is missing; otherwise calls `add_to_playlist(playlist_id, song_id, added_by)` (from `notification_service`) and returns a success message with status 201 (400 on `ValueError`).

#### `songs.py`

Exposes HTTP endpoints (blueprint `songs_bp`) for searching songs, viewing song details, rating songs, and logging listens.

- **`GET /search`** — Reads the `q` query parameter; 400s if missing; otherwise calls `search_songs(query)` and returns `{"results": ..., "count": ...}`.
- **`GET /<song_id>`** — Calls `get_song(song_id)` and returns its dict; 404 if not found.
- **`POST /<song_id>/rate`** — Reads `user_id` and `score` from the JSON body; 400s if either is missing; otherwise calls `rate_song(user_id, song_id, int(score))` and returns the rating as JSON with status 201 (400 on `ValueError`, e.g. invalid score).
- **`POST /<song_id>/listen`** — Reads `user_id` from the JSON body; 400s if missing; otherwise calls `record_listening_event(user_id, song_id)` and returns the created event with status 201 (400 on `ValueError`).

#### `users.py`

Exposes HTTP endpoints (blueprint `users_bp`) for fetching user profiles, streaks, and notifications.

- **`GET /<user_id>`** — Looks up the `User` directly via the DB session and returns its dict, or 404 if not found.
- **`GET /<user_id>/streak`** — Calls `get_streak(user_id)` and returns `{"user_id": ..., "streak": ...}`; 404 on `ValueError`.
- **`GET /<user_id>/notifications`** — Reads the `unread_only` query parameter (defaults to `"false"`); calls `get_notifications(user_id, unread_only=...)` and returns `{"notifications": ..., "count": ...}`; 404 on `ValueError`.
- **`POST /notifications/<notification_id>/read`** — Calls `mark_as_read(notification_id)` and returns a success message; 404 on `ValueError`.

### Tests files defined

#### `test_playlists.py`

Tests playlist retrieval logic (`create_playlist`, `get_playlist_songs`) against an in-memory SQLite DB.

- **`app` fixture** — Spins up a Flask app configured with an in-memory SQLite DB and creates/drops all tables around each test.
- **`seed_playlist` fixture** — Creates one user, 5 songs, and a playlist containing all 5 songs (in order, via `playlist_entries` with positions 1–5).
- **`test_playlist_returns_all_songs`** — Asserts `get_playlist_songs` returns all 5 songs in the playlist. Comment notes the known bug causes it to return only 4.
- **`test_playlist_returns_songs_in_order`** — Asserts the returned songs are ordered by position ("Track 1" through "Track 5").
- **`test_empty_playlist_returns_empty_list`** — Asserts a playlist with no songs returns an empty list without error.

#### `test_search.py`

Tests song search logic (`search_songs`), particularly around tag-related duplication bugs, against an in-memory SQLite DB.

- **`app` fixture** — Same pattern as above: in-memory SQLite DB, created/dropped per test.
- **`seed_songs` fixture** — Creates one user, 4 tags, and 3 songs with varying tag counts: no tags ("Midnight Drive"), one tag ("Block Party"), and three tags ("Crown Heights Anthem").
- **`test_search_returns_matching_songs`** — Asserts a search for "Borough" (matches artist) returns "Crown Heights Anthem".
- **`test_search_no_duplicates_single_tag_song`** — Asserts a song with exactly one tag appears only once in results.
- **`test_search_no_duplicates_multi_tag_song`** — Asserts a song with three tags still appears only once. Comment notes the known bug causes it to appear 3 times (once per tag, due to the join in `search_songs`).
- **`test_search_no_duplicates_no_tag_song`** — Asserts a song with zero tags appears exactly once.
- **`test_search_returns_empty_for_no_match`** — Asserts a query with no matches returns an empty list.

#### `test_streaks.py`

Tests listening-streak logic (`update_listening_streak`, `get_streak`) against an in-memory SQLite DB.

- **`app` fixture** — Same in-memory SQLite DB pattern as the other test files.
- **`user` fixture** — Creates a single test user with no listening history.
- **`test_streak_starts_at_1_for_new_user`** — Asserts a first-ever listen sets the streak to 1.
- **`test_streak_increments_on_consecutive_day`** — Asserts listening on Monday then Tuesday increments the streak from 1 to 2.
- **`test_streak_does_not_double_count_same_day`** — Asserts listening twice in the same day (morning and evening) keeps the streak at 1.
- **`test_streak_resets_after_skipped_day`** — Asserts listening Monday then Wednesday (skipping Tuesday) resets the streak to 1.
- **`test_streak_increments_on_sunday`** — Asserts listening Saturday then Sunday increments the streak to 2. This exercises the `today.weekday() != 6` special case in `update_listening_streak` (Sunday is weekday 6), verifying that consecutive-day increments still happen correctly on Sundays.


## Data Flow

### How a song gets into a user's feed

There is no dedicated "feed" table and no push/fan-out step — the feed is computed on read from `ListeningEvent` rows filtered to the requesting user's friends. There are two separate paths: the write path (a user listens to a song) and the read path (a friend requests the feed).

**Write path — a listen gets recorded**

1. `POST /songs/<song_id>/listen` in [routes/songs.py](routes/songs.py) reads `user_id` from the JSON body (400 if missing).
2. It calls **`record_listening_event(user_id, song_id)`** in [services/streak_service.py](services/streak_service.py):
   - Looks up the `User` (raises `ValueError` → 404 if not found).
   - Creates a new `ListeningEvent(user_id, song_id, listened_at=now)` and adds it to the session (not yet committed).
   - Calls **`update_listening_streak(user, now)`**, which mutates `user.listening_streak` and `user.last_listened_at` in place based on the streak rules (first listen, same-day, consecutive-day, or gap).
   - Commits the session (this is the single commit that persists both the new `ListeningEvent` and the updated streak).
3. The route returns the created event as JSON (201).

At this point the song is only "in the feed" implicitly: it now exists as a `ListeningEvent` row tied to the listener. Nothing is written to any friend's data — the fan-out happens at read time, not write time.

**Read path — a friend requests the feed**

4. `GET /feed/<user_id>/listening-now` in [routes/feed.py](routes/feed.py) calls **`get_friends_listening_now(user_id)`** in [services/feed_service.py](services/feed_service.py):
   - Looks up the requesting `User` (raises `ValueError` → 404 if not found).
   - Computes `friend_ids` from `user.friends` (the self-referential many-to-many `friendships` table in [models.py](models.py)).
   - Queries `ListeningEvent` rows where `user_id` is in `friend_ids` and `listened_at >= now - 24h`, ordered most-recent-first.
   - Deduplicates so only the single most recent event per friend survives.
   - For each surviving event, loads the `User` (friend) and `Song` by ID and assembles `{"friend": ..., "song": ..., "listened_at": ...}`.
5. The route wraps the list in `{"feed": ..., "count": ...}` and returns it.

There's a sibling, non-time-boxed version of the read path: `GET /feed/<user_id>/activity` → **`get_activity_feed(user_id, limit=20)`**, which runs the same friend-lookup and event query but without the 24-hour cutoff and without per-friend dedup, capped at `limit` total events instead.

**Call order summary**

```
POST /songs/<id>/listen
  → record_listening_event(user_id, song_id)      [streak_service.py]
      → update_listening_streak(user, now)        [streak_service.py]
      → db.session.commit()

GET /feed/<user_id>/listening-now
  → get_friends_listening_now(user_id)             [feed_service.py]
      → reads user.friends
      → queries ListeningEvent (friend_ids, last 24h)
      → dedups to most-recent-per-friend
      → loads User + Song per event for display
```

Note that adding a song to a *playlist* (`add_to_playlist` in [services/notification_service.py](services/notification_service.py)) is a separate flow that only creates a `Notification` for the original sharer — it does not touch `ListeningEvent` and therefore does not affect this feed.


## Function explanation

### `get_friends_listening_now(user_id)` — [services/feed_service.py:16-62](services/feed_service.py#L16-L62)

**Step by step**

1. **Look up the requesting user.** `db.session.get(User, user_id)`. If no user exists with that ID, raises `ValueError(f"User {user_id} not found")`, which the route layer turns into a 404.
2. **Compute the recency cutoff.** `cutoff = now(UTC) - 24 hours`. Only events at or after this timestamp will count as "listening now."
3. **Collect friend IDs.** `friend_ids = [f.id for f in user.friends]`, using the self-referential `friendships` table. If the user has no friends, returns `[]` immediately — no query is even run.
4. **Query recent listening events.** Fetches all `ListeningEvent` rows where `user_id` is in `friend_ids` AND `listened_at >= cutoff`, ordered most-recent-first (`desc(listened_at)`).
5. **Deduplicate per friend.** Walks the ordered events and keeps only the *first* one seen for each friend (via a `seen_friends` set) — since the list is already sorted newest-first, this is each friend's single most recent qualifying event.
6. **Assemble result dicts.** For each surviving event, loads the `User` (friend) and `Song` by ID and builds `{"friend": friend.to_dict(), "song": song.to_dict(), "listened_at": event.listened_at.isoformat()}`.

**Returns**

A list of dicts (one per friend who has listened to something in the last 24 hours), ordered most-recent-first. Returns `[]` if the user has no friends, or if none of the user's friends have a `ListeningEvent` within the last 24 hours.

**What could cause an unexpected value**

- **Non-existent user_id**: raises `ValueError` rather than returning a value at all — callers must catch this (the route does, converting it to a 404).
- **Asymmetric friendships**: `friendships` is queried only via `primaryjoin=(friendships.c.user_id == id)` — i.e., only rows where *this* user is the `user_id` column count as "friends." If a friendship was inserted in only one direction (e.g. seed/test data adds `A→B` but not `B→A`), `A.friends` includes `B` but `B.friends` does not include `A`. The feed would then silently miss a friend's activity depending on which side of the relationship the row was created from.
- **Timezone-naive `listened_at` values**: the cutoff comparison assumes `ListeningEvent.listened_at` is timezone-aware UTC (matching `datetime.now(timezone.utc)`). If a row was inserted with a naive datetime (no tzinfo) — e.g. from a script or migration that didn't use the same default — SQLAlchemy/SQLite comparisons could behave inconsistently, causing events to be incorrectly included or excluded from the 24-hour window.
- **Deleted/missing Song or User rows**: `db.session.get(User, event.user_id)` and `db.session.get(Song, event.song_id)` assume the referenced rows still exist. If a friend or song was deleted after the event was logged but the `ListeningEvent` row wasn't cleaned up (no cascade delete defined in `models.py`), `friend` or `song` would be `None`, and calling `.to_dict()` on it would raise an `AttributeError`, crashing the request instead of returning a clean result.
- **Clock skew / seed data timestamps**: since "recent" is defined relative to `datetime.now(timezone.utc)` at call time, events seeded as "30 minutes old" only stay in the feed for a fixed window after seeding — running the function long after seeding (>24h) will make previously-visible events disappear, which can look like a bug in testing/demo contexts but is expected behavior.


## Reproduce Bugs

### Bug #1: My listening streak keeps resetting

**How I reproduced it** 

Used a script (`repro_sunday_bug.py`) that spins up the real Flask app with an in-memory SQLite DB and drives it through the actual HTTP routes (Flask test client), so the request/response shapes match exactly what the user's client sees.

- **Data condition**: a user with an existing `listening_streak` of 12 and `last_listened_at` set to Saturday night (UTC).
- **Sequence of actions**:
  1. `POST /songs/<song_id>/listen` with that user's ID, at a "now" faked (via `unittest.mock.patch` on `services.streak_service.datetime`) to be Sunday morning — one calendar day after `last_listened_at`, i.e. a legitimate consecutive-day listen.
  2. `GET /users/<user_id>/streak` to read back the resulting streak.
- **Trigger condition**: the bug only fires when `days_since_last == 1` **and** the current day (`today.weekday()`) is a Sunday (`weekday() == 6`). Any other day of the week with a 1-day gap increments correctly.
- **Result**: streak dropped from 12 to 1, even though the listen was on a consecutive day — reproducing the user's report exactly (including that it only happens on Sundays, and that the next day's listen "starts working again" by incrementing from the reset baseline).
- **Root cause located**: `elif days_since_last == 1 and today.weekday() != 6:` — the `today.weekday() != 6` clause incorrectly excludes Sundays from the increment branch, sending them to the `else` reset branch instead.

**How I found the root cause**

Started at [services/streak_service.py](services/streak_service.py) since the symptom ("streak resets") is entirely owned by `update_listening_streak()` — there's no other file that touches `listening_streak`. Read the function top-down: it computes `days_since_last = (today - last_date).days`, then branches on that value (0 = same day/no-op, 1 = increment, otherwise = reset). The `elif` on line 73 read `days_since_last == 1 and today.weekday() != 6`, which stood out immediately because the docstring above the function (lines 46-50) never mentions any day-of-week exception — it just says "if they listened yesterday, increment." That mismatch between the documented rule and the actual condition was the moment I was confident I'd found the real cause, not just a suspicious area: `weekday()` returns 6 for Sunday in Python, so this clause is specifically false on Sundays, forcing every Sunday consecutive-day listen into the `else` reset branch. I confirmed this wasn't a red herring by checking [tests/test_streaks.py](tests/test_streaks.py), which already had `test_streak_increments_on_sunday` — a test written specifically to catch this — and running it showed it failing with `assert 1 == 2`, matching the exact mechanism.

**The root cause**

In `update_listening_streak()` ([services/streak_service.py:73](services/streak_service.py#L73)), the condition for incrementing the streak was `days_since_last == 1 and today.weekday() != 6`. Python's `datetime.weekday()` returns `6` for Sunday, so this extra clause is `False` every Sunday, regardless of whether the listen was actually on a consecutive day. That routes every Sunday listen — even a legitimate one-day gap from Saturday — into the `else` branch, which unconditionally sets `user.listening_streak = 1`. There is no legitimate reason in the streak rules (first listen, same-day, consecutive-day, gap) for the day of the week to matter at all; the clause was extraneous and directly caused the reported behavior of streaks resetting specifically on Sundays.

**My fix and side-effect check**

Removed the `and today.weekday() != 6` clause, leaving `elif days_since_last == 1:` as the sole condition for incrementing the streak — this is the minimal change that aligns the code with the documented streak rules (increment on any true one-day gap, regardless of weekday).

To check for side effects, I ran the full `tests/test_streaks.py` suite: all 5 tests passed, including `test_streak_increments_on_sunday` (the boundary case this fix targets) and `test_streak_resets_after_skipped_day` (confirming genuine gaps still reset correctly — the other side of the boundary). I also re-ran `Reproduce_Bugs/repro_sunday_bug.py`, which now shows the streak going from 12 → 13 on a Saturday-to-Sunday listen instead of resetting to 1. Finally, I ran `tests/test_playlists.py` and `tests/test_search.py` to confirm this change didn't touch unrelated functionality — the only failures there are the pre-existing, out-of-scope playlist-slicing bug, unaffected by this fix.

### Bug #2: Friends Listening Now shows people from yesterday

**How I reproduced it**

1. Examined [feed_service.py](services/feed_service.py) and saw `RECENT_THRESHOLD` is set to `timedelta(hours=24)` ([feed_service.py:13](services/feed_service.py#L13)). This confirms that anyone who listened within the last 24 hours will show up in the "Listening Now" feed, regardless of whether that falls on the current calendar day.
2. Ran `python seed_data.py` against a fresh SQLite DB, then queried it directly to inspect real seeded state: user IDs, friendships, and every `ListeningEvent.listened_at` timestamp.
3. Started the real Flask server (`python app.py`) and looked at darius's feed, since his friends are nova and simone:
   ```
   GET http://127.0.0.1:5000/feed/cc240019-ba47-427b-9d3a-8804f45be116/listening-now
   ```
4. **Data condition**: seed data gives darius's friends listening events spaced across the last ~24+ hours (e.g. nova ~17:04, simone ~18:49 relative to seed time, plus older events further back).
5. **Result**: the API returned both nova and simone as "listening now," including entries that were many hours old but still inside the 24-hour rolling window — confirming that a listen from the previous evening survives into the next morning's "Listening Now" feed, exactly matching the user's report about darius appearing with his 11pm listen still showing at 9am.
6. **Trigger condition**: any `ListeningEvent.listened_at >= datetime.now(UTC) - timedelta(hours=24)` qualifies — there is no check against the start of the current calendar day, so events from "yesterday evening" remain visible until a full 24 hours have elapsed, not until midnight.
7. **Root cause located**: [services/feed_service.py:13,32](services/feed_service.py#L13) — `RECENT_THRESHOLD = timedelta(hours=24)` implements a rolling window rather than "since local midnight" / "today," which is what "Listening Now" implies to users. The code behaves exactly as written; the mismatch is between this implementation and user-facing semantics of "today."

**How I found the root cause**

Started at [services/feed_service.py](services/feed_service.py) since `GET /feed/<user_id>/listening-now` is the only route that produces this feed, and it delegates entirely to `get_friends_listening_now()`. Read the function top-down: it computes `cutoff = datetime.now(timezone.utc) - RECENT_THRESHOLD` and filters `ListeningEvent.listened_at >= cutoff` — a single comparison, so there was nowhere else the "yesterday's listen still shows" behavior could be coming from. The moment of confidence came from re-reading `RECENT_THRESHOLD = timedelta(hours=24)` at the top of the file next to the docstring's use of the word "recently" — the code implements "within the last 24 hours" (a rolling window anchored to the exact call time), not "today" (anchored to local midnight). Those are different windows that happen to overlap most of the day, which is why the bug only shows up near the day boundary — exactly the "9am the morning after an 11pm listen" scenario reported. I confirmed this wasn't a red herring by reproducing it against real seeded data (`seed_data.py` creates events 17-26 hours old specifically to exercise this boundary) and watching them appear in `GET /feed/<user_id>/listening-now`.

**The root cause**

`get_friends_listening_now()` computed its recency cutoff as `datetime.now(timezone.utc) - timedelta(hours=24)` ([services/feed_service.py:32](services/feed_service.py#L32)), a rolling 24-hour window measured from the exact moment of the request. "Listening Now" is meant to convey "today," which users interpret as since local/calendar midnight — a boundary that resets once per day, not one that continuously slides forward. Because the cutoff never anchors to the start of a calendar day, any listen from up to 24 hours ago — including one from late the previous evening — still satisfies `listened_at >= cutoff` well into the next morning, which is exactly the reported symptom.

**My fix and side-effect check**

Changed the cutoff in [services/feed_service.py:32](services/feed_service.py#L32) from a rolling 24-hour window to the start of the current UTC calendar day:

```python
now = datetime.now(timezone.utc)
cutoff = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
```

This is the minimal change needed — it only touches how `cutoff` is computed, leaving the query, dedup logic, and `get_activity_feed()` (which doesn't use this cutoff at all) untouched.

To check for side effects, I re-ran `Reproduce_Bugs/repro_stale_listening_now.py`: darius's 11pm-last-night listen, checked at a simulated 9am, now correctly returns `count: 0` instead of showing him as "listening now." I also wrote and ran a same-day boundary check — a listen at 1am today, checked at 9am the same day — which still correctly returns `count: 1`, confirming the fix only excludes listens from before today, not all older listens within the day. Finally, I ran the full test suite (`tests/test_streaks.py`, `tests/test_search.py`, `tests/test_playlists.py`); the only failures are the same 2 pre-existing, out-of-scope playlist-slicing test failures seen before this fix — no new regressions.

### Bug #4 — I got notified when a friend added my song to a playlist but not when they rated it

**How I reproduced it**

1. Examined [notification_service.py](services/notification_service.py) and compared `add_to_playlist()` ([notification_service.py:35-70](services/notification_service.py#L35-L70)) against `rate_song()` ([notification_service.py:73-110](services/notification_service.py#L73-L110)). `add_to_playlist` explicitly calls `create_notification(user_id=song.shared_by, notification_type="song_added_to_playlist", ...)` when the adder isn't the original sharer. `rate_song` has no equivalent call anywhere in its body — it only validates the score, upserts the `Rating` row, and commits.
2. Ran `python seed_data.py` then `python app.py` against a real server, and pulled real IDs directly from the DB: a user who shared a song (nova) and a different user to act as the rater (darius).
3. **Data condition**: a song shared by nova (`shared_by = nova.id`), and darius is a different user than the sharer — the exact condition under which a notification should fire per the playlist pattern.
4. **Sequence of actions**:
   - Checked nova's notifications first: `GET /users/<nova_id>/notifications` → `{"count":1,...}` (only the pre-existing seed `song_added_to_playlist` notification).
   - Had darius rate nova's song: `POST /songs/<song_id>/rate` with `{"user_id": "<darius_id>", "score": 5}` → `201`, rating saved successfully (confirmed via response body).
   - Re-checked nova's notifications: `GET /users/<nova_id>/notifications` → still `{"count":1,...}`, byte-for-byte identical to before.
5. **Result**: the rating was persisted (verifiable via the song/rating data) but no new notification was created for nova, reproducing the report exactly — no delay, just nothing, and nothing shows up in `GET /users/<id>/notifications`.
6. **Trigger condition**: this fires on every rating submitted by a user other than the song's sharer — it's not a conditional/edge-case bug, `rate_song` simply never calls `create_notification` under any circumstance.
7. **Root cause located**: [services/notification_service.py:73-110](services/notification_service.py#L73-L110) — `rate_song()` is missing a `create_notification(...)` call entirely. This is a missing-feature gap rather than a broken condition; the fix is to add a notification call mirroring the playlist pattern (e.g. `notification_type="song_rated"`), guarded so a user rating their own song doesn't self-notify (`if song.shared_by != user_id`).

**How I found the root cause**

Started at [services/notification_service.py](services/notification_service.py) since it's the single file responsible for all notification creation, and both the working case (playlist adds) and broken case (ratings) live in it side by side. Read `add_to_playlist()` first since it's the known-working reference pattern the codebase map calls out: it does the mutation (append song to playlist), commits, then conditionally calls `create_notification(user_id=song.shared_by, ...)` guarded by `if song.shared_by != added_by_user_id`. Read `rate_song()` immediately after with that pattern fresh in mind — it does the mutation (upsert `Rating`), commits, and returns. There is no third step. The moment of confidence was structural, not speculative: `rate_song()` never references `create_notification` anywhere in its body, and grepping the file confirmed `create_notification` is called from exactly one place (`add_to_playlist`). This isn't a broken condition I had to trace through several branches to find — the call is simply absent, so there's no deeper "why" to chase beyond confirming no other code path notifies on rating (checked [routes/songs.py](routes/songs.py)'s `POST /<song_id>/rate` route, which calls `rate_song` directly and does nothing else).

**The root cause**

`rate_song()` in [services/notification_service.py:73-110](services/notification_service.py#L73-L110) persists the `Rating` row (insert or update) and commits, but never calls `create_notification()` for the song's original sharer. This is unlike `add_to_playlist()`, which explicitly notifies `song.shared_by` after a successful playlist add. There's no missing condition or off-by-one check to fix — the notification step for ratings was simply never implemented, so ratings are saved successfully but silently produce zero notifications for anyone, regardless of who rates or how many times.

**My fix and side-effect check**

Added a `create_notification(...)` call at the end of `rate_song()`, after the commit, guarded by `if song.shared_by != user_id` so a user rating their own shared song doesn't notify themselves — mirroring the exact guard pattern used in `add_to_playlist()`:

```python
if song.shared_by != user_id:
    create_notification(
        user_id=song.shared_by,
        notification_type="song_rated",
        body=f"{rater.username} rated your song '{song.title}' {score} stars.",
    )
```

To check for side effects, I re-ran `Reproduce_Bugs/repro_missing_rating_notification.py`: notification count went from 0 to 1 with the correct `song_rated` body after a friend rates a shared song. I also checked two boundary cases not covered by the original report: (1) a user rating their own song produces `count: 0` — no self-notification, confirming the guard works; (2) a friend updating an existing rating (rating the same song twice with different scores) still produces a notification each time, since the notification call is unconditional on the save path, not tied to "first rating only." Finally, I ran the full test suite (`tests/test_streaks.py`, `tests/test_search.py`, `tests/test_playlists.py`); the only failures are the same 2 pre-existing, out-of-scope playlist-slicing test failures seen before this fix — no new regressions, and nothing in the test suite exercises notifications directly so none were at risk of breaking.

