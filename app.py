"""WSGI entry point (used by `flask run` locally and gunicorn in the container)."""
from dotenv import load_dotenv

load_dotenv()  # loads FLASK_SECRET_KEY and other config from a local .env file, if present

from webapp import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
