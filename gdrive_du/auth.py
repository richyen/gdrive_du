"""Google OAuth (desktop flow) and Drive service construction."""
from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Read-only access is all we need to crawl and size files.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

DEFAULT_CREDENTIALS_FILE = os.environ.get("GDRIVE_DU_CREDENTIALS", "credentials.json")
DEFAULT_TOKEN_FILE = os.environ.get("GDRIVE_DU_TOKEN", "token.json")


def get_credentials(
    credentials_file: str = DEFAULT_CREDENTIALS_FILE,
    token_file: str = DEFAULT_TOKEN_FILE,
) -> Credentials:
    """Return valid user credentials, running the desktop OAuth flow if needed.

    A cached ``token.json`` is reused on subsequent runs. If it is missing or
    expired (and cannot be refreshed) the interactive consent flow runs, opening
    a browser window.
    """
    creds: Credentials | None = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"OAuth client secrets not found: {credentials_file}. "
                    "Download it from Google Cloud Console (OAuth client ID of "
                    "type 'Desktop app') and save it as credentials.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())

    return creds


def get_service(
    credentials_file: str = DEFAULT_CREDENTIALS_FILE,
    token_file: str = DEFAULT_TOKEN_FILE,
):
    """Build an authenticated Drive v3 service client."""
    creds = get_credentials(credentials_file, token_file)
    return build("drive", "v3", credentials=creds, cache_discovery=False)
