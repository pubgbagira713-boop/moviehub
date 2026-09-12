"""Authorized media import service.

This module only indexes filenames and stores references. It never uploads or copies
movie media to MovieHub.
"""
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

QUALITY_PATTERN = re.compile(r"(?P<quality>4k|480|720|1080)p?", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
IGNORED_TOKENS = {
    "web", "webdl", "web-dl", "webrip", "bluray", "blu-ray", "brrip", "dvdrip",
    "x264", "x265", "h264", "h265", "hevc", "aac", "ddp", "dd5", "atmos", "hdr",
    "10bit", "proper", "repack", "extended", "remastered", "multi", "dubbed",
}
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}


class MovieImporter:
    def __init__(self, app, db, movie_model, candidate_model):
        self.app = app
        self.db = db
        self.Movie = movie_model
        self.ImportCandidate = candidate_model

    def parse_filename(self, filename):
        path = Path(filename)
        stem = path.stem
        quality_match = QUALITY_PATTERN.search(stem)
        if not quality_match:
            return None
        year_match = YEAR_PATTERN.search(stem)
        raw_quality = quality_match.group("quality").lower()
        quality = "4k" if raw_quality == "4k" else f"{raw_quality}p"
        cutoff = min(
            [match.start() for match in (quality_match, year_match) if match]
        )
        raw_title = stem[:cutoff]
        tokens = [token for token in re.split(r"[._\-]+", raw_title) if token]
        title_tokens = [token for token in tokens if token.lower() not in IGNORED_TOKENS]
        title = " ".join(title_tokens).strip()
        return {"title": title or stem[:cutoff].strip(), "year": int(year_match.group()) if year_match else None, "quality": quality}

    def external_url(self, filename):
        base_url = self.app.config["EXTERNAL_MEDIA_BASE_URL"]
        if not base_url:
            return filename
        return f"{base_url}/{quote(filename)}"

    def scan(self):
        import_folder = Path(self.app.config["IMPORT_FOLDER"])
        import_folder.mkdir(parents=True, exist_ok=True)
        found = []
        for path in sorted(import_folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            parsed = self.parse_filename(path.name)
            if not parsed:
                continue
            candidate = self.ImportCandidate.query.filter_by(source_name=path.name).first()
            if candidate is None:
                candidate = self.ImportCandidate(source_name=path.name, external_url=self.external_url(path.name), **parsed)
                self.db.session.add(candidate)
            else:
                candidate.external_url = self.external_url(path.name)
                candidate.title, candidate.year, candidate.quality = parsed["title"], parsed["year"], parsed["quality"]
                if candidate.status == "skipped":
                    candidate.status = "pending"
            found.append(candidate)
        self.db.session.commit()
        return found

    def metadata_lookup(self, title, year=None):
        api_key = self.app.config["METADATA_API_KEY"]
        if not api_key:
            return None, "not_configured"
        params = f"api_key={quote(api_key)}&query={quote(title)}&include_adult=false&language=en-US"
        if year:
            params += f"&year={year}"
        try:
            search_url = f"https://api.themoviedb.org/3/search/movie?{params}"
            with urlopen(Request(search_url, headers={"User-Agent": "MovieHub-authorized-importer/1.0"}), timeout=8) as response:
                results = json.load(response).get("results", [])
            if not results:
                return None, "not_found"
            selected = results[0]
            details_url = f"https://api.themoviedb.org/3/movie/{selected['id']}?api_key={quote(api_key)}&append_to_response=credits&language=en-US"
            with urlopen(Request(details_url, headers={"User-Agent": "MovieHub-authorized-importer/1.0"}), timeout=8) as response:
                details = json.load(response)
            credits = details.get("credits", {})
            director = next((person["name"] for person in credits.get("crew", []) if person.get("job") == "Director"), "")
            cast = ", ".join(person["name"] for person in credits.get("cast", [])[:8])
            genres = ", ".join(genre["name"] for genre in details.get("genres", []))
            release_date = details.get("release_date") or ""
            return {
                "title": details.get("title") or title,
                "original_title": details.get("original_title"),
                "description": details.get("overview") or "",
                "year": int(release_date[:4]) if release_date[:4].isdigit() else year,
                "release_date": date.fromisoformat(release_date) if release_date else None,
                "poster": f"https://image.tmdb.org/t/p/w780{details['poster_path']}" if details.get("poster_path") else None,
                "backdrop": f"https://image.tmdb.org/t/p/w1280{details['backdrop_path']}" if details.get("backdrop_path") else None,
                "director": director,
                "cast": cast,
                "genre": genres or "Drama",
                "duration": f"{details['runtime']}m" if details.get("runtime") else "",
                "language": self.language_name(details.get("original_language")),
            }, "found"
        except Exception:
            return None, "unavailable"

    @staticmethod
    def language_name(code):
        return {"ml": "Malayalam", "ta": "Tamil", "hi": "Hindi", "en": "English"}.get(code, "English")

    def refresh_metadata(self, candidate):
        metadata, status = self.metadata_lookup(candidate.title, candidate.year)
        candidate.metadata_status = status
        self.db.session.commit()
        return metadata

    def import_candidate(self, candidate):
        metadata, status = self.metadata_lookup(candidate.title, candidate.year)
        movie = self.Movie.query.filter(self.db.func.lower(self.Movie.title) == candidate.title.lower()).first()
        created = movie is None
        if movie is None:
            movie = self.Movie(title=candidate.title, language="English", genre="Drama", year=candidate.year or 0, description="", duration="", cast="")
            self.db.session.add(movie)
        if metadata:
            for field in ("description", "language", "genre", "year", "release_date", "duration", "cast", "original_title", "backdrop", "director"):
                value = metadata.get(field)
                if value not in (None, ""):
                    setattr(movie, field, value)
            if metadata.get("poster"):
                movie.poster = metadata["poster"]
        if candidate.year and not movie.year:
            movie.year = candidate.year
        quality_column = "video_4k_url" if candidate.quality == "4k" else f"video_{candidate.quality[:-1]}_url"
        setattr(movie, quality_column, candidate.external_url)
        movie.metadata_status = status
        candidate.status = "imported"
        candidate.metadata_status = status
        self.db.session.commit()
        return movie, created
