"""
repro_stale_listening_now.py

Reproduces the "Friends Listening Now shows yesterday's listens" bug
exactly as a real user would experience it: via the real Flask app,
real HTTP-style requests (test client).

Run: python repro_stale_listening_now.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, db
from models import User, Song, ListeningEvent, friendships

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    # --- Set up "me" and "darius" as friends ---
    me = User(username="me", email="me@mixtape.app")
    darius = User(username="darius", email="darius@mixtape.app")
    song = Song(title="Late Night Vibes", artist="Some Artist", shared_by=None)
    db.session.add_all([me, darius])
    db.session.flush()
    song.shared_by = darius.id
    db.session.add(song)
    db.session.flush()

    db.session.execute(friendships.insert().values(user_id=me.id, friend_id=darius.id))
    db.session.execute(friendships.insert().values(user_id=darius.id, friend_id=me.id))
    db.session.commit()

    # darius listened at 11pm last night; he hasn't opened the app since
    last_night = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
    event = ListeningEvent(user_id=darius.id, song_id=song.id, listened_at=last_night)
    db.session.add(event)
    db.session.commit()

    print(f"my_id = {me.id}")
    print(f"darius_id = {darius.id}")
    print(f"darius listened_at = {last_night.isoformat()} (11pm last night)")

    # It's now 9am the next morning — only 10 hours later, still within the 24h window
    next_morning = last_night + timedelta(hours=10)
    print(f"\nSimulated 'now' = {next_morning.isoformat()} (9am the next morning)\n")

    client = app.test_client()

    with patch("services.feed_service.datetime") as mock_dt:
        mock_dt.now.return_value = next_morning
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        resp = client.get(f"/feed/{me.id}/listening-now")
        print(f"GET /feed/{me.id}/listening-now -> {resp.status_code}")
        print(resp.get_json())

