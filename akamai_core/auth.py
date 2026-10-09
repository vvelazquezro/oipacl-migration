"""Builds an authenticated PapiClient from user-supplied credentials.

Credentials are never persisted: they are written to a private (0600) temp
file only for the lifetime of a single job and removed as soon as auth
completes (success or failure).
"""
import configparser
import contextlib
import os
import tempfile

from AkamaiRequests import AkamaiRequests

from .client import PapiClient

EDGERC_SECTION = "default"
REQUIRED_FIELDS = ("host", "client_token", "client_secret", "access_token")


def validate_credentials(creds: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not creds.get(f)]
    if missing:
        raise ValueError(f"Missing required Akamai credential field(s): {', '.join(missing)}")


@contextlib.contextmanager
def build_client(creds: dict):
    """Yields a PapiClient authenticated from `creds`. Cleans up the temp .edgerc on exit."""
    validate_credentials(creds)

    config = configparser.ConfigParser()
    config[EDGERC_SECTION] = {
        "host": creds["host"].strip(),
        "client_token": creds["client_token"].strip(),
        "client_secret": creds["client_secret"].strip(),
        "access_token": creds["access_token"].strip(),
    }

    fd, path = tempfile.mkstemp(prefix=".edgerc-", suffix=".tmp")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as fh:
            config.write(fh)

        api_caller = AkamaiRequests()
        api_caller.set_edgerc(path)
        api_caller.set_section(EDGERC_SECTION)
        api_caller.auth_api()

        yield PapiClient(api_caller)
    finally:
        if os.path.exists(path):
            os.remove(path)


@contextlib.contextmanager
def build_client_from_edgerc(path: str, section: str = EDGERC_SECTION):
    """Yields a PapiClient authenticated from an existing .edgerc file (CLI usage)."""
    api_caller = AkamaiRequests()
    api_caller.set_edgerc(os.path.expanduser(path))
    api_caller.set_section(section)
    api_caller.auth_api()
    yield PapiClient(api_caller)
