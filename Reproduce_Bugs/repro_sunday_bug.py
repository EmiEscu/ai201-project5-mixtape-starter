"""
repro_sunday_bug.py

Reproduces the Sunday streak-reset bug exactly as a real user would experience it:
via the real Flask app, real HTTP-style requests (test client), against a picked user.

Run: python repro_sunday_bug.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, db
from models import User, Song

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    # --- Set up "me": a user with a 12-day streak, who listened yesterday (Saturday) ---
    me = User(username="me", email="me@mixtape.app", listening_streak=12)
    song = Song(title="Test Song", artist="Test Artist", shared_by=None)
    db.session.add(me)
    db.session.flush()
    song.shared_by = me.id
    db.session.add(song)
    db.session.commit()

    saturday = datetime(2024, 6, 15, 22, 0, 0, tzinfo=timezone.utc)  # Saturday night
    sunday_morning = datetime(2024, 6, 16, 9, 0, 0, tzinfo=timezone.utc)  # Sunday morning

    me.last_listened_at = saturday
    db.session.commit()

    print(f"my_id = {me.id}")
    print(f"song_id = {song.id}")
    print(f"Before Sunday listen -> streak = {me.listening_streak}")

    client = app.test_client()

    # Simulate listening on Sunday morning by freezing "now" inside streak_service
    with patch("services.streak_service.datetime") as mock_dt:
        mock_dt.now.return_value = sunday_morning
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        resp = client.post(
            f"/songs/{song.id}/listen",
            json={"user_id": me.id},
        )
        print(f"\nPOST /songs/{song.id}/listen -> {resp.status_code}")
        print(resp.get_json())

    resp = client.get(f"/users/{me.id}/streak")
    print(f"\nGET /users/{me.id}/streak -> {resp.status_code}")
    print(resp.get_json())
    print("\nExpected: 13. Actual: bug resets it to 1 because today.weekday() == 6 (Sunday).")
