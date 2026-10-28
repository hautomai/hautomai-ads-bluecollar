import time

import requests

SEARCH_URL = "https://google.serper.dev/search"
PLACES_URL = "https://google.serper.dev/places"


class SerperError(Exception):
    pass


class SerperClient:
    def __init__(self, api_key, max_retries=4):
        self.api_key = api_key
        self.max_retries = max_retries

    def _post(self, url, payload):
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        backoff = [2, 5, 12, 30]
        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}"
                else:
                    raise SerperError(f"Serper error HTTP {resp.status_code}: {resp.text[:300]}")
            except requests.RequestException as exc:
                last_error = str(exc)
            if attempt < self.max_retries - 1:
                time.sleep(backoff[attempt])
        raise SerperError(f"Serper request failed after {self.max_retries} attempts: {last_error}")

    def search(self, query, region, num=10):
        payload = {"q": query, "gl": region.lower(), "hl": "en", "num": num}
        return self._post(SEARCH_URL, payload)

    def places(self, query, region):
        payload = {"q": query, "gl": region.lower(), "hl": "en"}
        return self._post(PLACES_URL, payload)