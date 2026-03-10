"""MIRA CS Agent v2 — FastAPI backend server."""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from lib import db, gmail, processor
from lib.classifier import classify_email, extract_email_fields
from lib.drafter import generate_draft
from lib.rules import apply_rules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await db.init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(title="MIRA CS Agent v2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# --- Frontend routes ---

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/tasks")
async def serve_tasks():
    return FileResponse(os.path.join(FRONTEND_DIR, "tasks.html"))


@app.get("/settings")
async def serve_settings():
    return FileResponse(os.path.join(FRONTEND_DIR, "settings.html"))


# --- API: Processing ---

@app.post("/api/process")
async def api_process():
    """Main processing endpoint — processes recent emails."""
    try:
        settings = await db.get_settings()
        auto = settings.get("auto_processing", "true")
        # Always allow manual trigger, only check auto for cron
        result = await processor.process_emails(hours=24)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/run")
async def api_manual_run():
    """Manual trigger for processing."""
    try:
        result = await processor.process_emails(hours=48)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Manual run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- API: Emails ---

@app.get("/api/emails")
async def api_get_emails(status: str | None = None, limit: int = 50, offset: int = 0):
    """List processed emails."""
    emails = await db.get_emails(status=status, limit=limit, offset=offset)
    # Parse JSON fields for the response
    for email in emails:
        for field in ["shopify_data", "rules_applied", "thread_context"]:
            if email.get(field) and isinstance(email[field], str):
                try:
                    email[field] = json.loads(email[field])
                except json.JSONDecodeError:
                    pass
    return JSONResponse(emails)


@app.get("/api/emails/{email_id}")
async def api_get_email(email_id: str):
    """Get a single email with full details."""
    email = await db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    for field in ["shopify_data", "rules_applied", "thread_context"]:
        if email.get(field) and isinstance(email[field], str):
            try:
                email[field] = json.loads(email[field])
            except json.JSONDecodeError:
                pass
    return JSONResponse(email)


@app.patch("/api/emails/{email_id}")
async def api_update_email(email_id: str, request: Request):
    """Update email status or draft."""
    body = await request.json()
    email = await db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if "status" in body:
        await db.update_email_status(email_id, body["status"])
    if "draft_text" in body:
        await db.update_email_draft(email_id, body["draft_text"])

    return JSONResponse({"ok": True})


# --- API: Drafts ---

@app.post("/api/drafts/{email_id}/approve")
async def api_approve_draft(email_id: str):
    """Create a Gmail draft from the approved draft text."""
    email = await db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if not email.get("draft_text"):
        raise HTTPException(status_code=400, detail="No draft text to approve")

    try:
        result = await gmail.create_draft(
            reply_to_email_id=email["message_id"],
            thread_id=email["thread_id"],
            to=[email["from_email"]],
            subject=f"Re: {email['subject']}" if not email["subject"].startswith("Re:") else email["subject"],
            body=email["draft_text"],
        )
        draft_gmail_id = result.get("id", result.get("draft_id", ""))
        await db.update_email_draft(email_id, email["draft_text"], draft_gmail_id)
        await db.update_email_status(email_id, "reviewed")
        return JSONResponse({"ok": True, "gmail_draft_id": draft_gmail_id})
    except Exception as e:
        logger.error(f"Draft approval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/drafts/{email_id}/regenerate")
async def api_regenerate_draft(email_id: str):
    """Regenerate a draft for an email."""
    email = await db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Re-classify and re-draft
    classification = classify_email(email["subject"], email.get("body", ""))
    category = classification["category"]

    # Parse existing data
    order_data = email.get("shopify_data")
    if isinstance(order_data, str):
        try:
            order_data = json.loads(order_data)
        except json.JSONDecodeError:
            order_data = None

    thread_context = email.get("thread_context")
    if isinstance(thread_context, str):
        try:
            thread_context = json.loads(thread_context)
        except json.JSONDecodeError:
            thread_context = None

    existing_tasks = await db.find_tasks_for_customer(email["from_email"]) if email.get("from_email") else []

    rules_result = apply_rules(
        category=category,
        order_data=order_data,
        thread_context=thread_context,
        existing_tasks=existing_tasks,
    )

    draft_text = await generate_draft(
        customer_name=email.get("from_name", ""),
        customer_email=email.get("from_email", ""),
        subject=email.get("subject", ""),
        category=category,
        rules_result=rules_result,
        order_summary=order_data,
        thread_context=thread_context,
        existing_tasks=existing_tasks,
    )

    await db.update_email_draft(email_id, draft_text)
    return JSONResponse({"ok": True, "draft_text": draft_text})


# --- API: Tasks ---

@app.get("/api/tasks")
async def api_get_tasks(type: str | None = None, limit: int = 50):
    """List tasks, optionally filtered by type."""
    tasks = await db.get_tasks(task_type=type, limit=limit)
    for task in tasks:
        if task.get("details") and isinstance(task["details"], str):
            try:
                task["details"] = json.loads(task["details"])
            except json.JSONDecodeError:
                pass
    return JSONResponse(tasks)


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: int):
    """Get a single task."""
    task = await db.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("details") and isinstance(task["details"], str):
        try:
            task["details"] = json.loads(task["details"])
        except json.JSONDecodeError:
            pass
    return JSONResponse(task)


@app.patch("/api/tasks/{task_id}")
async def api_update_task(task_id: int, request: Request):
    """Update a task's status or details."""
    body = await request.json()
    task = await db.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.update_task(task_id, body)
    return JSONResponse({"ok": True})


# --- API: Settings ---

@app.get("/api/settings")
async def api_get_settings():
    """Get all settings."""
    settings = await db.get_settings()
    return JSONResponse(settings)


@app.post("/api/settings")
async def api_update_settings(request: Request):
    """Update settings."""
    body = await request.json()
    for key, value in body.items():
        await db.update_setting(key, str(value))
    return JSONResponse({"ok": True})


# --- API: Processing Logs ---

@app.get("/api/logs")
async def api_get_logs(limit: int = 20):
    """Get recent processing logs."""
    logs = await db.get_processing_logs(limit=limit)
    for log in logs:
        if log.get("errors") and isinstance(log["errors"], str):
            try:
                log["errors"] = json.loads(log["errors"])
            except json.JSONDecodeError:
                pass
    return JSONResponse(logs)


# --- API: Stats ---

@app.get("/api/stats")
async def api_get_stats():
    """Get dashboard stats."""
    all_emails = await db.get_emails(limit=1000)
    all_tasks = await db.get_tasks(limit=1000)

    status_counts = {}
    category_counts = {}
    for e in all_emails:
        s = e.get("status", "unknown")
        c = e.get("category", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
        category_counts[c] = category_counts.get(c, 0) + 1

    task_type_counts = {}
    task_status_counts = {}
    for t in all_tasks:
        tt = t.get("type", "unknown")
        ts = t.get("status", "unknown")
        task_type_counts[tt] = task_type_counts.get(tt, 0) + 1
        task_status_counts[ts] = task_status_counts.get(ts, 0) + 1

    return JSONResponse({
        "total_emails": len(all_emails),
        "total_tasks": len(all_tasks),
        "email_statuses": status_counts,
        "email_categories": category_counts,
        "task_types": task_type_counts,
        "task_statuses": task_status_counts,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
