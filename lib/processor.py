"""Main processing pipeline — orchestrates the full email processing flow."""

import logging
import time
import re

from . import gmail, shopify, db
from .classifier import (classify_email, is_inbound_customer_email,
                          extract_email_fields, extract_order_number)
from .rules import apply_rules
from .drafter import generate_draft
from .shopify import extract_order_summary

logger = logging.getLogger(__name__)


async def process_emails(hours: int = 24) -> dict:
    """
    Main processing pipeline. Called by /api/process or manual trigger.

    1. Search Gmail for recent emails
    2. Skip already-processed
    3. For each new email: classify, lookup, apply rules, draft, save
    4. Log run stats

    Returns dict with run statistics.
    """
    start_time = time.time()
    stats = {
        "emails_found": 0,
        "emails_processed": 0,
        "drafts_created": 0,
        "tasks_created": 0,
        "errors": [],
    }

    try:
        # Step 1: Fetch recent emails
        raw_emails = await gmail.search_recent_emails(hours=hours)
        stats["emails_found"] = len(raw_emails)
        logger.info(f"Found {len(raw_emails)} emails in last {hours}h")

        # Step 2: Filter and process each email
        for raw_email in raw_emails:
            try:
                result = await _process_single_email(raw_email)
                if result:
                    if result.get("drafted"):
                        stats["drafts_created"] += 1
                    if result.get("task_created"):
                        stats["tasks_created"] += 1
                    stats["emails_processed"] += 1
            except Exception as e:
                error_msg = f"Error processing email: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats["errors"].append(error_msg)

    except Exception as e:
        error_msg = f"Pipeline error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        stats["errors"].append(error_msg)

    # Step 4: Log run
    elapsed_ms = int((time.time() - start_time) * 1000)
    stats["duration_ms"] = elapsed_ms
    await db.log_processing_run(stats)
    logger.info(f"Processing complete: {stats}")

    return stats


async def _process_single_email(raw_email: dict) -> dict | None:
    """Process a single email through the full pipeline."""
    # Extract standard fields
    fields = extract_email_fields(raw_email)
    message_id = fields["message_id"]
    thread_id = fields["thread_id"]

    if not message_id:
        return None

    # Skip if already processed
    if await db.is_email_processed(message_id):
        return None

    # Skip outbound / system emails
    if not is_inbound_customer_email(fields):
        return None

    customer_email = fields["from_email"]
    customer_name = fields["from_name"]
    subject = fields["subject"]
    body = fields["body"]

    logger.info(f"Processing email from {customer_email}: {subject}")

    # Step 3a: Get full thread context
    thread_emails = []
    if thread_id:
        thread_emails = await gmail.search_thread(thread_id)

    # Step 3b: Classify intent
    classification = classify_email(subject, body, thread_emails)
    category = classification["category"]
    logger.info(f"Classified as: {category} (confidence: {classification['confidence']})")

    # Skip spam
    if category == "spam":
        await db.save_processed_email({
            "message_id": message_id,
            "thread_id": thread_id,
            "from_email": customer_email,
            "from_name": customer_name,
            "subject": subject,
            "body": body,
            "received_at": fields["received_at"],
            "category": "spam",
            "status": "archived",
        })
        return {"drafted": False, "task_created": False}

    # Step 3c: Look up customer in Shopify
    order_summary = None
    shopify_order_id = None
    shopify_order_number = None

    # Try by email first
    orders = await shopify.lookup_customer_orders(customer_email)

    # If no orders by email, try by order number in subject/body
    if not orders:
        order_num = extract_order_number(f"{subject} {body}")
        if order_num:
            search_results = await shopify.search_orders(f"name:#{order_num}", max_results=1)
            if search_results:
                order_id = search_results[0].get("id")
                if order_id:
                    detail = await shopify.get_order(order_id)
                    if detail:
                        orders = [detail]

    # If no orders by order number, try by name
    if not orders and customer_name:
        name_parts = customer_name.split()
        if len(name_parts) >= 2:
            customers = await shopify.search_customers(
                f"first_name:{name_parts[0]} last_name:{name_parts[-1]}"
            )
            if customers:
                cust_orders = customers[0].get("orders", {})
                nodes = cust_orders.get("nodes", []) if isinstance(cust_orders, dict) else []
                for node in nodes[:3]:
                    oid = node.get("id")
                    if oid:
                        detail = await shopify.get_order(oid)
                        if detail:
                            orders.append(detail)

    # Step 3d: Get full order details
    if orders:
        # Use the most recent order
        order = orders[0]
        order_summary = extract_order_summary(order)
        shopify_order_id = order_summary.get("order_id")
        shopify_order_number = order_summary.get("order_number")

    # Step 3e: Search for other threads with same customer
    other_threads = []
    if customer_email:
        other_emails = await gmail.search_emails_from(customer_email)
        seen_threads = {thread_id}
        for email in other_emails:
            tid = email.get("threadId", email.get("thread_id", ""))
            if tid and tid not in seen_threads:
                seen_threads.add(tid)
                other_threads.append(extract_email_fields(email))

    # Step 3f: Check existing tasks for this customer
    existing_tasks = []
    if customer_email:
        existing_tasks = await db.find_tasks_for_customer(customer_email)

    # Step 3g: Apply rules engine
    rules_result = apply_rules(
        category=category,
        order_data=order_summary,
        thread_context=thread_emails,
        existing_tasks=existing_tasks,
    )

    # Step 3h: Generate draft via Claude
    draft_text = await generate_draft(
        customer_name=customer_name,
        customer_email=customer_email,
        subject=subject,
        category=category,
        rules_result=rules_result,
        order_summary=order_summary,
        thread_context=thread_emails,
        other_threads=other_threads,
        existing_tasks=existing_tasks,
    )

    # Step 3i: Create task if needed
    task_created = False
    if rules_result.get("create_task"):
        task_data = rules_result["create_task"]
        task_data["customer_email"] = customer_email
        task_data["customer_name"] = customer_name
        task_data["order_number"] = shopify_order_number
        task_data["email_id"] = message_id
        await db.create_task(task_data)
        task_created = True

    # Step 3j: Save to database
    await db.save_processed_email({
        "message_id": message_id,
        "thread_id": thread_id,
        "from_email": customer_email,
        "from_name": customer_name,
        "subject": subject,
        "body": body,
        "received_at": fields["received_at"],
        "category": category,
        "status": "draft_created" if draft_text else "pending",
        "shopify_order_id": shopify_order_id,
        "shopify_order_number": shopify_order_number,
        "shopify_data": order_summary,
        "draft_text": draft_text,
        "rules_applied": rules_result.get("rules", []),
        "thread_context": thread_emails,
    })

    return {
        "drafted": bool(draft_text),
        "task_created": task_created,
        "category": category,
        "customer": customer_email,
    }
