from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime
from ntrp.sources.google.auth import (
    CREDENTIALS_PATH,
    NTRP_DIR,
    add_gmail_account,
    discover_gmail_tokens,
)
from ntrp.sources.google.gmail import GmailSource, MultiGmailSource

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/accounts")
async def gmail_accounts():
    accounts = []
    token_paths = discover_gmail_tokens()

    for token_path in token_paths:
        try:
            src = GmailSource(token_path=token_path)
            email = src.get_email_address()
            has_send = src.has_send_scope()
            accounts.append(
                {
                    "email": email,
                    "token_file": token_path.name,
                    "has_send_scope": has_send,
                }
            )
        except Exception as e:
            accounts.append(
                {
                    "email": None,
                    "token_file": token_path.name,
                    "error": str(e),
                }
            )

    return {"accounts": accounts}


@router.post("/add")
async def gmail_add():
    if not CREDENTIALS_PATH.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Gmail credentials not found at {CREDENTIALS_PATH}. "
            "Download OAuth 'Desktop app' credentials from Google Cloud Console.",
        )

    try:
        email = add_gmail_account()

        # Reinitialize Gmail source in runtime
        runtime = get_runtime()
        runtime.gmail = MultiGmailSource()

        return {"email": email, "status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{token_file}")
async def gmail_remove(token_file: str):
    # Security: only allow removing gmail_token*.json files
    if not token_file.startswith("gmail_token") or not token_file.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid token file name")

    token_path = NTRP_DIR / token_file
    if not token_path.exists():
        raise HTTPException(status_code=404, detail="Token file not found")

    try:
        # Get email before deleting (for response)
        email = None
        try:
            src = GmailSource(token_path=token_path)
            email = src.get_email_address()
        except Exception:
            pass

        token_path.unlink()

        # Reinitialize Gmail source in runtime
        runtime = get_runtime()
        runtime.gmail = MultiGmailSource()
        if not runtime.gmail.sources:
            runtime.gmail = None

        return {"email": email, "status": "removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
