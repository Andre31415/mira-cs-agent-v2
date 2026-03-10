"""Claude-powered draft generation for customer service emails."""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-3-5-haiku-latest"


async def generate_draft(
    customer_name: str,
    customer_email: str,
    subject: str,
    category: str,
    rules_result: dict,
    order_summary: dict | None = None,
    thread_context: list[dict] | None = None,
    other_threads: list[dict] | None = None,
    existing_tasks: list[dict] | None = None,
) -> str:
    """
    Generate a draft email reply using Claude.

    Returns the draft text string.
    """
    # Build the structured prompt
    prompt = _build_prompt(
        customer_name=customer_name,
        customer_email=customer_email,
        subject=subject,
        category=category,
        rules_result=rules_result,
        order_summary=order_summary,
        thread_context=thread_context,
        other_threads=other_threads,
        existing_tasks=existing_tasks,
    )

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = message.content[0].text.strip()
        return draft
    except Exception as e:
        logger.error(f"Claude draft generation failed: {e}")
        return _fallback_draft(customer_name, category, rules_result)


SYSTEM_PROMPT = """You are drafting a customer service email reply for MIRA, a smart glasses company.

TONE RULES (follow exactly):
- Address customer by first name only (e.g., "Jeff," not "Dear Jeff" or "Hi Jeff,")
- Brief and direct — no long paragraphs
- Empathetic but not over-apologetic
- Sign off exactly as: "Best,\\nTeam MIRA"
- Acknowledge delays honestly
- Offer something positive when delivering bad news

OUTPUT: Return ONLY the email body text. No subject line, no metadata. Start with the customer's first name followed by a comma."""


def _build_prompt(
    customer_name: str,
    customer_email: str,
    subject: str,
    category: str,
    rules_result: dict,
    order_summary: dict | None = None,
    thread_context: list[dict] | None = None,
    other_threads: list[dict] | None = None,
    existing_tasks: list[dict] | None = None,
) -> str:
    """Build the structured prompt for Claude."""
    first_name = customer_name.split()[0] if customer_name else "there"

    sections = []

    # Category and rules
    sections.append(f"EMAIL CATEGORY: {category}")
    sections.append(f"CUSTOMER: {first_name} ({customer_email})")
    sections.append(f"SUBJECT: {subject}")

    # Rules to follow
    rules = rules_result.get("rules", [])
    template = rules_result.get("template", "")
    response_notes = rules_result.get("response_notes", [])

    if rules:
        sections.append(f"\nRULES (these are ABSOLUTE — never violate):\n{template}")

    if response_notes:
        sections.append("\nRESPONSE REQUIREMENTS:")
        for note in response_notes:
            sections.append(f"- {note}")

    # Order data
    if order_summary:
        sections.append("\nORDER DATA (factual — reference only this):")
        sections.append(json.dumps(order_summary, indent=2, default=str))

    # Thread context
    if thread_context:
        sections.append("\nTHREAD CONTEXT (chronological):")
        for i, msg in enumerate(thread_context):
            direction = "CUSTOMER" if not _is_team(msg) else "TEAM MIRA"
            body = msg.get("body", msg.get("text", ""))[:500]
            date = msg.get("date", msg.get("received_at", ""))
            sections.append(f"\n--- Message {i+1} ({direction}, {date}) ---\n{body}")

    # Other threads with same customer
    if other_threads:
        sections.append("\nOTHER THREADS WITH THIS CUSTOMER:")
        for t in other_threads[:3]:
            sections.append(f"- Subject: {t.get('subject', 'N/A')}, "
                          f"Date: {t.get('date', 'N/A')}")

    # Existing tasks
    if existing_tasks:
        sections.append("\nEXISTING TASKS FOR THIS CUSTOMER:")
        for task in existing_tasks:
            details = task.get("details", "{}")
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except json.JSONDecodeError:
                    pass
            sections.append(f"- Type: {task.get('type')}, Status: {task.get('status')}, "
                          f"Details: {json.dumps(details, default=str)}")

    sections.append(f"\nDraft a reply to {first_name}. Follow all rules above exactly. "
                    "If unsure about any fact, do NOT include it. "
                    "If you need info from the customer, ask specifically.")

    return "\n".join(sections)


def _is_team(msg: dict) -> bool:
    """Check if message is from MIRA team."""
    from_field = msg.get("from", msg.get("from_email", "")).lower()
    return "team@trymira.com" in from_field or "team@halo.so" in from_field


def _fallback_draft(customer_name: str, category: str, rules_result: dict) -> str:
    """Generate a fallback draft if Claude is unavailable."""
    first_name = customer_name.split()[0] if customer_name else "there"

    if category == "missing_ring":
        return (
            f"{first_name},\n\n"
            "Sorry for the confusion here. The ring will be shipped separately from the "
            "glasses due to some manufacturing and customs delays.\n\n"
            "Thankfully, the glasses work without the ring as well, so at least you'll "
            "be able to test and get used to them in the meantime. Here's a tutorial "
            "showing more about how everything works:\n"
            "https://www.youtube.com/watch?v=7YrYoqvV8jA\n\n"
            "Be sure to use the insert card in the box to confirm your size if you "
            "haven't already.\n\n"
            "We'll let you know as soon as possible regarding when the rings will be "
            "sent out, and you'll get tracking for them as well.\n\n"
            "Best,\nTeam MIRA"
        )
    elif category == "return":
        return (
            f"{first_name},\n\n"
            "Thanks for reaching out. We're sorry to hear the product isn't working "
            "for you. Could you share a bit more about what specifically isn't working? "
            "We'd love to help if we can.\n\n"
            "Best,\nTeam MIRA"
        )
    elif category == "ring_exchange":
        return (
            f"{first_name},\n\n"
            "Thanks for reaching out about exchanging your ring. We'd be happy to help!\n\n"
            "We'll need to receive your current ring back first before we can send a new one. "
            "We're currently waiting on our next batch of rings, which should arrive in "
            "4-7 weeks.\n\n"
            "Could you confirm your desired new size using the insert card that came "
            "with your glasses?\n\n"
            "Best,\nTeam MIRA"
        )
    elif category == "prescription":
        return (
            f"{first_name},\n\n"
            "Thanks for your patience! Prescription glasses orders are now scheduled "
            "to ship in April. We apologize for the delay — we wanted to make sure "
            "everyone had time to submit their prescriptions and that manufacturing "
            "is just right.\n\n"
            "We'll send you tracking info as soon as your order ships.\n\n"
            "Best,\nTeam MIRA"
        )
    else:
        return (
            f"{first_name},\n\n"
            "Thanks for reaching out! We'll look into this and get back to you shortly.\n\n"
            "Best,\nTeam MIRA"
        )
