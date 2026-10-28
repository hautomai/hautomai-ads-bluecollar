import json
import time

import gspread
from google.oauth2 import service_account


class SheetsError(Exception):
    pass


class SheetsWriter:
    HEADERS = [
        "query", "region", "business_name", "advertiser_link",
        "website", "facebook", "instagram", "tiktok", "linkedin", "email", "phone", "address",
        "maps_url", "ad_count", "last_ad_shown", "found_date",
    ]

    def __init__(self, credentials_path, sheet_title, share_email, state_file, oauth_token_file="token.json"):
        self.credentials_path = credentials_path
        self.sheet_title = sheet_title
        self.share_email = share_email
        self.state_file = state_file
        self.oauth_token_file = oauth_token_file
        self.client = None
        self.sheet = None

    def _creds_type(self):
        with open(self.credentials_path) as fh:
            data = json.load(fh)
        if data.get("type") == "service_account":
            return "service_account"
        if "installed" in data or "web" in data:
            return "oauth"
        return "service_account"

    def connect(self):
        if not self.credentials_path:
            raise SheetsError("GOOGLE_CREDENTIALS_JSON not set")
        if self._creds_type() == "oauth":
            self.client = gspread.oauth(
                credentials_filename=self.credentials_path,
                authorized_user_filename=self.oauth_token_file,
            )
        else:
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ]
            )
            self.client = gspread.authorize(creds)

    def _load_state(self):
        try:
            with open(self.state_file) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, state):
        with open(self.state_file, "w") as fh:
            json.dump(state, fh, indent=2)

    def ensure_spreadsheet(self):
        state = self._load_state()
        spreadsheet_id = state.get("spreadsheet_id")
        if spreadsheet_id:
            try:
                self.sheet = self.client.open_by_key(spreadsheet_id)
            except gspread.SpreadsheetNotFound:
                self.sheet = None
        if self.sheet is None:
            self.sheet = self.client.create(self.sheet_title)
            self._save_state({"spreadsheet_id": self.sheet.id})
            if self.share_email and self._creds_type() == "service_account":
                self.sheet.share(self.share_email, perm_type="user", role="writer")
        worksheet = self.sheet.sheet1
        if worksheet.row_count == 1 and not worksheet.get_all_values():
            worksheet.update([self.HEADERS], value_input_option="RAW")
        return f"https://docs.google.com/spreadsheets/d/{self.sheet.id}"

    def fetch_existing_keys(self):
        worksheet = self.sheet.sheet1
        values = worksheet.get_all_values()
        if not values:
            return set()
        header = values[0]
        id_col = None
        if "advertiser_link" in header:
            id_col = header.index("advertiser_link")
        elif "advertiser_id" in header:
            id_col = header.index("advertiser_id")
        try:
            name_col = header.index("business_name")
            region_col = header.index("region")
        except ValueError:
            return set()
        keys = set()
        for row in values[1:]:
            if id_col is not None and id_col < len(row) and row[id_col]:
                adv_id = row[id_col].strip()
                if "/advertiser/" in adv_id:
                    adv_id = adv_id.rstrip("/").split("/")[-1]
                if adv_id:
                    keys.add(("id", adv_id))
            if name_col < len(row) and region_col < len(row):
                name = row[name_col].strip().lower()
                region = row[region_col].strip().upper() if region_col < len(row) else ""
                if name:
                    keys.add(("name", f"{name}|{region}"))
        return keys

    def append_rows(self, rows):
        if not rows:
            return 0
        worksheet = self.sheet.sheet1
        data = []
        for row in rows:
            values = [row.get(col, "") for col in self.HEADERS]
            if len(values) < len(self.HEADERS):
                values += [""] * (len(self.HEADERS) - len(values))
            else:
                values = values[: len(self.HEADERS)]
            data.append(values)
        for i in range(0, len(data), 100):
            worksheet.append_rows(data[i:i + 100], value_input_option="RAW")
            time.sleep(0.3)
        return len(data)

    def rebuild(self, rows):
        worksheet = self.sheet.sheet1
        worksheet.clear()
        worksheet.update([self.HEADERS], value_input_option="RAW")
        count = self.append_rows(rows)
        try:
            worksheet.freeze(rows=1)
            worksheet.set_column_widths([(1, 16), (2, 12), (3, 28), (4, 40), (5, 40), (6, 40), (7, 40), (8, 40), (9, 40), (10, 30), (11, 22), (12, 38), (13, 42), (14, 10), (15, 16), (16, 12)])
        except Exception:
            pass
        return count