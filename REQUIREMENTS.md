# MIRA CS Agent v2 — Requirements & Architecture

## Overview
A Next.js web application deployed on Vercel that autonomously processes customer emails for team@trymira.com every 10 minutes, generates intelligent draft replies (never sends), and tracks pending tasks (ring exchanges, returns/refunds). The app uses the Perplexity connector APIs for Gmail and Shopify access (NOT direct API access — see Programmatic Tool Calling section).

## CRITICAL: Programmatic Tool Calling Architecture
This app does NOT directly call Gmail or Shopify APIs. Instead, it calls the Perplexity connector endpoints programmatically. The app needs to use the `programmatic-tool-calling` skill approach — making HTTP requests to the Perplexity external tool endpoints with a Perplexity API key.

### How Email Access Works
- Search emails: POST to connector endpoint with tool_name="search_email", source_id="gcal"
- Draft emails: POST to connector endpoint with tool_name="draft_email", source_id="gcal"

### How Shopify Access Works  
- Search orders: POST with tool_name="shopify_developer_app-search-orders", source_id="shopify_developer_app__pipedream"
- Get order details: POST with tool_name="shopify_developer_app-get-order", source_id="shopify_developer_app__pipedream"
- Search customers: POST with tool_name="shopify_developer_app-search-customers", source_id="shopify_developer_app__pipedream"

**Load the `programmatic-tool-calling` skill to understand the exact API format.**

## Key Design Principles
1. **Never send emails** — only create drafts for human review
2. **Full thread context** — always fetch and consider the entire email conversation
3. **Grounded in real data** — every response references actual Shopify order/shipping data
4. **Explicit rules engine** — business rules are hard-coded, not just LLM prompt
5. **Task tracking** — persistent tracking of ring exchanges, returns/refunds in progress
6. **Low credit usage** — use efficient LLM calls, cache Shopify data, batch where possible

## Business Rules (CRITICAL — these override any LLM tendency to hallucinate)

### Rule 1: Prescription Glasses Shipment Timeline
- All prescription glasses orders are now scheduled for **April** shipment
- Reason: Manufacturing delays + giving customers time to submit prescriptions
- Many customers needed extra time
- Response pattern: Apologize, explain April timeline, reassure tracking will be sent

### Rule 2: Ring Exchanges
- We need to **receive the old ring back before sending a new one**
- We just **ran out of rings** — next batch ships in **4-7 weeks**
- Process: Ask customer to confirm new size using insert card → arrange return of old ring → ship new ring when available
- Track these as tasks in the dashboard

### Rule 3: Returns/Refund Process (STRUCTURED — follow in order)
1. Customer expresses desire to return/cancel
2. **ASK** them to clarify what specifically isn't working (understand their frustration)
3. **WAIT** for their response (don't skip to step 4)
4. Once they respond with a reason (verify from thread context), **confirm** we'll send a return label
5. Refund is processed **after** we receive the glasses back
6. Track these as tasks in the dashboard

### Rule 4: Missing Ring Inquiries (Most Common)
- Rings are shipping separately due to manufacturing and customs delays
- Glasses work without the ring
- Include tutorial link: https://www.youtube.com/watch?v=7YrYoqvV8jA
- Ask them to use insert card to confirm ring size if they haven't
- We'll notify them when rings ship + send tracking

### Rule 5: Order Lookup Logic
1. Try matching by customer email address
2. If no match, try exact or very close name match
3. If still no match, draft asking customer to confirm order number
4. Always identify the subject/intent of the email before executing

### Rule 6: Delivery Status Inquiries
- Use Shopify fulfillment data: displayStatus (LABEL_PRINTED, IN_TRANSIT, DELIVERED)
- Use timestamps: estimatedDeliveryAt, inTransitAt, deliveredAt
- Carrier info from shippingLine.source (usps, fedex)
- NOTE: Tracking numbers are NOT available through the Shopify connector — reference the status and timestamps instead, and suggest checking their Shopify order confirmation email for tracking numbers

### Rule 7: Thread Context Awareness
- Before drafting any reply, review ALL emails in the thread
- Consider OTHER threads with the same customer (search by email)
- Don't repeat information already communicated
- Don't ask questions that have already been answered in the thread
- Match the conversational stage (new inquiry vs. follow-up vs. escalation)

## Response Tone & Style (learned from actual team@trymira.com emails)
- First-name basis: "Jeff," or "Merrick," (not "Dear Jeff" or "Hi Mr. Brown")
- Brief and direct — no long paragraphs
- Empathetic but not over-apologetic
- Sign off: "Best,\nTeam MIRA"
- Acknowledge delays honestly
- Offer something positive when delivering bad news (e.g., "Thankfully, the glasses work without the ring")
- For returns: try to understand and address concerns before processing
- Mention specific updates (increased query limits, premium access, etc.) when relevant to retention

## Shopify Data Available (from connector testing)

### search-orders
- Order number, financial status, fulfillment status
- Customer name, email, address
- Line items (product title, variant: Prescription/Non-prescription, quantity, price)
- Fulfillment summary (status only, no tracking)
- Metafields: halo_prescription.custom_data (ring size, prescription data)

### get-order (richer — use for detailed lookups)
- Everything above PLUS:
- Cancel reason/date, risk level
- Shipping carrier (shippingLine.source: "usps"/"fedex", shippingLine.title)
- Fulfillment timestamps: estimatedDeliveryAt, inTransitAt, deliveredAt
- displayStatus: LABEL_PRINTED, IN_TRANSIT, DELIVERED
- Transactions and refunds
- Billing address

### search-customers
- Customer ID, name, email, phone, addresses
- List of order IDs (need get-order for details)

## Web Dashboard Requirements

### Main View: Email Queue
- List of unread/pending customer emails
- For each: customer name, subject, order number (if found), category/intent
- Status: Pending Draft | Draft Created | Reviewed | Archived
- Click to expand full thread + generated draft

### Draft Review Panel
- Show the generated draft reply
- Show the email thread context
- Show Shopify order data that was referenced
- Show which rules were applied
- Edit draft inline before approving
- One-click: "Create Gmail Draft" (creates in Gmail for final send)

### Task Tracker
- **Ring Exchanges**: Customer name, email, order #, old size, new size, status (Awaiting Return | Received | Awaiting Stock | Shipped)
- **Returns/Refunds**: Customer name, email, order #, reason, status (Inquiry | Clarification Sent | Reason Received | Label Sent | Item Received | Refunded)
- **Prescription Orders**: Customer name, order #, prescription submitted (Y/N), estimated ship date

### Settings Panel
- Toggle auto-processing on/off
- Set processing interval (default 10 min)
- View processing logs
- Manual "Run Now" button

## Technical Architecture

### Stack
- Next.js 14 (App Router)
- Tailwind CSS + shadcn/ui components
- SQLite (via better-sqlite3 or Turso) for task tracking & processing state
- Vercel Cron for scheduled processing
- Anthropic Claude API (claude-3-5-haiku for cost efficiency) for draft generation

### API Routes
- POST /api/process — Main processing endpoint (called by cron)
- GET /api/emails — List pending/processed emails
- GET /api/emails/[id] — Get email details + thread + draft
- POST /api/drafts — Create/update draft
- POST /api/drafts/[id]/approve — Create Gmail draft
- GET /api/tasks — List all tasks
- POST /api/tasks — Create task
- PATCH /api/tasks/[id] — Update task status
- GET /api/settings — Get agent settings
- POST /api/settings — Update settings
- POST /api/run — Manual trigger

### Vercel Cron
```json
{
  "crons": [{
    "path": "/api/process",
    "schedule": "*/10 * * * *"
  }]
}
```

### Database Schema (SQLite / Turso)

```sql
-- Processed emails tracking
CREATE TABLE processed_emails (
  id TEXT PRIMARY KEY,
  thread_id TEXT,
  message_id TEXT,
  from_email TEXT,
  from_name TEXT,
  subject TEXT,
  received_at TEXT,
  category TEXT, -- 'return', 'ring_exchange', 'delivery_status', 'prescription', 'missing_ring', 'general', 'spam'
  status TEXT DEFAULT 'pending', -- 'pending', 'draft_created', 'reviewed', 'archived'
  shopify_order_id TEXT,
  shopify_order_number TEXT,
  draft_text TEXT,
  draft_gmail_id TEXT,
  rules_applied TEXT, -- JSON array of rule names
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Tasks for follow-ups
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL, -- 'ring_exchange', 'return_refund', 'prescription_followup'
  customer_email TEXT,
  customer_name TEXT,
  order_number TEXT,
  status TEXT NOT NULL,
  details TEXT, -- JSON with type-specific details
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Processing log
CREATE TABLE processing_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at TEXT DEFAULT CURRENT_TIMESTAMP,
  emails_found INTEGER,
  drafts_created INTEGER,
  tasks_created INTEGER,
  errors TEXT, -- JSON array
  duration_ms INTEGER
);

-- Settings
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
```

### Environment Variables
```
ANTHROPIC_API_KEY=          # For Claude draft generation
PPLX_API_KEY=               # For Perplexity connector API (Gmail + Shopify)
CRON_SECRET=                # Verify cron requests
```

### Processing Pipeline (each cron run)

1. **Fetch Unread Emails**: Search Gmail for unread emails to team@trymira.com
2. **Dedup**: Skip emails already in processed_emails table
3. **For each new email**:
   a. **Get full thread**: Search for all emails in same thread
   b. **Classify intent**: Determine category (return, ring exchange, delivery, etc.)
   c. **Lookup customer in Shopify**: By email first, then by name
   d. **Get order details**: If order found, fetch full order data including fulfillment status
   e. **Check for other threads**: Search for other emails from same customer
   f. **Check existing tasks**: Look for existing tasks for this customer
   g. **Apply rules engine**: Determine which rules apply based on category + context
   h. **Generate draft**: Send to Claude with full context + rules + order data
   i. **Create task if needed**: Ring exchange, return, etc.
   j. **Save to database**: Store processed email + draft + tasks

4. **Log run**: Record stats to processing_log

### LLM Prompt Strategy (to minimize hallucination)

The system prompt for Claude should be STRUCTURED, not conversational:

```
You are drafting a customer service email reply for MIRA, a smart glasses company.

RULES (these are absolute — never violate):
[Insert applicable rules based on classification]

ORDER DATA (this is factual — reference only this data):
[Insert Shopify order data]

THREAD CONTEXT (every message in chronological order):
[Insert full thread]

OTHER THREADS WITH THIS CUSTOMER:
[Insert other thread summaries]

EXISTING TASKS FOR THIS CUSTOMER:
[Insert any existing tasks]

INSTRUCTIONS:
- Draft a reply that follows the rules above
- Reference only the factual order data provided
- Match the tone: first-name, brief, empathetic, sign as "Team MIRA"
- If you're unsure about any factual claim, DO NOT include it
- If you need more info from the customer, ask specifically
```

## File Structure
```
mira-cs-agent-v2/
├── package.json
├── next.config.js
├── vercel.json
├── tailwind.config.js
├── .env.example
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              # Dashboard
│   │   ├── tasks/
│   │   │   └── page.tsx          # Task tracker
│   │   ├── settings/
│   │   │   └── page.tsx          # Settings
│   │   └── api/
│   │       ├── process/route.ts  # Cron endpoint
│   │       ├── emails/route.ts
│   │       ├── emails/[id]/route.ts
│   │       ├── drafts/route.ts
│   │       ├── drafts/[id]/approve/route.ts
│   │       ├── tasks/route.ts
│   │       ├── tasks/[id]/route.ts
│   │       ├── settings/route.ts
│   │       └── run/route.ts
│   ├── lib/
│   │   ├── connectors.ts         # Perplexity connector API wrapper
│   │   ├── gmail.ts              # Gmail operations via connector
│   │   ├── shopify.ts            # Shopify operations via connector
│   │   ├── classifier.ts         # Email intent classification
│   │   ├── rules-engine.ts       # Business rules application
│   │   ├── drafter.ts            # Claude draft generation
│   │   ├── db.ts                 # Database operations
│   │   └── processor.ts          # Main processing pipeline
│   └── components/
│       ├── email-list.tsx
│       ├── email-detail.tsx
│       ├── draft-editor.tsx
│       ├── task-list.tsx
│       ├── task-detail.tsx
│       ├── processing-log.tsx
│       └── nav.tsx
└── README.md
```
