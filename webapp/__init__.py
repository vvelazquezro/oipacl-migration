import logging
import os

from flask import Flask
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .creds import CredentialStore
from .jobs import JobManager
from .middleware import PrefixMiddleware

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(PrefixMiddleware(app.wsgi_app, prefix=app.config["APP_ROOT_PATH"]),
                             x_for=1, x_proto=1, x_host=1)
    csrf.init_app(app)

    app.job_manager = JobManager(max_workers=app.config["MAX_CONCURRENT_JOBS"])
    app.cred_store = CredentialStore(ttl_seconds=app.config["CREDENTIAL_TTL_SECONDS"])

    if not os.environ.get("FLASK_SECRET_KEY"):
        logging.warning("FLASK_SECRET_KEY not set; using an ephemeral key generated at startup.")

    from .routes import bp
    app.register_blueprint(bp)

    return app
