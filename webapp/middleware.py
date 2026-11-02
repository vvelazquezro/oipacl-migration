"""WSGI middleware that makes the app work correctly when mounted under a sub-path.

Rewrites PATH_INFO/SCRIPT_NAME so Flask's own routing and `url_for` (including
the built-in static file endpoint) generate/accept URLs prefixed with
APP_ROOT_PATH, as required for reverse-proxied sub-path hosting.
"""

# GSAP's APL Workload probes hit the pod IP and container port directly, without the
# gateway's path prefix, so these must bypass prefix routing entirely.
UNPREFIXED_PATHS = {"/readyz", "/livez"}


class PrefixMiddleware:
    def __init__(self, wsgi_app, prefix: str = ""):
        self.wsgi_app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in UNPREFIXED_PATHS:
            return self.wsgi_app(environ, start_response)

        if not self.prefix:
            return self.wsgi_app(environ, start_response)

        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = self.prefix
            return self.wsgi_app(environ, start_response)

        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Not Found: this app is only served under " + self.prefix.encode()]
