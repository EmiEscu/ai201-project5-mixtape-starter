"""
repro_missing_rating_notification.py

Reproduces the missing rating-notification bug (Bug #4) exactly as a real user
would experience it: via the real Flask app, real HTTP-style requests (test client).

Run: python repro_missing_rating_notification.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, db
from models import User, Song

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    # --- Set up "me" (the sharer) and "friend" (the rater) ---
    me = User(username="me", email="me@mixtape.app")
    friend = User(username="friend", email="friend@mixtape.app")
    song = Song(title="Test Song", artist="Test Artist", shared_by=None)
    db.session.add_all([me, friend])
    db.session.flush()
    song.shared_by = me.id
    db.session.add(song)
    db.session.commit()

    print(f"my_id = {me.id}")
    print(f"friend_id = {friend.id}")
    print(f"song_id = {song.id}")

    client = app.test_client()

    resp = client.get(f"/users/{me.id}/notifications")
    print(f"\nBefore rating -> GET /users/{me.id}/notifications -> {resp.status_code}")
    print(resp.get_json())

    resp = client.post(
        f"/songs/{song.id}/rate",
        json={"user_id": friend.id, "score": 5},
    )
    print(f"\nPOST /songs/{song.id}/rate -> {resp.status_code}")
    print(resp.get_json())

    resp = client.get(f"/users/{me.id}/notifications")
    print(f"\nAfter rating -> GET /users/{me.id}/notifications -> {resp.status_code}")
    print(resp.get_json())

    print("\nExpected: count == 1, a notification about the rating.")
    
