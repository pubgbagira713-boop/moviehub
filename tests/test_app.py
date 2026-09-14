from io import BytesIO
from pathlib import Path

import pytest

from app import Movie, create_app, db


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })
    with app.test_client() as test_client:
        yield test_client


def login(client):
    return client.post("/admin/login", data={"username": "Baghira", "password": "MovieHub@010"}, follow_redirects=True)


def test_homepage_has_seeded_movies(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Avengers: Endgame" in response.data
    assert b"MovieHub" in response.data


def test_search_and_detail(client):
    response = client.get("/search?q=Iron+Man")
    assert b"Iron Man" in response.data
    with client.application.app_context():
        movie = Movie.query.filter_by(title="Iron Man").first()
        movie_id = movie.id
    assert client.get(f"/movie/{movie_id}").status_code == 200


def test_admin_crud(client):
    assert client.get("/admin").status_code == 302
    response = login(client)
    assert b"Catalog overview" in response.data
    response = client.post("/admin/movies/new", data={"title": "Test Film", "description": "A test."}, follow_redirects=True)
    assert b"Test Film" in response.data
    with client.application.app_context():
        movie = Movie.query.filter_by(title="Test Film").first()
        movie_id = movie.id
    response = client.post(f"/admin/movies/{movie_id}/edit", data={"title": "Updated Film"}, follow_redirects=True)
    assert b"Updated Film" in response.data
    response = client.post(f"/admin/movies/{movie_id}/delete", follow_redirects=True)
    assert b"Updated Film" not in response.data


def test_metadata_requires_auth_and_returns_known_suggestion(client):
    assert client.get("/admin/metadata?title=Thor").status_code == 302
    login(client)
    response = client.get("/admin/metadata?title=Thor")
    assert response.json["found"] is True
    assert response.json["metadata"]["release_year"] == "2011"


def test_poster_upload_and_youtube_embed(client, tmp_path):
    login(client)
    response = client.post("/admin/movies/new", data={
        "title": "Uploaded Poster Film",
        "trailer_url": "https://youtu.be/dQw4w9WgXcQ",
        "poster_file": (BytesIO(b"small-poster"), "My Poster!.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    with client.application.app_context():
        movie = Movie.query.filter_by(title="Uploaded Poster Film").first()
        assert movie.poster_url.startswith("uploads/posters/")
        assert (Path(client.application.config["UPLOAD_FOLDER"]) / Path(movie.poster_url).name).exists()
        assert movie.youtube_embed_url() == "https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&mute=1&rel=0"
        movie_id = movie.id
    detail = client.get(f"/movie/{movie_id}")
    assert b"autoplay=1&amp;mute=1" in detail.data


def test_homepage_includes_discovery_rows(client):
    response = client.get("/")
    assert b"Malayalam Picks" in response.data
    assert b"Highly Rated" in response.data
