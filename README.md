# MovieHub

A small Flask + SQLite movie catalog with a protected admin area.

## Local setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Admin login: `/admin/login`.

For production, run `gunicorn app:app`.

The app stores metadata and external URLs only. Replace demo poster/trailer/download fields from the admin area with content you are authorized to distribute.
