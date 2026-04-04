import time
import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LinkedInScraperClient:
    """Modular HTTP client with built-in retries and exponential backoff for resilience."""

    def __init__(self, session: requests.Session, max_retries: int = 3, backoff_factor: float = 1.0):
        self.session = session
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.common_headers = {
            "x-restli-protocol-version": "2.0.0",
        }

    def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Core request method with redundancy (retries)."""
        headers = self.common_headers.copy()
        headers.update(kwargs.pop("headers", {}))

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(method, url, headers=headers, **kwargs)
                
                # Check for rate limiting
                if response.status_code == 429:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"Rate limited (429). Retrying in {wait_time}s... (Attempt {attempt})")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                # 404 is usually not worth retrying
                if response.status_code == 404:
                    return {"error": "not_found", "status": 404}
                
                # For other HTTP errors, retry if not the last attempt
                if attempt < self.max_retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"HTTP error {response.status_code}. Retrying in {wait_time}s...: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"HTTP error persistence: {e} after {self.max_retries} attempts.")
                    raise

            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                if attempt < self.max_retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"Request/Parse failed ({type(e).__name__}). Retrying in {wait_time}s...: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Fatal communication error: {e}")
                    raise

        raise Exception(f"Failed to complete request to {url} after {self.max_retries} attempts.")

    def get_json(self, url: str, use_graphql_agent: bool = False) -> Dict[str, Any]:
        """Performs a GET request and returns the parsed JSON response."""
        headers = {}
        if use_graphql_agent:
            headers["x-li-graphql-pegasus-client"] = "true"
        return self._request("GET", url, headers=headers)

    def post_json(self, url: str, data: Any, is_protobuf: bool = False) -> Dict[str, Any]:
        """Performs a POST request, supporting both JSON and Protobuf payloads."""
        headers = {}
        if is_protobuf:
            headers["Content-Type"] = "application/x-protobuf2; symbol-table=voyager-20757"
        else:
            headers["Content-Type"] = "application/json"

        # Check if data is already string or needs to be JSON
        payload = data if isinstance(data, (str, bytes)) else json.dumps(data)
        return self._request("POST", url, headers=headers, data=payload)
