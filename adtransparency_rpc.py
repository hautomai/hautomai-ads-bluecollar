import datetime
import json
import time

import requests

URL = "https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives?authuser=0"
BACKOFF = [2, 6, 15]


class TransparencyError(Exception):
    pass


def probe_advertiser(advertiser_id, page_size=40, max_retries=4, timeout=30):
    """Return total ad count + last shown date for an advertiser via the
    keyless SearchCreatives RPC (global, all regions).

    Returns {"ad_count": int|None, "last_ad_shown": "YYYY-MM-DD"|None, "error": str|None}.
    Fails open: on network/parse errors ad_count is None so the caller decides.
    """
    result = {"ad_count": None, "last_ad_shown": None, "error": None}
    payload = {
        "2": page_size,
        "3": {"13": {"1": [advertiser_id]}},
        "7": {"1": 1},
    }
    body = "f.req=" + json.dumps(payload, separators=(",", ":"))
    headers = {"content-type": "application/x-www-form-urlencoded"}

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(URL, data=body, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                last_error = "HTTP 429"
            elif resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
            else:
                text = resp.text.strip()
                if text in ("{}", "{1:[]}", "[]", ""):
                    result["ad_count"] = 0
                    return result
                data = json.loads(text)
                creatives = data.get("1") or []
                if isinstance(creatives, list) and creatives:
                    shown = []
                    for creative in creatives:
                        if isinstance(creative, dict) and creative.get("7") and isinstance(creative["7"], dict):
                            stamp = creative["7"].get("1")
                            try:
                                shown.append(int(stamp))
                            except (TypeError, ValueError):
                                continue
                    if shown:
                        result["last_ad_shown"] = (
                            datetime.datetime.fromtimestamp(
                                max(shown), datetime.timezone.utc
                            )
                            .date()
                            .isoformat()
                        )
                total = data.get("4") or data.get("5")
                try:
                    result["ad_count"] = int(total) if total is not None else (len(creatives) if isinstance(creatives, list) else 0)
                except (TypeError, ValueError):
                    result["ad_count"] = len(creatives) if isinstance(creatives, list) else 0
                return result
        except requests.RequestException as exc:
            last_error = str(exc)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = f"parse: {exc}"
        if attempt < max_retries - 1:
            time.sleep(BACKOFF[attempt])

    result["error"] = last_error
    return result