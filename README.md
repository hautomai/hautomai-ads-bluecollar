# Blue Collar Advertiser Leads

Daily scraper that finds blue-collar businesses (roofing, plumbing, HVAC, etc.)
advertising on Google in English-speaking countries, enriches them via
[Serper](https://serper.dev), and writes new leads to a Google Sheet
(or CSV) — max 10 new businesses per day, deduplicated forever.

## Pipeline

1. For each (query, region) combo: run the Apify actor
   [`solidcode/ads-transparency-scraper`](https://apify.com/solidcode/ads-transparency-scraper)
   → ad creatives with advertiser name + AR ID.
2. Per advertiser: Serper `/search` (website, Facebook, Instagram, email) and
   `/places` (phone, address, Maps link).
3. Append rows to the Google Sheet. Every advertiser ID/name is remembered, so
   no business is ever processed twice.

Combos rotate round-robin (3 per day by default) so coverage spreads across
all 150 query × region combinations over time.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create `.env` (see `.env.example`):

```
apify: <Apify API token>            # https://console.apify.com/settings/integrations
serper: <Serper API key>            # https://serper.dev/dashboard
GOOGLE_CREDENTIALS_JSON: /path/to/credentials.json
```

### Google Sheets access (two options)

**Option A — OAuth desktop app (recommended, spreadsheet lands in your own Drive):**
1. Create an OAuth client ID (Desktop app) at https://console.cloud.google.com/apis/credentials
2. Enable the Google Sheets API and Google Drive API for the project
3. Download the JSON → set `GOOGLE_CREDENTIALS_JSON`
4. On the **first run only**, a browser opens for you to log in and authorize
   — a `token.json` is then cached and later (cron) runs are non-interactive

**Option B — Service account:**
Create a service-account key (same console), set
`GOOGLE_SERVICE_ACCOUNT_JSON`, and set `share_email` in `config.yaml` to your
email so the auto-created spreadsheet is shared with you.

No Google credentials yet? The script falls back to writing `leads_<date>.csv`.

## Run

```bash
.venv/bin/python main.py                      # normal daily run (3 combos, 10 leads)
.venv/bin/python main.py --dry-run            # no Google Sheets/CSV write
.venv/bin/python main.py --query roofing      # only one niche
.venv/bin/python main.py --region CA          # only one country
.venv/bin/python main.py --max 5 --combos 2   # tune output size
.venv/bin/python main.py --reset-rotation     # restart combo rotation
.venv/bin/python rebuild_sheet.py             # rebuild the sheet cleanly from results.jsonl
```

### Daily automation

```bash
crontab -e
# run at 8am every day, log to a file
0 8 * * * cd /path/to/ads-bluecollar && .venv/bin/python main.py >> daily.log 2>&1
```

## Config (`config.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `max_per_day` | 10 | Max new businesses enriched per run |
| `combos_per_day` | 3 | (query × region) combos processed per run |
| `apify_max_results` | 20 | Ad creatives requested per Apify run |
| `request_delay_seconds` | 0.7 | Pause between Serper calls |
| `apify_run_delay_seconds` | 3 | Pause between Apify runs |
| `share_email` | empty | Your Google email to share the sheet with (service account only) |

## Costs

- Apify: a few actor runs/day (≈$0.01–0.05)
- Serper: ~20 calls/day — free tier covers 2,500/month

## Sheet columns

`query, region, business_name, advertiser_id, creative_count, website,
facebook, instagram, email, phone, address, maps_url, found_date`

Notes: emails come only from SERP data (snippets, knowledge graph) — they are
sparse and should be spot-checked. Advertiser names from Google Ads can be
generic ("My Roofing"); the website/place matching is best-effort, so review
rows before contacting.