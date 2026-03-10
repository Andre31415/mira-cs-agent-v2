# MIRA CS Agent v2

Autonomous customer service email automation system for MIRA smart glasses.

## Features

- **Email Processing**: Fetches customer emails via Gmail, classifies intent, looks up Shopify orders, and generates draft replies using Claude AI
- **Rules Engine**: Hard-coded business rules for returns, ring exchanges, missing rings, prescriptions, and delivery status
- **Task Tracking**: Persistent tracking of ring exchanges, returns/refunds, and prescription follow-ups
- **Dashboard**: Dark-themed web UI for managing emails, tasks, and settings

## Architecture

- **Backend**: Python FastAPI on port 8000
- **Frontend**: Static HTML/CSS/JS with dark theme
- **Database**: SQLite for persistence
- **External APIs**: Gmail + Shopify via `external-tool` CLI, Anthropic Claude for drafting

## Setup

```bash
pip install -r requirements.txt
python server.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/process` | Process recent emails (auto) |
| POST | `/api/run` | Manual processing trigger |
| GET | `/api/emails` | List processed emails |
| GET | `/api/emails/:id` | Get email details |
| PATCH | `/api/emails/:id` | Update email status/draft |
| POST | `/api/drafts/:id/approve` | Create Gmail draft |
| POST | `/api/drafts/:id/regenerate` | Regenerate draft |
| GET | `/api/tasks` | List tasks |
| PATCH | `/api/tasks/:id` | Update task status |
| GET/POST | `/api/settings` | Get/update settings |
| GET | `/api/logs` | Processing logs |
| GET | `/api/stats` | Dashboard statistics |

## Business Rules

1. **Prescription glasses**: Ship in April (manufacturing delays)
2. **Ring exchanges**: Must return old ring first; out of stock 4-7 weeks
3. **Returns/refunds**: Ask why → wait for reason → confirm return label → refund after receipt
4. **Missing ring**: Ships separately; glasses work without it; share tutorial video
5. **Order lookup**: Match by email → name → ask for order number
6. **Delivery status**: Use Shopify fulfillment data (no tracking numbers via API)
7. **Thread context**: Review full thread history before drafting
