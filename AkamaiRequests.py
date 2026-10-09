#!/usr/bin/env python3

"""
AKAMAI INTERNAL USE ONLY - DO NOT SHARE WITH CUSTOMERS.
THIS IS AN INTERNAL ONLY LIBRARY. DO NOT SHARE THIS WITH CUSTOMERS OR OTHER THIRD PARTIES. THERE ARE NO SLAS FOR THIS LIBRARY AND EXTERNAL USE WILL NOT RECEIVE ANY SUPPORT.

Akamai-oriented Python requests package for interfacing with Akamai APIs.

Designed to quickly get up to speed and allows users to focus on value-add
functionality rather than building the plumbing code from scratch.

Source hosted at https://git.source.akamai.com/projects/UNICORN/repos/akamairequests/browse

Last Updated: 01/26/2026
Author: celdon@akamai.com
"""

import datetime
import logging
from re import split
import time
from urllib.parse import urljoin

import requests
try:
    from requests_cache import CachedSession
    USE_CACHING = True
except ImportError:
    print('Unable to import module "requests_cache", please ensure this is installed to utilize requests caching.')
    USE_CACHING = False

from akamai.edgegrid import EdgeGridAuth, EdgeRc

# String Constants for logger processing
ERROR_DETAILS = "%s - Error Details: %s"
REQUEST_BODY = "%s - Request Body: %s"
TIMEOUT_ERROR = "%s - Timeout experienced while processing the request to %s."


class AkamaiRequests:
    """
    Class for interacting with Akamai APIs. Includes built-in rate limits
    for interactions with Akamai APIs.
    """

    # pylint: disable=too-many-instance-attributes
    # Attributes have been reviewed and validated as necessary

    def __init__(self, verbose: int = 0) -> None:
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.edgerc: EdgeRc
        self.baseurl: str
        self.url: str
        self.section: str = "default"
        if USE_CACHING:
            self.requests = CachedSession('~/akamai-requests-cache')
        else:
            self.requests = requests.Session()
        self.body: str
        self.request_result: requests.models.Response
        self.retry_request: bool = True
        self.version: str = "v0.3.2"

        if verbose == 1:
            self.verbose = True
        else:
            self.verbose = False

        if self.verbose is True:
            logging.basicConfig(
                filename="akamai_requests.log",
                level=logging.DEBUG)
        else:
            logging.basicConfig(
                filename="akamai_requests.log",
                level=logging.INFO)

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.info(
            "%s - Initialized akamai_requests class",
            current_time
        )
        self.logger.debug(
            "%s - Initialized akamai_requests class. Parameters: Verbose = %s",
            current_time,
            self.verbose,
        )

        self.set_switchkey("")
        self.set_request_url("", False)
        self.headers = {}
        self.add_request_header(
            "User-Agent",
            f"Akamai-GovServices-Requests/{self.version}/dl-govserv-civ@akamai.com",
        )
        self.request_data = ""

        # Requests never had a timeout before, so a slow/unresponsive API call
        # could hang a job forever; bound every call so Timeout can actually fire.
        self.request_timeout = 30

        # Limit the number of requests per minute to this value by default.
        # This can be overridden if the API endpoint supports it
        self.rate_limit = 50

        # The number of allowed requests remaining for the current minute.
        # This can be overridden if the API endpoint supports it
        self.rate_limit_remaining = 50

        # Capture the initial epoch time to be used to compare with the
        # current time. This will be used to reset the rateLimitRemaining
        # variable
        self.current_epoch_time = int(time.time())

        # Self-report the version of the class to compare against
        # a status check service
        try:
            if USE_CACHING:
                with self.requests.cache_disabled():
                    status_check = self.requests.get(
                        "https://govserv-script-status.akamaized.net"
                        "/akamai_requests/version.json",
                        headers=self.headers,
                        timeout=self.request_timeout,
                    )
            else:
                status_check = self.requests.get(
                    "https://govserv-script-status.akamaized.net"
                    "/akamai_requests/version.json",
                    headers=self.headers,
                    timeout=self.request_timeout,
                )

            if status_check.json()["latest_version"] != self.version:
                print(
                    "=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-\n"
                    "WARNING - "
                    "The current version of the AkamaiRequests Class "
                    f"({status_check.json()['latest_version']}) does "
                    f"not match this script's version ({self.version}). "
                    "Please update your script or contact the developer "
                    "to update.\n\n"
                    "Repo URL: https://git.source.akamai.com/projects/"
                    "UNICORN/repos/akamairequests/browse/"
                    "AkamaiRequests.py\n"
                    "=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-\n"
                )
        except:
            print(
                "=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-\n"
                "Unable to validate the script version. Please proceed "
                "with caution.\n"
                "=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-\n"
            )

    def set_edgerc(self, edgerc: str) -> None:
        """
        Defines location of .edgerc file

        :edgerc: Path to .edgerc file
        """

        self.edgerc = EdgeRc(edgerc)
        self.baseurl = f"https://{self.edgerc.get(self.section, 'host')}"

    def set_section(self, section: str) -> None:
        """
        Defines .edgerc section

        :param section: .edgerc section title
        """

        self.section = section

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.info(
            "%s - Edgerc Section set to %s",
            current_time,
            self.section
        )

    def set_switchkey(self, switchkey: str) -> None:
        """
        Defines account switchkey to use for requests

        :param switchkey: Account Switchkey for the account to manage
        """

        self.switchkey = switchkey

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.info(
            "%s - Account Switchkey set to %s", current_time, self.switchkey
        )

    def auth_api(self) -> None:
        """
        Prepares sessions interface for making requests
        """

        self.requests.auth = EdgeGridAuth.from_edgerc(
            self.edgerc,
            self.section
        )

    def set_request_url(self, url: str, apply_switchkey: bool = True) -> None:
        """
        Defines request URL for API calls

        :param url: URL to apply for the request
        :param apply_switchkey: Manage a specific account using a Switchkey
        """

        if apply_switchkey is True:
            if "?" in url:
                self.url = f"{url}&accountSwitchKey={self.switchkey}"
            else:
                self.url = f"{url}?accountSwitchKey={self.switchkey}"
        else:
            self.url = url

    def set_request_body(self, body) -> None:
        """
        Defines request body for API calls

        :param body: Request body to send in the request
        """
        self.body = body

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.debug(
            "%s - Request body set to %s",
            current_time,
            self.body
        )

    def get_request_headers(self) -> None:
        """
        Retrieves current set of request headers
        """
        print(self.headers)

    def add_request_header(self, header_name: str, header_value: str):
        """
        Add a request header to the header array. If duplicates are passed,
        it will overwrite existing entries with the new value.

        :param header_name: Name of the request header to add
        :param header_value: Value of the request header to add
        """
        self.headers[header_name] = header_value

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.debug(
            "%s - New Request Header added: %s = %s",
            current_time,
            header_name,
            header_value,
        )

    def remove_request_header(self, header_name: str) -> None:
        """
        Remove a request header from the header array.

        :param header_name: Name of the request header to remove
        """
        del self.headers[header_name]

        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.logger.debug("%s - Header removed: %s", current_time, header_name)

    def clear_request_cache(self) -> None:
        """
        Clears all of the requests cache
        """

        if USE_CACHING:
            self.requests.cache.clear()
        else:
            print("No Cache to clear, requests_cache module is not installed.")

    def check_rate_limit(self) -> None:
        """
        Check rate limit compared to max allowed limit
        """

        use_custom_rate_limits = False
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        current_epoch_time = time.time()

        # Compare the current epoch time with the stored time.
        # If it's been more than one minute, reset the rateLimitRemaining
        # variable
        if current_epoch_time - self.current_epoch_time > 60:
            self.current_epoch_time = current_epoch_time
            self.rate_limit_remaining = self.rate_limit
            self.logger.debug(
                "%s - Resetting Rate Limit Remaining to %s",
                current_time,
                self.rate_limit,
            )

        # The following APIs return Rate Limit information in consistent Response Headers:
        # Property Manager - https://techdocs.akamai.com/property-mgr/reference/rate-and-resource-limiting
        # Edge Diagnostics - https://techdocs.akamai.com/edge-diagnostics/reference/rate-limiting
        SUPPORTED_APPS = ["papi", "edge-diagnostics", "client-lists"]
        url_split = split("/", self.url)

        if url_split[1] in SUPPORTED_APPS:

            use_custom_rate_limits = True

            if "X-RateLimit-Limit" in self.request_result.headers:
                self.rate_limit = int(
                    self.request_result.headers["X-RateLimit-Limit"]
                )
            # Client Lists has a rate limit of 30 requests per minute
            # https://techdocs.akamai.com/client-lists/reference/rate-control
            if url_split[1] == "client-lists":
                self.rate_limit = 30

            if "X-RateLimit-Remaining" in self.request_result.headers:
                self.rate_limit_remaining = int(
                    self.request_result.headers["X-RateLimit-Remaining"]
                )

        # Don't allow the Rate Limit Remaining to use
        # more than 25% of total rate limit.
        if self.rate_limit_remaining / self.rate_limit < 0.05:
            print(
                f"{current_time} - Waiting 60 seconds before processing to remain under"
                "rate limit."
            )
            self.logger.info(
                "%s - Waiting 60 seconds before processing to remain under"
                "rate limit.",
                current_time,
            )
            time.sleep(60)

        # Decrement the rateLimitRemaining variable for apps that don't return
        # rate information
        if use_custom_rate_limits is False:
            self.rate_limit_remaining -= 1
        self.logger.debug(
            "%s - Rate Limit Remaining: %s /"
            "Rate Limit: %s /"
            "Percent of Rate Limit Remaining: %s",
            current_time,
            self.rate_limit_remaining,
            self.rate_limit,
            self.rate_limit_remaining / self.rate_limit,
        )

    def get_request(self, cache: int = 0) -> None:
        """
        Performs GET request

        :param cache: Allow the response to be cached for future use. A value of 0 disables caching
        """
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

        try:
            if USE_CACHING:
                if cache != 0:
                    self.request_result = self.requests.get(
                        urljoin(self.baseurl, self.url),
                        expire_after=cache,
                        headers=self.headers,
                        timeout=self.request_timeout,
                    )
                    if self.request_result.from_cache:
                        self.logger.debug(
                            "%s - URL %s retrieved from requests cache.",
                            current_time,
                            self.url
                        )
                else:
                    with self.requests.cache_disabled():
                        self.request_result = self.requests.get(
                            urljoin(self.baseurl, self.url), headers=self.headers,
                            timeout=self.request_timeout,
                        )
                        self.check_rate_limit()
            else:
                self.request_result = self.requests.get(
                    urljoin(self.baseurl, self.url),
                    headers=self.headers,
                    timeout=self.request_timeout,
                )
                self.check_rate_limit()

            # Check for 429 response code, only doing this for GET requests to
            # prevent potential duplicate body submissions
            if self.get_response_status() == 429:
                # Check if the X-RateLimit-Next response header exists to calculate when we can attempt the next request, otherwise, hardcode the retry time
                if "X-RateLimit-Next" in self.request_result.headers:
                    ratelimit_next = datetime.datetime.fromisoformat(self.request_result.headers["X-RateLimit-Next"]).astimezone(datetime.timezone.utc)
                    current_time = datetime.datetime.now().astimezone(datetime.timezone.utc)
                    retry_seconds = ((ratelimit_next - current_time).seconds + 5)
                else:
                    retry_seconds = 30

                print(
                    f"API returned 429 response, sleeping for {retry_seconds} seconds before"
                    " trying again."
                )
                time.sleep(retry_seconds)
                self.get_request()
        except requests.exceptions.Timeout as e:
            if self.retry_request is True:
                self.logger.error(
                    "%s - Timeout experienced while processing the request"
                    " to %s. Waiting 15 seconds and trying again.",
                    current_time,
                    self.url,
                )
                # Set the retry_request attribute to False
                # This will allow for a single retry to take place
                self.retry_request = False
                time.sleep(15)
                self.get_request()
            else:
                self.logger.error(
                    "%s - Timeout experienced while processing the request"
                    " to %s.",
                    current_time,
                    self.url,
                )

                raise SystemExit() from e

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "%s - Error during GET request processing for %s",
                current_time,
                self.url,
            )
            self.logger.error(ERROR_DETAILS, current_time, e)

            raise SystemExit() from e

    def post_request(self) -> None:
        """
        Performs POST request
        """
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

        try:
            self.request_result = self.requests.post(
                urljoin(self.baseurl, self.url),
                headers=self.headers,
                json=self.body,
                timeout=self.request_timeout,
            )
            self.check_rate_limit()

        # Don't attempt to retry POST requests
        except requests.exceptions.Timeout as e:
            self.logger.error(
                TIMEOUT_ERROR,
                current_time,
                self.url,
            )

            raise SystemExit() from e

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "%s - Error during POST request processing for %s",
                current_time,
                self.url,
            )
            self.logger.error(REQUEST_BODY, current_time, self.body)
            self.logger.error(ERROR_DETAILS, current_time, e)

            raise SystemExit() from e

    def put_request(self) -> None:
        """
        Performs PUT request
        """
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

        try:
            self.request_result = self.requests.put(
                urljoin(self.baseurl, self.url),
                headers=self.headers,
                json=self.body,
                timeout=self.request_timeout,
            )
            self.check_rate_limit()

        # Don't attempt to retry PUT requests
        except requests.exceptions.Timeout as e:
            self.logger.error(
                TIMEOUT_ERROR,
                current_time,
                self.url,
            )

            raise SystemExit() from e

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "%s - Error during PUT request processing for %s",
                current_time,
                self.url,
            )
            self.logger.error(REQUEST_BODY, current_time, self.body)
            self.logger.error(ERROR_DETAILS, current_time, e)

            raise SystemExit() from e

    def patch_request(self) -> None:
        """
        Performs PATCH request
        """
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

        try:
            self.request_result = self.requests.patch(
                urljoin(self.baseurl, self.url),
                headers=self.headers,
                json=self.body,
                timeout=self.request_timeout,
            )
            self.check_rate_limit()

        # Don't attempt to retry PATCH requests
        except requests.exceptions.Timeout as e:
            self.logger.error(
                TIMEOUT_ERROR,
                current_time,
                self.url,
            )

            raise SystemExit() from e

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "%s - Error during PATCH request processing for %s",
                current_time,
                self.url,
            )
            self.logger.error(REQUEST_BODY, current_time, self.body)
            self.logger.error(ERROR_DETAILS, current_time, e)

            raise SystemExit() from e

    def delete_request(self) -> None:
        """
        Performs DELETE request
        """
        current_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

        try:
            self.request_result = self.requests.delete(
                urljoin(self.baseurl, self.url),
                headers=self.headers,
                json=self.body,
                timeout=self.request_timeout,
            )
            self.check_rate_limit()

        # Don't attempt to retry DELETE requests
        except requests.exceptions.Timeout as e:
            self.logger.error(
                TIMEOUT_ERROR,
                current_time,
                self.url,
            )

            raise SystemExit() from e

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "%s - Error during DELETE request processing for %s",
                current_time,
                self.url,
            )
            self.logger.error(REQUEST_BODY, current_time, self.body)
            self.logger.error(ERROR_DETAILS, current_time, e)

            raise SystemExit() from e

    def get_response_body(self) -> str:
        """
        Returns response data from previous request

        :return: JSON-formatted output from response body
        """
        # Reset the retry_request attribute
        self.retry_request = True
        return self.request_result.json()

    def get_response_body_text(self) -> str:
        """
        Returns response data from previous request as text

        :return: Text output from response body
        """
        # Reset the retry_request attribute
        self.retry_request = True
        return self.request_result.text

    def get_response_status(self) -> int:
        """
        Returns response status code from previous request

        :return status_code: Status Code from response
        """
        return self.request_result.status_code

    def get_response_headers(self) -> None:
        """
        Prints response headers from the request
        """
        print(self.request_result.headers)

    def papi_get_switchkey(self, account_id: str) -> list:
        """
        Retrieves the list of account switchkeys for an account by Account ID

        :return switchkeys: List of account switchkeys associated to the account
        """

        endpoint = f"/identity-management/v3/api-clients/self/account-switch-keys?search={account_id}"
        self.set_request_url(endpoint, False)
        self.get_request(604800)
        switchkeys = self.get_response_body()

        return switchkeys