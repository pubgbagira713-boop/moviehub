import os
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("MOVIEHUB_SECRET", "moviehub-development-key"),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{BASE_DIR / 'database.db'}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=str(BASE_DIR / "static" / "videos"),
    POSTER_FOLDER=str(BASE_DIR / "static" / "images"),
)
db = SQLAlchemy(app)


class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    language = db.Column(db.String(40), nullable=False)
    genre = db.Column(db.String(120), nullable=False, default="Drama")
    year = db.Column(db.Integer, nullable=False)
    release_date = db.Column(db.Date, nullable=True)
    rating = db.Column(db.Float, nullable=False, default=0)
    duration = db.Column(db.String(40), nullable=False, default="1h 45m")
    cast = db.Column(db.String(240), nullable=False, default="")
    poster = db.Column(db.String(240), nullable=False, default="poster-aurora.svg")
    trailer = db.Column(db.String(240), nullable=True)
    video_480 = db.Column(db.String(240), nullable=True)
    video_720 = db.Column(db.String(240), nullable=True)
    video_1080 = db.Column(db.String(240), nullable=True)
    featured = db.Column(db.Boolean, default=False)

    @property
    def poster_url(self):
        return url_for("static", filename=f"images/{self.poster}")

    @property
    def qualities(self):
        return [("1080p", self.video_1080), ("720p", self.video_720), ("480p", self.video_480)]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def movies_for(language=None):
    query = Movie.query
    if language:
        query = query.filter_by(language=language)
    return query.order_by(Movie.year.desc(), Movie.id.desc()).all()


@app.context_processor
def inject_globals():
    return {"languages": ["Malayalam", "Tamil", "Hindi", "English"]}


@app.route("/")
def index():
    all_movies = movies_for()
    return render_template(
        "index.html",
        featured=Movie.query.filter_by(featured=True).order_by(Movie.year.desc()).first(),
        latest=all_movies,
        released=all_movies[:6],
        trending=sorted(all_movies, key=lambda movie: movie.rating, reverse=True)[:6],
        language_movies={language: movies_for(language)[:6] for language in ["Malayalam", "Tamil", "Hindi", "English"]},
    )


@app.route("/<language>")
def language_page(language):
    normalized = language.capitalize()
    if normalized not in ["Malayalam", "Tamil", "Hindi", "English"]:
        abort(404)
    return render_template("language.html", language=normalized, movies=movies_for(normalized))


@app.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    movie = db.get_or_404(Movie, movie_id)
    return render_template("movie.html", movie=movie)


@app.route("/search")
def search():
    term = request.args.get("q", "").strip()
    movies = []
    if term:
        pattern = f"%{term}%"
        movies = Movie.query.filter(or_(Movie.title.ilike(pattern), Movie.language.ilike(pattern), Movie.genre.ilike(pattern), db.cast(Movie.year, db.String).ilike(pattern))).order_by(Movie.year.desc()).all()
    return render_template("search.html", movies=movies, term=term)


@app.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == os.environ.get("MOVIEHUB_ADMIN_PASSWORD", "moviehub-admin"):
            session["admin_authenticated"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("That administrator password was not accepted.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("index"))


def save_upload(file_storage, folder):
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    file_storage.save(Path(folder) / filename)
    return filename


def movie_from_form(movie=None):
    movie = movie or Movie()
    movie.title = request.form.get("title", "").strip()
    movie.description = request.form.get("description", "").strip()
    movie.language = request.form.get("language", "English")
    movie.genre = request.form.get("genre", "Drama").strip()
    movie.year = int(request.form.get("year", datetime.now().year))
    movie.release_date = datetime.strptime(request.form["release_date"], "%Y-%m-%d").date() if request.form.get("release_date") else None
    movie.rating = float(request.form.get("rating", 0) or 0)
    movie.duration = request.form.get("duration", "").strip()
    movie.cast = request.form.get("cast", "").strip()
    movie.featured = request.form.get("featured") == "on"
    poster = save_upload(request.files.get("poster"), app.config["POSTER_FOLDER"])
    if poster:
        movie.poster = poster
    for quality in ("480", "720", "1080"):
        uploaded = save_upload(request.files.get(f"video_{quality}"), app.config["UPLOAD_FOLDER"])
        if uploaded:
            setattr(movie, f"video_{quality}", uploaded)
    trailer = save_upload(request.files.get("trailer"), app.config["UPLOAD_FOLDER"])
    if trailer:
        movie.trailer = trailer
    return movie


@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin/dashboard.html", movies=Movie.query.order_by(Movie.id.desc()).all())


@app.route("/admin/movie/add", methods=["GET", "POST"])
@admin_required
def add_movie():
    if request.method == "POST":
        movie = movie_from_form()
        if not movie.title:
            flash("A movie title is required.", "error")
        else:
            db.session.add(movie)
            db.session.commit()
            flash("Movie added to the catalog.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin/add_movie.html", movie=None)


@app.route("/admin/movie/<int:movie_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_movie(movie_id):
    movie = db.get_or_404(Movie, movie_id)
    if request.method == "POST":
        movie_from_form(movie)
        db.session.commit()
        flash("Movie updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/edit_movie.html", movie=movie)


@app.post("/admin/movie/<int:movie_id>/delete")
@admin_required
def delete_movie(movie_id):
    movie = db.get_or_404(Movie, movie_id)
    db.session.delete(movie)
    db.session.commit()
    flash("Movie removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, title="Page not found", message="The page you requested has moved off-screen."), 404


@app.errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template("error.html", code=500, title="Something went wrong", message="The projector needs a moment. Please try again."), 500


with app.app_context():
    (BASE_DIR / "static" / "images").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "static" / "videos").mkdir(parents=True, exist_ok=True)
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
