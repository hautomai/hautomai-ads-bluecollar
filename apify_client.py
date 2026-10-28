import time

import requests

ACTOR_ID = "solidcode~ads-transparency-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


class ApifyError(Exception):
    pass


class ApifyClient:
    def __init__(self, token, max_retries=4, timeout=600):
        self.token = token
        self.max_retries = max_retries
        self.timeout = timeout

    def run_actor(self, search_query, region, max_results, date_from=None):
        payload = {
            "searchQuery": search_query,
            "region": region,
            "maxResults": max_results,
        }
        if date_from:
            payload["dateFrom"] = date_from
        params = {"token": self.token}
        backoff = [3, 8, 20, 45]
        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    RUN_SYNC_URL, params=params, json=payload, timeout=self.timeout
                )
                if 200 <= resp.status_code < 300:
                    return self._unwrap(resp.json())
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}"
                else:
                    raise ApifyError(f"Apify error HTTP {resp.status_code}: {resp.text[:300]}")
            except requests.RequestException as exc:
                last_error = str(exc)
            if attempt < self.max_retries - 1:
                time.sleep(backoff[attempt])
        raise ApifyError(f"Apify run failed after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _unwrap(body):
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in ("items", "data", "results", "output"):
                if isinstance(body.get(key), list):
                    return body[key]
        return []


NAME_KEYS = (
    "advertiserName",
    "advertiser_name",
    "advertiser.name",
    "advertiser",
    "name",
    "title",
    "companyName",
)
ID_KEYS = (
    "advertiserId",
    "advertiser_id",
    "advertiser.id",
    "advertiserIdString",
)
DOMAIN_KEYS = (
    "advertiserDomain",
    "domain",
    "landingUrl",
    "landing_url",
    "landingDomain",
    "url",
)


def _first_value(item, keys):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
        if "." in key:
            head, _, tail = key.partition(".")
            nested = item.get(head)
            if isinstance(nested, dict) and tail in nested:
                value = nested[tail]
                if value not in (None, ""):
                    return value
    return None


def extract_advertisers(items, min_last_shown=None):
    advertisers = {}
    for item in items:
        name = _first_value(item, NAME_KEYS)
        adv_id = _first_value(item, ID_KEYS)
        domain = _first_value(item, DOMAIN_KEYS)
        last_shown = item.get("lastShown") or item.get("last_shown") or item.get("dateEnd") or ""
        if name is None and adv_id is None and domain is None:
            continue
        name = str(name).strip() if name is not None else None
        if name and name.lower() in ("unknown", "n/a"):
            name = None
        domain = str(domain).strip() if domain is not None else None
        if domain and domain.startswith("http"):
            domain = domain.split("//", 1)[1].split("/", 1)[0].lower()
        key = adv_id or f"{name or domain or ''}|{domain or ''}"
        entry = advertisers.setdefault(key, {"name": name, "advertiser_id": adv_id, "domains": set(), "last_shown": ""})
        if last_shown and str(last_shown) > str(entry["last_shown"]):
            entry["last_shown"] = str(last_shown)[:10]
        if domain:
            entry["domains"].add(domain)
    if min_last_shown:
        advertisers = {
            key: entry
            for key, entry in advertisers.items()
            if entry["last_shown"] and entry["last_shown"] >= min_last_shown
        }
    return list(advertisers.values())