"""Gmail operations via external-tool CLI."""

import logging
from datetime import datetime, timedelta, timezone

from .connectors import call_tool, GMAIL_SOURCE_ID

logger = logging.getLogger(__name__)


async def search_emails(query: str) -> list[dict]:
    """Search Gmail with the given query string."""
    try:
        result = await call_tool(GMAIL_SOURCE_ID, "search_email", {"queries": [query]})
        # Response format: {email_results: {emails: [...]}}
        if isinstance(result, dict):
            email_results = result.get("email_results", {})
            if isinstance(email_results, dict):
                emails = email_results.get("emails", [])
                if emails:
                    return emails
            # Fallback: check other known formats
            if "emails" in result:
                return result["emails"]
            if "results" in result:
                return result["results"]
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.error(f"Gmail search failed: {e}")
        return []


async def search_recent_emails(hours: int = 24) -> list[dict]:
    """Search for recent emails to team@trymira.com."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S-00:00")
    query = f"to:team@trymira.com after:{cutoff_str}"
    return await search_emails(query)


async def search_emails_from(email: str) -> list[dict]:
    """Search for all emails from a specific address."""
    query = f"from:{email}"
    return await search_emails(query)


async def search_thread(thread_id: str) -> list[dict]:
    """Get all emails in a thread."""
    query = f"thread:{thread_id}"
    return await search_emails(query)


async def create_draft(reply_to_email_id: str, thread_id: str, to: list[str],
                       subject: str, body: str) -> dict:
    """Create a Gmail draft (never sends)."""
    try:
        result = await call_tool(GMAIL_SOURCE_ID, "draft_email", {
            "reply_to_email_id": reply_to_email_id,
            "thread_id": thread_id,
            "to": to,
            "subject": subject,
            "body": body,
        })
        return result
    except Exception as e:
        logger.error(f"Gmail draft creation failed: {e}")
        return {"error": str(e)}
