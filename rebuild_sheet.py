import json
import sys

sys.path.insert(0, ".")

from main import load_env_file, load_config
from sheets_writer import SheetsWriter
from extract import detect_region

env = load_env_file(".env")
config = load_config()

creds_path = (
    env.get("GOOGLE_CREDENTIALS_JSON")
    or env.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    or env.get("GOOGLE_SERVICE_ACCOUNT")
)
writer = SheetsWriter(creds_path, config["sheet_title"], config.get("share_email", ""), "sheet_state.json")
writer.connect()
url = writer.ensure_spreadsheet()
print(f"Spreadsheet: {url}")

rows = []
with open(config["results_file"]) as fh:
    for line in fh:
        rows.append(json.loads(line))

fixed = 0
for row in rows:
    if not row.get("advertiser_link") and row.get("advertiser_id"):
        row["advertiser_link"] = (
            f"https://adstransparency.google.com/advertiser/{row['advertiser_id']}"
        )
        fixed += 1
    actual = detect_region(row.get("region", ""), row)
    if actual != row.get("region"):
        print(f"  region {row.get('region')} -> {actual}: {row.get('business_name')}")
        row["region"] = actual
        fixed += 1

print(f"Rebuilding with {len(rows)} rows (backfilled {fixed})...")
count = writer.rebuild(rows)
print(f"Done. {count} rows written.")