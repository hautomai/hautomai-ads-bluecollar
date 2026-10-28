import re
from urllib.parse import urlparse

SOCIAL_DOMAINS = {
    "facebook.com", "www.facebook.com", "m.facebook.com", "instagram.com",
    "www.instagram.com", "linkedin.com", "www.linkedin.com", "youtube.com",
    "www.youtube.com", "tiktok.com", "www.tiktok.com", "twitter.com",
    "www.twitter.com", "x.com", "pinterest.com", "www.pinterest.com",
    "yelp.com", "www.yelp.com", "yelp.ca", "yellowpages.com", "trustpilot.com",
    "bbb.org", "houzz.com", "angi.com", "homeadvisor.com", "wikipedia.org",
    "google.com", "g.page", "maps.google.com", "goo.gl", "facebook.net",
    "instagram.com", "facebook.com", "m.facebook.com",
}
DROPPED_DOMAINS = SOCIAL_DOMAINS | {
    "linkedin.com", "yelp.com", "yelp.ca", "yellowpages.com", "trustpilot.com",
    "bbb.org", "houzz.com", "angi.com", "homeadvisor.com", "wikipedia.org",
    "google.com", "maps.google.com", "g.page", "goo.gl", "facebook.net",
    "youtube.com", "tiktok.com", "twitter.com", "x.com", "pinterest.com",
    "duckduckgo.com", "bing.com", "indeed.com", "glassdoor.com", "zoominfo.com",
    "signalhire.com", "apollo.io", "facebook.com", "homestars.com", "homestars.ca",
    "thumbtack.com", "nextdoor.com",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{4}(?!\d)")

REGION_TLDS = {
    "US": {"com", "us", "net", "org"},
    "GB": {"co.uk", "uk", "org.uk"},
    "CA": {"ca"},
    "FR": {"fr"},
    "AE": {"ae"},
    "IE": {"ie"},
    "AU": {"com.au", "au", "net.au"},
    "NZ": {"co.nz", "nz", "net.nz"},
    "SG": {"sg", "com.sg"},
    "ZA": {"co.za", "za"},
    "MT": {"com.mt", "mt"},
}

CA_POSTCODE = re.compile(r"\b[A-Za-z]\d[A-Za-z] \d[A-Za-z]\d\b")

DIAL_CODES = {
    "US": ["+1"],
    "CA": ["+1"],
    "GB": ["+44", "020", "012", "013", "014", "015", "016", "017", "018", "019", "070"],
    "AU": ["+61"],
    "NZ": ["+64"],
    "AE": ["+971"],
    "FR": ["+33"],
    "IE": ["+353"],
    "SG": ["+65"],
    "ZA": ["+27"],
    "MT": ["+356"],
}

COUNTRY_TERMS = {
    "US": ["united states", " usa ", "florida", "texas", "california", "georgia", "pennsylvania", "ohio", "illinois", "new york"],
    "CA": ["canada", "ontario", "british columbia", "quebec", "alberta", "manitoba", "saskatchewan", "nova scotia"],
    "GB": ["united kingdom", "england", "scotland", "wales", "northern ireland", "london", "manchester", "liverpool", "birmingham", "leeds", "glasgow"],
    "AE": ["united arab emirates", "uae", "dubai", "sharjah", "abu dhabi", "ajman", "ras al khaimah", "fujairah"],
    "FR": ["france", "paris", "lyon", "marseille", "toulouse", "bordeaux", "lille", "nice", "nantes", "strasbourg"],
    "IE": ["ireland", "dublin", "cork", "limerick", "galway"],
    "AU": ["australia", "new south wales", "queensland", "sydney", "melbourne", "brisbane", "perth"],
    "NZ": ["new zealand", "auckland", "wellington", "christchurch", "queenstown"],
    "SG": ["singapore"],
    "ZA": ["south africa", "johannesburg", "cape town", "durban"],
    "MT": ["malta"],
}


def _host(url):
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def _tld_of(domain):
    parts = domain.rstrip(".").lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov"):
        return ".".join(parts[-2:])
    return parts[-1] if parts else ""


def _normalize(url):
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _clean_social_url(url):
    url = _normalize(url)
    if not url:
        return None
    url = url.split("?")[0].split("#")[0].rstrip("/")
    host = _host(url)
    if "facebook.com" in host or "instagram.com" in host:
        return url
    return None


def _clean_tiktok_url(url):
    url = _normalize(url)
    if not url:
        return None
    url = url.split("?")[0].split("#")[0].rstrip("/")
    host = _host(url)
    if "tiktok.com" not in host:
        return None
    path = urlparse(url).path
    if not path:
        return None
    if path.startswith("/@"):
        parts = path.split("/")
        handle = parts[1]
        return f"https://www.tiktok.com/{handle}"
    return None


def _find_tiktok(links):
    found = []
    for link in links:
        if not link:
            continue
        host = _host(link)
        if "tiktok.com" in host:
            cleaned = _clean_tiktok_url(link)
            if cleaned and cleaned not in found:
                found.append(cleaned)
    return found


def pick_tiktok(links, name):
    """Pick the TikTok handle best matching a business name.

    Scores candidates by token overlap between the sanitized handle and the
    business name, downgrading person-name/non-business noise and exact-name
    handles are preferred.
    """
    candidates = _find_tiktok(links)
    if not candidates:
        return None

    def score(handle):
        slug = handle.rstrip("/").split("@")[-1]
        slug = re.sub(r"official|store|page|profile|tiktok|_+", " ", slug, flags=re.I)
        slug = re.sub(r"\s+", "", slug.lower())
        name_collapsed = re.sub(r"\s+", "", name.lower())
        if name_collapsed and name_collapsed in slug:
            return 1.0
        words = [w for w in _name_tokens(name) if len(w) >= 3]
        if not words:
            return 0.0
        hits = sum(1 for w in words if w in slug)
        return hits / len(words)

    scored = sorted(((score(h), h) for h in candidates), key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    if best_score <= 0.0:
        return None
    return best


def _clean_linkedin_url(url):
    url = _normalize(url)
    if not url:
        return None
    url = url.split("?")[0].split("#")[0].rstrip("/")
    host = _host(url)
    if "linkedin.com" not in host:
        return None
    path = urlparse(url).path.rstrip("/")
    if not path or path.startswith("/in/") or path in ("/company", "/companies"):
        return None
    if path.endswith(("/about", "/posts", "/people", "/jobs", "/life")):
        path = path.rsplit("/", 1)[0]
    if path.startswith("/company/"):
        return f"https://www.linkedin.com{path}"
    if path.startswith("/school/"):
        return f"https://www.linkedin.com{path}"
    return None


def _collect_text_links(resp):
    links = []
    kg = resp.get("knowledgeGraph") or {}
    if kg.get("website"):
        links.append(kg["website"])
    for organic in resp.get("organic") or []:
        links.append(organic.get("link", ""))
        for sub in organic.get("sitelinks") or []:
            links.append(sub.get("link", ""))
    for ans in resp.get("answerBox") or [] if isinstance(resp.get("answerBox"), list) else [resp.get("answerBox")]:
        if isinstance(ans, dict) and ans.get("link"):
            links.append(ans["link"])
    return [link for link in links if link]


def _find_social(links, fragment):
    found = []
    for link in links:
        if not link:
            continue
        host = _host(link)
        if fragment in host:
            if "/groups/" in link or "/posts/" in link:
                continue
            cleaned = _clean_social_url(link)
            if cleaned and cleaned not in found:
                found.append(cleaned)
    return found


def _find_linkedin(links):
    found = []
    for link in links:
        if not link:
            continue
        host = _host(link)
        if "linkedin.com" in host:
            cleaned = _clean_linkedin_url(link)
            if cleaned and cleaned not in found:
                found.append(cleaned)
    return found


def find_website(resp):
    kg = resp.get("knowledgeGraph") or {}
    kg_site = kg.get("website")
    if kg_site:
        host = _host(kg_site)
        if host not in DROPPED_DOMAINS and host:
            return _normalize(kg_site)
    for organic in resp.get("organic") or []:
        link = organic.get("link")
        if not link:
            continue
        host = _host(link)
        if host and host not in DROPPED_DOMAINS:
            return _normalize(link)
    return None


def extract_emails(text):
    if not text:
        return []
    emails = []
    for match in EMAIL_RE.findall(text):
        email = match.lower()
        local = email.split("@")[0]
        if local in ("image", "example", "user", "test", "support") and email.endswith((".png", ".jpg", ".gif", ".webp")):
            continue
        if email not in emails:
            emails.append(email)
    return emails[:3]


def extract_phones(text):
    if not text:
        return []
    phones = []
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) < 7 or len(digits) > 15:
            continue
        if match not in phones:
            phones.append(match.strip())
    return phones[:3]


def _text_blobs(resp):
    blobs = []
    kg = resp.get("knowledgeGraph") or {}
    if isinstance(kg.get("attributes"), dict):
        blobs.append(" ".join(str(v) for v in kg["attributes"].values()))
    if kg.get("description"):
        blobs.append(kg["description"])
    ans = resp.get("answerBox")
    if isinstance(ans, dict):
        blobs.append(ans.get("snippet") or "")
    for organic in resp.get("organic") or []:
        blobs.append(organic.get("snippet") or "")
    for pa in resp.get("peopleAlsoAsk") or []:
        blobs.append(pa.get("snippet") or "")
    return blobs


def _name_tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t}


def _place_score(place, name):
    tokens = _name_tokens(name)
    if not tokens:
        return 0
    title_tokens = _name_tokens(place.get("title"))
    score = len(tokens & title_tokens) / len(tokens)
    site = place.get("website") or ""
    if site and any(t in site.lower() for t in tokens):
        score += 0.5
    return score


def _maps_url(place):
    if place.get("googleMapsUrl"):
        return place["googleMapsUrl"]
    if place.get("googleMapsLink"):
        return place["googleMapsLink"]
    if place.get("cid"):
        return f"https://www.google.com/maps?cid={place['cid']}"
    return None


def build_profile(search_resp, places_resp, name, region):
    profile = {
        "website": None,
        "facebook": None,
        "instagram": None,
        "tiktok": None,
        "linkedin": None,
        "email": None,
        "phone": None,
        "address": None,
        "maps_url": None,
    }

    links = _collect_text_links(search_resp)
    profile["website"] = find_website(search_resp)

    facebook = _find_social(links, "facebook.com")
    instagram = _find_social(links, "instagram.com")
    profile["facebook"] = facebook[0] if facebook else None
    profile["instagram"] = instagram[0] if instagram else None

    tiktok = _find_tiktok(links)
    profile["tiktok"] = pick_tiktok(links, name)

    linkedin = _find_linkedin(links)
    profile["linkedin"] = linkedin[0] if linkedin else None

    blobs = _text_blobs(search_resp)
    emails = []
    phones = []
    for blob in blobs:
        emails.extend(extract_emails(blob))
        phones.extend(extract_phones(blob))
    emails = list(dict.fromkeys(emails))
    phones = list(dict.fromkeys(phones))
    profile["email"] = emails[0] if emails else None

    places = places_resp.get("places") or []
    if isinstance(places, dict):
        places = [places]
    places = [p for p in places if isinstance(p, dict)]

    scored = sorted(((_place_score(p, name), p) for p in places), key=lambda x: x[0], reverse=True)
    best_place = scored[0][1] if scored and scored[0][0] >= 0.4 else None
    if (
        best_place is not None
        and best_place.get("website")
        and profile["website"] is not None
        and _host(best_place["website"]) not in DROPPED_DOMAINS
    ):
        current_tld = _tld_of(_host(profile["website"]))
        allowed = REGION_TLDS.get(region.upper(), set())
        if allowed and current_tld not in allowed:
            profile["website"] = _normalize(best_place["website"])

    for score, place in scored:
        if profile["phone"] is None:
            profile["phone"] = place.get("phoneNumber") or place.get("phone")
        if profile["address"] is None:
            profile["address"] = place.get("address")
        if profile["maps_url"] is None:
            profile["maps_url"] = _maps_url(place)
        if place.get("website") and not profile["website"]:
            host = _host(place["website"])
            if host and host not in DROPPED_DOMAINS:
                profile["website"] = _normalize(place["website"])
        if place.get("email"):
            profile["email"] = profile["email"] or place["email"]

    if profile["phone"] is None and phones:
        profile["phone"] = phones[0]
    if profile["email"] is None and emails:
        profile["email"] = emails[0]

    return profile


def detect_region(requested, profile):
    requested = requested.upper()
    website = (profile.get("website") or "").lower()
    address = (profile.get("address") or "").lower()
    hay = f" {' '.join(website.replace('.', ' ').replace('/', ' ').split())} {address} "

    detected = set()
    for r, terms in COUNTRY_TERMS.items():
        for term in terms:
            if term.lower() in hay:
                detected.add(r)

    if re.search(CA_POSTCODE, hay) and "US" not in detected:
        detected.add("CA")

    if not detected and profile.get("website"):
        tld = _tld_of(_host(profile["website"]))
        tld_specific = {
            "ca": "CA", "co.uk": "GB", "uk": "GB", "com.au": "AU", "au": "AU",
            "ae": "AE", "fr": "FR", "ie": "IE", "co.nz": "NZ", "nz": "NZ", "sg": "SG",
            "co.za": "ZA", "za": "ZA", "com.mt": "MT", "mt": "MT",
        }
        if tld in tld_specific:
            return tld_specific[tld]

    if not detected:
        return requested
    if requested in detected:
        return requested
    if len(detected) == 1:
        return next(iter(detected))
    return requested