"""Business rules engine. Hard-coded rules that override LLM behavior."""

import json
import logging

logger = logging.getLogger(__name__)

# Tutorial video for ring setup
RING_TUTORIAL_URL = "https://www.youtube.com/watch?v=7YrYoqvV8jA"


def apply_rules(category: str, order_data: dict | None = None,
                thread_context: list[dict] | None = None,
                existing_tasks: list[dict] | None = None) -> dict:
    """
    Apply business rules based on email category and context.

    Returns:
        dict with 'rules' (list of rule names), 'template' (response guidelines),
        'create_task' (task to create if needed), 'response_notes' (specific points to include)
    """
    rules = []
    response_notes = []
    create_task = None
    template = ""

    # Determine thread stage
    thread_messages = thread_context or []
    our_replies = [m for m in thread_messages
                   if _is_our_reply(m)]
    is_followup = len(our_replies) > 0

    # Check if we already have a task for this customer
    has_existing_task = bool(existing_tasks)

    if category == "missing_ring":
        rules.append("rule_4_missing_ring")
        template = _missing_ring_template(order_data, is_followup, existing_tasks)
        response_notes = [
            "Rings ship separately due to manufacturing and customs delays",
            "Glasses work without the ring",
            f"Include tutorial link: {RING_TUTORIAL_URL}",
            "Ask them to use insert card to confirm ring size if not done",
            "We'll notify when rings ship + send tracking",
        ]

    elif category == "ring_exchange":
        rules.append("rule_2_ring_exchange")
        template = _ring_exchange_template(order_data, is_followup, existing_tasks)
        response_notes = [
            "Must receive old ring back before sending new one",
            "Currently out of stock — next batch ships in 4-7 weeks",
            "Ask customer to confirm new size using insert card",
            "Track as ring exchange task",
        ]
        if not _has_task_type(existing_tasks, "ring_exchange"):
            create_task = {
                "type": "ring_exchange",
                "status": "awaiting_return",
                "details": {
                    "old_size": _get_ring_size(order_data),
                    "new_size": None,
                },
            }

    elif category == "return":
        rules.append("rule_3_return_refund")
        template = _return_template(order_data, is_followup, thread_messages, existing_tasks)
        response_notes = _return_response_notes(is_followup, thread_messages)
        if not _has_task_type(existing_tasks, "return_refund"):
            create_task = {
                "type": "return_refund",
                "status": "inquiry",
                "details": {"reason": None},
            }

    elif category == "prescription":
        rules.append("rule_1_prescription_timeline")
        template = _prescription_template(order_data, is_followup)
        response_notes = [
            "All prescription glasses orders now ship in April",
            "Reason: manufacturing delays + time for prescription collection",
            "Apologize for delay, reassure tracking will be sent",
        ]

    elif category == "delivery_status":
        rules.append("rule_6_delivery_status")
        template = _delivery_status_template(order_data)
        response_notes = [
            "Use Shopify fulfillment displayStatus and timestamps",
            "Tracking numbers NOT available via API — suggest checking Shopify order confirmation email",
            "Reference carrier from shippingLine.source if available",
        ]

    elif category == "positive_feedback":
        template = (
            "The customer is expressing positive feedback or satisfaction. "
            "Respond warmly but briefly. Thank them and express excitement. "
            "Keep it short — 1-2 sentences max."
        )
        response_notes = ["Brief, warm acknowledgment", "No need for lengthy response"]

    elif category == "general":
        rules.append("rule_5_order_lookup")
        template = (
            "General inquiry. Identify what the customer needs and respond helpfully. "
            "If order-related, try to look up their order. "
            "If unsure, ask for clarification."
        )
        response_notes = [
            "Match by email first, then name, then ask for order number",
        ]

    # Always apply thread context rule
    if thread_messages:
        rules.append("rule_7_thread_context")
        response_notes.append("Review full thread — don't repeat info already given")
        response_notes.append("Don't ask questions already answered in thread")

    return {
        "rules": rules,
        "template": template,
        "create_task": create_task,
        "response_notes": response_notes,
    }


def _is_our_reply(message: dict) -> bool:
    """Check if a message is from Team MIRA."""
    from_field = message.get("from_", message.get("from", message.get("from_email", ""))).lower()
    return "team@trymira.com" in from_field or "team@halo.so" in from_field


def _has_task_type(tasks: list[dict] | None, task_type: str) -> bool:
    """Check if there's an existing task of the given type."""
    if not tasks:
        return False
    return any(t.get("type") == task_type for t in tasks)


def _get_ring_size(order_data: dict | None) -> str | None:
    """Extract ring size from order metafields."""
    if not order_data:
        return None
    metafields = order_data.get("metafields", {})
    custom_data = metafields.get("custom_data", "")
    if custom_data:
        try:
            data = json.loads(custom_data) if isinstance(custom_data, str) else custom_data
            items = data.get("items", [])
            if items:
                return items[0].get("ringSize")
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
    return None


def _missing_ring_template(order_data: dict | None, is_followup: bool,
                           existing_tasks: list[dict] | None) -> str:
    """Generate template for missing ring inquiries."""
    if is_followup:
        return (
            "This is a follow-up about a missing ring. The customer already knows "
            "the ring ships separately. Provide an update if possible, or reassure "
            "that we'll notify them when rings ship."
        )
    return (
        "First response about missing ring. Apologize for confusion. Explain:\n"
        "1. Ring ships separately due to manufacturing/customs delays\n"
        "2. Glasses work without the ring\n"
        "3. Share tutorial video link\n"
        "4. Ask them to confirm ring size using insert card if not done\n"
        "5. We'll notify when rings ship + send tracking"
    )


def _ring_exchange_template(order_data: dict | None, is_followup: bool,
                            existing_tasks: list[dict] | None) -> str:
    """Generate template for ring exchange requests."""
    base = (
        "Ring exchange request. Key points:\n"
        "1. We need to receive the old ring back first\n"
        "2. We're currently out of rings — next batch ships in 4-7 weeks\n"
        "3. Ask customer to confirm desired new size using the insert card\n"
        "4. We'll arrange return shipping for the old ring"
    )
    if is_followup and _has_task_type(existing_tasks, "ring_exchange"):
        return "Follow-up on existing ring exchange. Check task status and provide update."
    return base


def _return_template(order_data: dict | None, is_followup: bool,
                     thread_messages: list[dict],
                     existing_tasks: list[dict] | None) -> str:
    """Generate template for return/refund requests — follows structured process."""
    # Check thread for return reason
    has_reason = _customer_gave_return_reason(thread_messages)
    we_asked_reason = _we_asked_for_reason(thread_messages)

    if not we_asked_reason and not has_reason:
        return (
            "STEP 1: Customer wants to return. Before processing, ask what "
            "specifically isn't working for them. Be empathetic. If there are "
            "recent improvements (increased query limits, premium access), "
            "mention them and ask if they'd still like to proceed."
        )
    elif we_asked_reason and not has_reason:
        return (
            "STEP 2: We already asked the reason. Wait for customer to respond "
            "with their reason. If they've just confirmed they want to return, "
            "acknowledge and confirm we'll send a return label."
        )
    elif has_reason:
        return (
            "STEP 3: Customer has given their reason. Confirm we'll send a return "
            "label. Note that refund is processed after we receive the product back."
        )
    return (
        "Return request. Follow the structured process: ask why → wait for reason → "
        "send return label → refund after receiving product."
    )


def _return_response_notes(is_followup: bool, thread_messages: list[dict]) -> list[str]:
    """Get specific response notes for returns."""
    notes = [
        "Follow structured return process: ask why → wait → confirm label → refund after receipt",
    ]
    if not is_followup:
        notes.append("Ask what specifically isn't working before processing return")
        notes.append("Mention improvements if applicable (query limits, premium access)")
    return notes


def _customer_gave_return_reason(thread_messages: list[dict]) -> bool:
    """Check if customer already gave a return reason in thread."""
    import re
    reason_indicators = [
        r"doesn't (work|fit)",
        r"too (big|small|heavy|bulky)",
        r"not (comfortable|what I expected|satisfied)",
        r"limited (to|queries)",
        r"shape.*(doesn't|not).*work",
        r"size.*(doesn't|not).*work",
        r"bummer",
        r"disappointed",
    ]
    for msg in thread_messages:
        if _is_our_reply(msg):
            continue
        body = msg.get("body", msg.get("text", "")).lower()
        for pattern in reason_indicators:
            if re.search(pattern, body):
                return True
    return False


def _we_asked_for_reason(thread_messages: list[dict]) -> bool:
    """Check if we already asked the customer for their return reason."""
    import re
    ask_indicators = [
        r"what.*specifically",
        r"why.*return",
        r"what.*isn't working",
        r"are you sure",
        r"could you.*share",
        r"mind.*sharing",
    ]
    for msg in thread_messages:
        if not _is_our_reply(msg):
            continue
        body = msg.get("body", msg.get("text", "")).lower()
        for pattern in ask_indicators:
            if re.search(pattern, body):
                return True
    return False


def _prescription_template(order_data: dict | None, is_followup: bool) -> str:
    """Generate template for prescription-related inquiries."""
    return (
        "Prescription glasses inquiry. Key facts:\n"
        "1. All prescription orders now ship in April\n"
        "2. Reason: manufacturing delays + time for customers to submit prescriptions\n"
        "3. Apologize for the delay\n"
        "4. Tracking will be sent when shipped\n"
        "5. If they haven't submitted prescription yet, direct to account.trymira.com"
    )


def _delivery_status_template(order_data: dict | None) -> str:
    """Generate template based on actual Shopify fulfillment data."""
    if not order_data:
        return (
            "Delivery status inquiry but no order data available. "
            "Ask customer for order number or email to look up their order."
        )

    fulfillments = order_data.get("fulfillments", [])
    if not fulfillments:
        return (
            "Order found but no fulfillment data. The order may not have shipped yet. "
            "Check displayFulfillmentStatus for current state."
        )

    # Build template from actual data
    parts = ["Delivery status inquiry. Order data shows:"]
    for f in fulfillments:
        status = f.get("display_status", f.get("displayStatus", ""))
        parts.append(f"- Fulfillment status: {status}")
        if f.get("estimated_delivery") or f.get("estimatedDeliveryAt"):
            parts.append(f"- Estimated delivery: {f.get('estimated_delivery') or f.get('estimatedDeliveryAt')}")
        if f.get("delivered_at") or f.get("deliveredAt"):
            parts.append(f"- Delivered at: {f.get('delivered_at') or f.get('deliveredAt')}")
        if f.get("in_transit_at") or f.get("inTransitAt"):
            parts.append(f"- In transit since: {f.get('in_transit_at') or f.get('inTransitAt')}")

    parts.append("\nNote: Tracking numbers are NOT available via API. "
                 "Suggest checking Shopify order confirmation email for tracking.")
    return "\n".join(parts)
