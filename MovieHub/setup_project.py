import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ensure_dependencies():
    venv_dir = ROOT / ".venv"
    venv_python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_python.exists():
        print("Creating local virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    subprocess.check_call([str(venv_python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    return venv_python


def seed_database():
    from app import Movie, app, db
    with app.app_context():
        db.create_all()
        if Movie.query.count():
            print("Database already contains movies; keeping existing catalog.")
            return
        samples = [
            Movie(title="Neon Monsoon", description="A sound designer returns to Kochi and finds an unfinished melody hiding a family secret.", language="Malayalam", genre="Drama / Mystery", year=2025, release_date=date(2025, 8, 15), rating=8.4, duration="2h 06m", cast="Maya Krishnan, Arjun Dev", poster="poster-neon-monsoon.svg", trailer="", video_480="", video_720="", video_1080="", featured=True),
            Movie(title="Paper Lanterns", description="Two night-shift strangers map the quiet corners of Chennai while chasing a second chance.", language="Tamil", genre="Romance / Drama", year=2025, release_date=date(2025, 7, 4), rating=8.1, duration="1h 54m", cast="Nila Rao, Kavin Surya", poster="poster-paper-lanterns.svg", featured=True),
            Movie(title="The Last Frequency", description="An independent radio host receives a transmission that may prevent a city-wide blackout.", language="Hindi", genre="Thriller", year=2024, release_date=date(2024, 11, 22), rating=8.7, duration="2h 12m", cast="Aarav Mehta, Sana Kapoor", poster="poster-last-frequency.svg"),
            Movie(title="Low Tide Club", description="A crew of amateur sailors races the clock to save their disappearing coastal clubhouse.", language="English", genre="Adventure / Comedy", year=2024, release_date=date(2024, 9, 13), rating=7.9, duration="1h 48m", cast="June Ellis, Theo Grant", poster="poster-low-tide.svg"),
            Movie(title="Blue Hour", description="A photographer follows a trail of blue lights through a city that never sleeps.", language="Malayalam", genre="Crime / Drama", year=2023, release_date=date(2023, 5, 19), rating=7.8, duration="2h 01m", cast="Dev Menon, Anika Paul", poster="poster-blue-hour.svg"),
            Movie(title="Monsoon Postcard", description="A joyful road trip becomes a tender portrait of friendship and homecoming.", language="Tamil", genre="Feel-good", year=2023, release_date=date(2023, 6, 30), rating=7.6, duration="1h 42m", cast="Rishi Anand, Tara Iyer", poster="poster-monsoon-postcard.svg"),
            Movie(title="Signal Fires", description="A mountain rescue team deciphers a string of impossible signals after sundown.", language="Hindi", genre="Mystery", year=2022, release_date=date(2022, 10, 7), rating=7.5, duration="1h 50m", cast="Kabir Joshi, Meera Shah", poster="poster-signal-fires.svg"),
            Movie(title="Glass Atlas", description="A cartographer builds a map of places that only appear in dreams.", language="English", genre="Fantasy / Drama", year=2022, release_date=date(2022, 3, 18), rating=8.0, duration="2h 08m", cast="Wren Cole, Malik Stone", poster="poster-glass-atlas.svg"),
        ]
        db.session.add_all(samples)
        db.session.commit()
        print(f"Added {len(samples)} fictional sample movies.")


if __name__ == "__main__":
    print("Preparing MovieHub...")
    for folder in ("templates/admin", "static/css", "static/js", "static/images", "static/videos"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    venv_python = ensure_dependencies()
    if sys.prefix == sys.base_prefix:
        subprocess.check_call([str(venv_python), str(Path(__file__).resolve()), "--ready"])
        sys.exit(0)
    seed_database()
    print("MovieHub is ready. Run: python run.py")
