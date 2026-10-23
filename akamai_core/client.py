"""Thin, exception-safe wrapper around the internal AkamaiRequests client.

AkamaiRequests.get_request/post_request/put_request raise bare SystemExit on
timeouts or network errors. In a background worker thread that would cause the
thread to silently die (threading swallows SystemExit) without the job ever
reporting a failure, so every call here is caught and re-raised as
PapiRequestError instead.
"""
import time
import urllib.parse

from .errors import PapiRequestError

# post_request/put_request never retry on timeout (unlike get_request), so do a single
# retry here too -- activations occasionally take longer than the request timeout to
# respond even though they went through, and a retry is safe since Akamai treats an
# already-in-flight activation request as a no-op ("already being activated").
_WRITE_RETRY_DELAY_SECONDS = 15


class PapiClient:
    def __init__(self, api_caller):
        self._api = api_caller

    @staticmethod
    def _build_url(endpoint, params):
        # Drop empty params (e.g. no account switch key selected yet) instead of sending them blank.
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        return f"{endpoint}?{query_string}" if query_string else endpoint

    def _call(self, method, endpoint, params, body=None):
        url = self._build_url(endpoint, params)
        self._api.set_request_url(url, apply_switchkey=False)
        if body is not None:
            self._api.set_request_body(body)
        for attempt in range(2):
            try:
                if method == "get":
                    self._api.get_request(0)
                elif method == "post":
                    self._api.post_request()
                elif method == "put":
                    self._api.put_request()
                break
            except SystemExit as exc:
                if method in ("post", "put") and attempt == 0:
                    time.sleep(_WRITE_RETRY_DELAY_SECONDS)
                    continue
                raise PapiRequestError(f"{method.upper()} {endpoint} failed (network/timeout error)") from exc

        res = self._api.get_response_body()
        return res if isinstance(res, dict) else {"error_raw": str(res)}

    def get(self, endpoint, params):
        return self._call("get", endpoint, params)

    def post(self, endpoint, body, account_switch_key):
        return self._call("post", endpoint, {"accountSwitchKey": account_switch_key}, body)

    def post_with_params(self, endpoint, body, params):
        return self._call("post", endpoint, params, body)

    def put(self, endpoint, body, params):
        return self._call("put", endpoint, params, body)
