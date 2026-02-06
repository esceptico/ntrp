from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

NTRP_DIR = Path.home() / ".ntrp"
CREDENTIALS_PATH = NTRP_DIR / "gmail_credentials.json"

SCOPES_GMAIL_READ = ["https://www.googleapis.com/auth/gmail.readonly"]
SCOPES_GMAIL_SEND = ["https://www.googleapis.com/auth/gmail.send"]
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]

# Default scopes for new tokens (Gmail + Calendar for unified auth)
SCOPES_ALL = SCOPES_GMAIL_READ + SCOPES_GMAIL_SEND + SCOPES_CALENDAR


def discover_gmail_tokens() -> list[Path]:
    """Find all Gmail token files in ~/.ntrp/"""
    if not NTRP_DIR.exists():
        return []
    return sorted(list(NTRP_DIR.glob("gmail_token*.json")))


def discover_calendar_tokens() -> list[Path]:
    """Find all token files that have calendar scope (Gmail tokens work too)."""
    if not NTRP_DIR.exists():
        return []
    # Check both calendar_token*.json AND gmail_token*.json (unified auth)
    calendar_tokens = list(NTRP_DIR.glob("calendar_token*.json"))
    gmail_tokens = list(NTRP_DIR.glob("gmail_token*.json"))
    return sorted(calendar_tokens + gmail_tokens)


def get_next_gmail_token_path() -> Path:
    """Get path for next Gmail token (for adding new account)."""
    existing = discover_gmail_tokens()
    if not existing:
        return NTRP_DIR / "gmail_token.json"
    n = len(existing) + 1
    return NTRP_DIR / f"gmail_token_{n}.json"


def get_google_credentials(
    token_path: Path,
    scopes: list[str] | None = None,
    require_scopes: list[str] | None = None,
) -> Credentials:
    """
    Get or refresh OAuth credentials from token file.

    Args:
        token_path: Path to the token JSON file
        scopes: Scopes to request for new tokens (default: SCOPES_ALL)
        require_scopes: If set, raise PermissionError if token lacks these scopes

    Returns:
        Valid Credentials object

    Raises:
        FileNotFoundError: If credentials file doesn't exist
        PermissionError: If token lacks required scopes
    """
    scopes = scopes or SCOPES_ALL
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path))

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDENTIALS_PATH}\n"
                    "Download OAuth 'Desktop app' credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    if require_scopes and creds.scopes:
        for scope in require_scopes:
            if scope not in creds.scopes:
                raise PermissionError(
                    f"Token at {token_path} lacks required scope: {scope}\n"
                    "Run 'ntrp gmail add' to re-authenticate with required scopes."
                )

    return creds


def has_scope(creds: Credentials, scope: str) -> bool:
    """Check if credentials have a specific scope."""
    if not creds.scopes:
        return False
    return scope in creds.scopes


def add_gmail_account() -> str:
    """
    Add a new Gmail account via OAuth flow.

    Returns:
        The email address of the added account

    Raises:
        FileNotFoundError: If credentials file doesn't exist
    """

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {CREDENTIALS_PATH}\n"
            "Download OAuth 'Desktop app' credentials from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES_ALL)
    creds = flow.run_local_server(port=0)

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "unknown")

    token_path = get_next_gmail_token_path()
    NTRP_DIR.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    return email
