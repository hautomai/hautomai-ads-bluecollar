import argparse
import csv
import json
import os
import re
import time
from datetime import date, timedelta

import yaml
from dotenv import load_dotenv

from adtransparency_rpc import probe_advertiser
from apify_client import ApifyClient, ApifyError, extract_advertisers
from extract import build_profile, detect_region, pick_tiktok, _collect_text_links
from serper_client import SerperClient, SerperError
from sheets_writer import SheetsWriter, SheetsError

ENV_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.*?)\s*$")


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return {}
    values = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = ENV_RE.match(line)
            if match:
                values[match.group(1).upper()] = match.group(2).strip("\"'")
    return values


def load_config(path="config.yaml"):
    with open(path) as fh:
        return yaml.safe_load(fh)


def load_rotation(path):
    try:
        with open(path) as fh:
            return json.load(fh).get("index", 0)
    except (OSError, json.JSONDecodeError):
        return 0


def save_rotation(path, index):
    with open(path, "w") as fh:
        json.dump({"index": index}, fh)


def normalize_name(name, domain):
    name = (name or "").strip()
    if not name or name.lower() in ("unknown", "n/a", "unavailable"):
        name = domain or ""
    return name


def _id_from_link(link):
    link = link or ""
    return link.rstrip("/").split("/")[-1] if "/advertiser/" in link else (link or "")


def main():
    parser = argparse.ArgumentParser(description="Daily blue-collar advertiser lead scraper")
    parser.add_argument("--query", action="append", help="Restrict to specific query")
    parser.add_argument("--region", action="append", help="Restrict to specific region")
    parser.add_argument("--max", type=int, help="Override max_per_day")
    parser.add_argument("--combos", type=int, help="Override combos_per_day")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Google Sheets")
    parser.add_argument("--reset-rotation", action="store_true", help="Restart combo rotation")
    parser.add_argument("--csv-only", action="store_true", help="Write CSV instead of Google Sheets")
    args = parser.parse_args()

    env = load_env_file(".env")
    config = load_config()

    apify_token = env.get("APIFY_TOKEN") or env.get("APIFY")
    serper_key = env.get("SERPER_API_KEY") or env.get("SERPER")
    if not apify_token:
        raise SystemExit("APIFY_TOKEN missing in .env")
    if not serper_key:
        raise SystemExit("SERPER_API_KEY missing in .env")

    queries = args.query or config["queries"]
    regions = args.region or config["regions"]
    max_per_day = args.max or config["max_per_day"]
    combos_per_day = args.combos or config["combos_per_day"]

    q_order = [queries[(i * 7) % len(queries)] for i in range(len(queries))]
    combos = []
    for block in range(len(regions)):
        for j in range(len(queries)):
            combos.append((q_order[j], regions[(j + block) % len(regions)]))
    index = 0 if args.reset_rotation else load_rotation(config["rotation_file"])
    chosen = [(combos[i % len(combos)]) for i in range(index, index + combos_per_day)]
    save_rotation(config["rotation_file"], (index + combos_per_day) % len(combos))

    print(f"Combos today ({combos_per_day} of {len(combos)}):")
    for query, region in chosen:
        print(f"  {query} / {region}")

    apify = ApifyClient(apify_token)
    serper = SerperClient(serper_key)

    date_from = date.today() - timedelta(days=config["date_from_days"])

    sheets = None
    spreadsheet_url = None
    if not args.csv_only:
        creds_path = (
            env.get("GOOGLE_CREDENTIALS_JSON")
            or env.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            or env.get("GOOGLE_SERVICE_ACCOUNT")
        )
        sheets = SheetsWriter(
            creds_path,
            config["sheet_title"],
            config.get("share_email", ""),
            "sheet_state.json",
        )
        try:
            sheets.connect()
            spreadsheet_url = sheets.ensure_spreadsheet()
            print(f"Spreadsheet: {spreadsheet_url}")
        except SheetsError as exc:
            print(f"WARNING: Google Sheets unavailable ({exc}) — falling back to CSV")
            sheets = None

    existing_keys = set()
    results_file = config["results_file"]
    if sheets:
        try:
            existing_keys = sheets.fetch_existing_keys()
        except Exception as exc:
            print(f"WARNING: could not read sheet history ({exc})")
    else:
        try:
            with open(results_file) as fh:
                for line in fh:
                    row = json.loads(line)
                    adv_id = row.get("advertiser_id") or _id_from_link(row.get("advertiser_link") or "")
                    if adv_id:
                        existing_keys.add(("id", adv_id))
                    name = (row.get("business_name") or "").strip().lower()
                    region = (row.get("region") or "").strip().upper()
                    if name:
                        existing_keys.add(("name", f"{name}|{region}"))
        except (OSError, json.JSONDecodeError):
            pass

    seen = set()
    advertisers = []
    for query, region in chosen:
        try:
            items = apify.run_actor(query, region, config["apify_max_results"], date_from.isoformat())
        except ApifyError as exc:
            print(f"  ERROR {query}/{region}: {exc}")
            continue
        found = extract_advertisers(items, date_from.isoformat())
        print(f"  {query} / {region}: {len(found)} advertisers from {len(items)} creatives")
        for adv in found:
            name = normalize_name(adv["name"], next(iter(adv["domains"]), None))
            adv_id = adv["advertiser_id"]
            key_id = ("id", adv_id) if adv_id else None
            key_name = ("name", f"{name.lower()}|{region}")
            dup = key_id in existing_keys or key_id in seen if key_id else False
            dup = dup or (key_name in existing_keys or key_name in seen)
            if dup:
                continue
            if key_id:
                seen.add(key_id)
            seen.add(key_name)
            advertisers.append({"query": query, "region": region, "advertiser": adv})
        time.sleep(config["apify_run_delay_seconds"])
        if len(advertisers) >= max_per_day:
            break

    advertisers = advertisers[:max_per_day]
    print(f"New advertisers to enrich: {len(advertisers)}")

    probed = []
    probe_delay = config["probe_request_delay_seconds"]
    for entry in advertisers:
        adv = entry["advertiser"]
        adv_id = adv.get("advertiser_id")
        name = normalize_name(adv["name"], next(iter(adv["domains"]), None))
        if not adv_id:
            probed.append(entry)
            continue
        info = probe_advertiser(adv_id)
        if info.get("error"):
            print(f"  PROBE {name}: failed ({info['error']}) — keeping lead")
            entry["ad_count"] = ""
            entry["last_ad_shown"] = ""
            probed.append(entry)
            time.sleep(probe_delay)
            continue
        if info["ad_count"] == 0:
            print(f"  PROBE {name}: 0 ads — skipped")
            time.sleep(probe_delay)
            continue
        entry["ad_count"] = info["ad_count"]
        entry["last_ad_shown"] = info["last_ad_shown"] or ""
        print(f"  PROBE {name}: {info['ad_count']} ads, last shown {info['last_ad_shown'] or '-'}")
        probed.append(entry)
        time.sleep(probe_delay)
    advertisers = probed
    print(f"Advertisers after 0-ad check: {len(advertisers)}")

    rows = []
    with open(results_file, "a") as fh:
        for i, entry in enumerate(advertisers, start=1):
            query = entry["query"]
            region = entry["region"]
            adv = entry["advertiser"]
            name = normalize_name(adv["name"], next(iter(adv["domains"]), None))
            print(f"[{i}/{len(advertisers)}] {name} ({region})")
            keyword = query if query.lower() not in name.lower() else ""
            search_q = f'"{name}" {keyword}'.strip()
            try:
                search_resp = serper.search(search_q, region, config["serper_num_results"])
            except SerperError as exc:
                print(f"    ERROR search: {exc}")
                continue
            places_q = f"{name} {keyword}".strip()
            try:
                places_resp = serper.places(places_q, region)
            except SerperError as exc:
                print(f"    ERROR places: {exc}")
                places_resp = {}
            profile = build_profile(search_resp, places_resp, name, region)
            if not profile.get("tiktok"):
                try:
                    tk_resp = serper.search(
                        f'"{name}" site:tiktok.com', region, config["serper_num_results"]
                    )
                    profile["tiktok"] = pick_tiktok(_collect_text_links(tk_resp), name)
                except SerperError as exc:
                    print(f"    WARN tiktok lookup: {exc}")
            actual_region = detect_region(region, profile)
            allowed_regions = set(r.upper() for r in config["regions"])
            if actual_region not in allowed_regions:
                print(f"    SKIP: {name} appears to be in {actual_region}, not a targeted country")
                continue
            row = {
                "query": query,
                "region": actual_region,
                "business_name": name,
                "advertiser_link": f"https://adstransparency.google.com/advertiser/{adv.get('advertiser_id') or ''}",
                "website": profile["website"] or "",
                "facebook": profile["facebook"] or "",
                "instagram": profile["instagram"] or "",
                "tiktok": profile["tiktok"] or "",
                "linkedin": profile["linkedin"] or "",
                "email": profile["email"] or "",
                "phone": profile["phone"] or "",
                "address": profile["address"] or "",
                "maps_url": profile["maps_url"] or "",
                "ad_count": entry.get("ad_count", ""),
                "last_ad_shown": entry.get("last_ad_shown", ""),
                "found_date": date.today().isoformat(),
            }
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            time.sleep(config["request_delay_seconds"])

    if rows:
        if sheets:
            sheets.append_rows(rows)
            print(f"Appended {len(rows)} rows to spreadsheet")
        else:
            csv_path = f"leads_{date.today().isoformat()}.csv"
            with open(csv_path, "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=SheetsWriter.HEADERS)
                writer.writeheader()
                writer.writerows(rows)
            print(f"Wrote {len(rows)} rows to {csv_path}")
    print(f"Done. {len(rows)} new leads.")


if __name__ == "__main__":
    main()