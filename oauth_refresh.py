import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from main import load_env_file

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

env = load_env_file(".env")
creds_path = (
    env.get("GOOGLE_CREDENTIALS_JSON")
    or env.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    or env.get("GOOGLE_SERVICE_ACCOUNT")
)
if not creds_path:
    raise SystemExit("GOOGLE_CREDENTIALS_JSON not set in .env")
token_path = "token.json"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8090


def run_server():
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes=SCOPES)
    creds = flow.run_local_server(port=PORT, open_browser=False)
    with open(token_path, "w") as fh:
        json.dump(
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes),
            },
            fh,
        )
    print("\nTOKEN_OK")


if __name__ == "__main__":
    run_server()