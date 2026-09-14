import os
import re
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename


db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "moviehub-local-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///moviehub.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(app.static_folder, "uploads", "posters"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.context_processor
    def inject_year():
        def poster_src(poster):
            if not poster:
                return ""
            if poster.startswith(("http://", "https://", "/")):
                return poster
            return url_for("static", filename=poster)

        return {"current_year": datetime.utcnow().year, "poster_src": poster_src}

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_authenticated"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    @app.route("/")
    def index():
        movies = Movie.query.order_by(Movie.created_at.desc()).all()
        featured = movies[:6]
        return render_template("home.html", movies=movies, featured=featured, query="", sections=discovery_sections(movies))

    @app.route("/search")
    def search():
        query = request.args.get("q", "").strip()
        if query:
            needle = f"%{query}%"
            movies = Movie.query.filter(
                db.or_(
                    Movie.title.ilike(needle),
                    Movie.language.ilike(needle),
                    Movie.category.ilike(needle),
                    Movie.genre.ilike(needle),
                )
            ).order_by(Movie.title).all()
        else:
            movies = Movie.query.order_by(Movie.created_at.desc()).all()
        return render_template("home.html", movies=movies, featured=movies[:6], query=query, sections=[])

    @app.route("/movie/<int:movie_id>")
    def movie_detail(movie_id):
        movie = db.get_or_404(Movie, movie_id)
        return render_template("movie_detail.html", movie=movie, trailer_embed=movie.youtube_embed_url())

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == "Baghira" and password == "MovieHub@010":
                session["admin_authenticated"] = True
                return redirect(request.args.get("next") or url_for("admin_dashboard"))
            flash("The username or password is incorrect.", "error")
        return render_template("admin_login.html")

    @app.post("/admin/logout")
    def admin_logout():
        session.pop("admin_authenticated", None)
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        movies = Movie.query.order_by(Movie.updated_at.desc()).all()
        return render_template("admin_dashboard.html", movies=movies)

    @app.route("/admin/movies/new", methods=["GET", "POST"])
    @admin_required
    def admin_movie_new():
        movie = Movie()
        if request.method == "POST":
            save_movie(movie)
            flash("Movie added to the catalog.", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_movie_form.html", movie=movie, is_new=True)

    @app.route("/admin/movies/<int:movie_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_movie_edit(movie_id):
        movie = db.get_or_404(Movie, movie_id)
        if request.method == "POST":
            save_movie(movie)
            flash("Movie changes saved.", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_movie_form.html", movie=movie, is_new=False)

    @app.post("/admin/movies/<int:movie_id>/delete")
    @admin_required
    def admin_movie_delete(movie_id):
        movie = db.get_or_404(Movie, movie_id)
        db.session.delete(movie)
        db.session.commit()
        flash("Movie removed from the catalog.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/metadata")
    @admin_required
    def generate_metadata():
        title = request.args.get("title", "").strip().lower()
        suggestion = METADATA_SUGGESTIONS.get(title)
        if not suggestion:
            return jsonify({"found": False, "message": "No verified local suggestion for this title. Fill the fields manually."})
        return jsonify({"found": True, "metadata": suggestion})

    with app.app_context():
        Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
        db.create_all()
        if Movie.query.count() == 0:
            db.session.add_all(seed_movies())
            db.session.commit()

    return app


ALLOWED_POSTER_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def save_movie(movie):
    movie.title = request.form.get("title", "").strip()
    movie.description = request.form.get("description", "").strip()
    movie.rating = request.form.get("rating", "").strip()
    movie.release_year = request.form.get("release_year", "").strip()
    movie.duration = request.form.get("duration", "").strip()
    movie.language = request.form.get("language", "").strip()
    movie.category = request.form.get("category", "").strip()
    movie.genre = request.form.get("genre", "").strip()
    movie.cast = request.form.get("cast", "").strip()
    movie.director = request.form.get("director", "").strip()
    poster_url = request.form.get("poster_url", "").strip()
    poster_file = request.files.get("poster_file")
    if poster_file and poster_file.filename:
        extension = Path(poster_file.filename).suffix.lower().lstrip(".")
        if extension not in ALLOWED_POSTER_EXTENSIONS:
            raise ValueError("Poster must be a JPG, PNG, or WebP image")
        safe_stem = secure_filename(Path(poster_file.filename).stem) or "poster"
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_stem}.{extension}"
        poster_file.save(os.path.join(current_upload_folder(), filename))
        movie.poster_url = f"uploads/posters/{filename}"
    else:
        movie.poster_url = poster_url
    movie.trailer_url = request.form.get("trailer_url", "").strip()
    movie.download_4k_url = request.form.get("download_4k_url", "").strip()
    movie.download_1080p_url = request.form.get("download_1080p_url", "").strip()
    movie.download_720p_url = request.form.get("download_720p_url", "").strip()
    movie.download_480p_url = request.form.get("download_480p_url", "").strip()
    if not movie.title:
        raise ValueError("Movie title is required")
    db.session.add(movie)
    db.session.commit()


def current_upload_folder():
    return current_app.config["UPLOAD_FOLDER"]


def discovery_sections(movies):
    def newest(items):
        return sorted(items, key=lambda movie: movie.created_at or datetime.min, reverse=True)[:10]

    def rated(items):
        return sorted(items, key=lambda movie: float(movie.rating or 0), reverse=True)[:10]

    return [
        ("Top Releases", rated(movies)),
        ("Trending Now", movies[:10]),
        ("Latest Movies", newest(movies)),
        ("Popular Movies", rated(movies)),
        ("Malayalam Picks", [movie for movie in movies if movie.language.lower() == "malayalam"]),
        ("Hindi Picks", [movie for movie in movies if movie.language.lower() == "hindi"]),
        ("English Picks", [movie for movie in movies if movie.language.lower() == "english"]),
        ("Animation Picks", [movie for movie in movies if movie.category.lower() in {"anime", "animation"}]),
        ("Highly Rated", [movie for movie in rated(movies) if float(movie.rating or 0) >= 8]),
        ("Recommended for You", newest(movies)),
    ]


class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    rating = db.Column(db.String(20), default="")
    release_year = db.Column(db.String(10), default="")
    duration = db.Column(db.String(40), default="")
    language = db.Column(db.String(80), default="")
    category = db.Column(db.String(80), default="")
    genre = db.Column(db.String(180), default="")
    cast = db.Column(db.Text, default="")
    director = db.Column(db.String(180), default="")
    poster_url = db.Column(db.Text, default="")
    trailer_url = db.Column(db.Text, default="")
    download_4k_url = db.Column(db.Text, default="")
    download_1080p_url = db.Column(db.Text, default="")
    download_720p_url = db.Column(db.Text, default="")
    download_480p_url = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def youtube_embed_url(self):
        if not self.trailer_url:
            return None
        parsed = urlparse(self.trailer_url)
        video_id = ""
        if parsed.hostname in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/")
        elif parsed.hostname and "youtube.com" in parsed.hostname:
            if parsed.path == "/watch":
                from urllib.parse import parse_qs
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif parsed.path.startswith("/embed/") or parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/")[2]
        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
            return f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&rel=0"
        return None


POSTERS = [
    "https://images.unsplash.com/photo-1489599849927-2ee91abba3ba?auto=format&fit=crop&w=900&q=85",
    "https://images.unsplash.com/photo-1518676590629-3dcbd9c5a5c9?auto=format&fit=crop&w=900&q=85",
    "https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=900&q=85",
    "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=900&q=85",
    "https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?auto=format&fit=crop&w=900&q=85",
    "https://images.unsplash.com/photo-1535016120720-40c646be5580?auto=format&fit=crop&w=900&q=85",
]


def movie_data(title, description, rating, year, duration, language, category, genre, cast, director, poster_index):
    return Movie(title=title, description=description, rating=rating, release_year=year, duration=duration,
                 language=language, category=category, genre=genre, cast=cast, director=director,
                 poster_url=POSTERS[poster_index % len(POSTERS)])


def seed_movies():
    return [
        movie_data("Avengers: Endgame", "The surviving heroes gather for one final attempt to undo a universe-changing loss.", "8.4", "2019", "3h 1m", "English", "Movie", "Action, Adventure, Sci-Fi", "Robert Downey Jr., Chris Evans, Scarlett Johansson", "Anthony Russo, Joe Russo", 0),
        movie_data("Avengers: Infinity War", "The Avengers and their allies race across worlds as an unstoppable cosmic threat closes in.", "8.4", "2018", "2h 29m", "English", "Movie", "Action, Adventure, Sci-Fi", "Robert Downey Jr., Chris Hemsworth, Josh Brolin", "Anthony Russo, Joe Russo", 1),
        movie_data("Thor", "A proud heir to a distant realm is sent to Earth, where humility becomes his greatest strength.", "7.0", "2011", "1h 55m", "English", "Movie", "Action, Adventure, Fantasy", "Chris Hemsworth, Natalie Portman, Tom Hiddleston", "Kenneth Branagh", 2),
        movie_data("Iron Man", "A brilliant inventor rebuilds his life and his purpose inside a remarkable suit of his own design.", "7.9", "2008", "2h 6m", "English", "Movie", "Action, Adventure, Sci-Fi", "Robert Downey Jr., Gwyneth Paltrow, Jeff Bridges", "Jon Favreau", 3),
        movie_data("English Vinglish", "A quiet homemaker discovers a new confidence when an unexpected journey nudges her beyond familiar limits.", "7.8", "2012", "2h 14m", "Hindi", "Movie", "Comedy, Drama, Family", "Sridevi, Adil Hussain, Mehdi Nebbou", "Gauri Shinde", 4),
        movie_data("Barfi!", "A warm-hearted tale of mischief, friendship, and love told through a man who refuses to let life become ordinary.", "8.1", "2012", "2h 31m", "Hindi", "Movie", "Comedy, Drama, Romance", "Ranbir Kapoor, Priyanka Chopra, Ileana D'Cruz", "Anurag Basu", 5),
        movie_data("Vicky Donor", "A playful romance grows around an unusual profession, family expectations, and a surprisingly big heart.", "7.8", "2012", "2h 6m", "Hindi", "Movie", "Comedy, Romance", "Ayushmann Khurrana, Yami Gautam, Annu Kapoor", "Shoojit Sircar", 0),
        movie_data("Yeh Jawaani Hai Deewani", "Four friends reunite and find that ambition, memory, and affection have all changed shape with time.", "7.2", "2013", "2h 40m", "Hindi", "Movie", "Drama, Romance", "Ranbir Kapoor, Deepika Padukone, Aditya Roy Kapur", "Ayan Mukerji", 1),
        movie_data("Tanu Weds Manu Returns", "A spirited reunion turns into a comic tangle of mistaken identities and second chances.", "7.6", "2015", "2h 8m", "Hindi", "Movie", "Comedy, Romance", "Kangana Ranaut, R. Madhavan, Jimmy Sheirgill", "Aanand L. Rai", 2),
        movie_data("Manjhi: The Mountain Man", "Driven by devotion and determination, a villager takes on a mountain with nothing but persistence.", "8.0", "2015", "2h", "Hindi", "Movie", "Biography, Drama", "Nawazuddin Siddiqui, Radhika Apte, Tigmanshu Dhulia", "Ketan Mehta", 3),
        movie_data("Biju Menon", "A gentle demo romance about two people finding an easy rhythm in an unexpectedly busy season of life.", "7.8", "2024", "1h 58m", "Malayalam", "Demo", "Romance, Feel-good", "Demo placeholder", "Demo placeholder", 4),
        movie_data("Dhanith", "A light-hearted demo comedy where friendship turns a string of small problems into a memorable adventure.", "8.0", "2024", "2h 2m", "Malayalam", "Demo", "Comedy, Friendship", "Demo placeholder", "Demo placeholder", 5),
        movie_data("Jassil", "An emotional demo family story about returning home, listening closely, and making room for a fresh beginning.", "8.2", "2024", "2h 10m", "Malayalam", "Demo", "Family, Emotional", "Demo placeholder", "Demo placeholder", 0),
        movie_data("Vaishnava", "A feel-good demo portrait of an optimistic young artist learning to trust her own pace.", "7.9", "2024", "1h 52m", "Malayalam", "Demo", "Drama, Feel-good", "Demo placeholder", "Demo placeholder", 1),
        movie_data("Demon Slayer", "A determined young swordsman enters a dangerous world of demons while protecting the family he has left.", "8.6", "2019", "24 min / episode", "Japanese", "Anime", "Action, Fantasy", "Natsuki Hanae, Akari Kito, Hiro Shimono", "Haruo Sotozaki", 2),
        movie_data("One Piece", "A fearless crew sails toward the ultimate treasure, building unlikely friendships across an enormous world.", "9.0", "1999", "24 min / episode", "Japanese", "Anime", "Adventure, Action, Fantasy", "Mayumi Tanaka, Kazuya Nakai, Akemi Okamura", "Kounosuke Uda", 3),
        movie_data("Bleach", "A teenager with an unexpected duty balances school life with the perilous work of protecting souls.", "8.2", "2004", "24 min / episode", "Japanese", "Anime", "Action, Adventure, Supernatural", "Masakazu Morita, Fumiko Orikasa, Hiroki Yasumoto", "Noriyuki Abe", 4),
        movie_data("Classroom of the Elite", "A gifted but guarded student navigates a ruthless academy where every advantage comes with a price.", "7.7", "2017", "24 min / episode", "Japanese", "Anime", "Drama, Psychological", "Shoya Chiba, Akari Kito, Yurika Kubo", "Seiji Kishi", 5),
    ]


METADATA_SUGGESTIONS = {
    "avengers: endgame": {"description": "The surviving heroes gather for one final attempt to undo a universe-changing loss.", "rating": "8.4", "release_year": "2019", "duration": "3h 1m", "language": "English", "category": "Movie", "genre": "Action, Adventure, Sci-Fi", "cast": "Robert Downey Jr., Chris Evans, Scarlett Johansson", "director": "Anthony Russo, Joe Russo"},
    "avengers: infinity war": {"description": "The Avengers and their allies race across worlds as an unstoppable cosmic threat closes in.", "rating": "8.4", "release_year": "2018", "duration": "2h 29m", "language": "English", "category": "Movie", "genre": "Action, Adventure, Sci-Fi", "cast": "Robert Downey Jr., Chris Hemsworth, Josh Brolin", "director": "Anthony Russo, Joe Russo"},
    "thor": {"description": "A proud heir to a distant realm is sent to Earth, where humility becomes his greatest strength.", "rating": "7.0", "release_year": "2011", "duration": "1h 55m", "language": "English", "category": "Movie", "genre": "Action, Adventure, Fantasy", "cast": "Chris Hemsworth, Natalie Portman, Tom Hiddleston", "director": "Kenneth Branagh"},
    "iron man": {"description": "A brilliant inventor rebuilds his life and his purpose inside a remarkable suit of his own design.", "rating": "7.9", "release_year": "2008", "duration": "2h 6m", "language": "English", "category": "Movie", "genre": "Action, Adventure, Sci-Fi", "cast": "Robert Downey Jr., Gwyneth Paltrow, Jeff Bridges", "director": "Jon Favreau"},
}


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
