# AimHarder MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives AI agents direct access to your AimHarder box — list classes, book spots, cancel bookings, and find who's attending.

> **Requires Python 3.10+.** The `mcp` package does not support Python 3.9.

## Features

| Tool | Description |
|---|---|
| `list_classes` | List all classes for a date |
| `book_class` | Book a class by ID |
| `cancel_booking` | Cancel an existing booking |
| `get_wod` | Fetch the Workout of the Day |
| `get_my_bookings` | List your upcoming booked classes |
| `get_wod` | Fetch the Workout of the Day |

---

## Installation

```bash
cd mcp_server
# Create a Python 3.10+ virtual environment (3.11 shown here)
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Install the MCP package with CLI extras
.venv/bin/pip install "mcp[cli]"
```

### Environment variables

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

```
EMAIL=your@email.com
PASSWORD=your_aimharder_password
BOX_NAME=your_box_name       # subdomain of your box's URL
BOX_ID=your_box_id           # numeric ID from the Aimharder dashboard
```

> How to find your `BOX_ID`: open your box's AimHarder URL, open DevTools → Network,
> and look for requests to `/api/bookings?box=<ID>`.

---

## Running

### stdio (Claude Desktop / Cursor)

```bash
.venv/bin/python server.py
```

### SSE (web / HTTP clients)

```bash
.venv/bin/python server.py --transport sse --port 8000
```

---

## Claude Desktop configuration

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aimharder": {
      "command": "/path/to/mcp-server/.venv/bin/python",
      "args": ["/path/to/mcp-server/server.py"],
      "env": {
        "EMAIL": "your@email.com",
        "PASSWORD": "your_password",
        "BOX_NAME": "your_box_name",
        "BOX_ID": "your_box_id"
      }
    }
  }
}
```

Restart Claude Desktop. The AimHarder tools will appear under the 🔌 icon.

---

## Cursor / VS Code configuration

Add to your `.cursor/mcp.json` (or equivalent):

```json
{
  "mcpServers": {
    "aimharder": {
      "command": "/path/to/mcp-server/.venv/bin/python",
      "args": ["/path/to/mcp-server/server.py"],
      "env": {
        "EMAIL": "your@email.com",
        "PASSWORD": "your_password",
        "BOX_NAME": "your_box_name",
        "BOX_ID": "your_box_id"
      }
    }
  }
}
```

---

## Development & Testing

Use the MCP Inspector to test tools interactively:

```bash
# Install the inspector globally
npx @modelcontextprotocol/inspector .venv/bin/python server.py
```

Or call a quick syntax/import check:

```bash
.venv/bin/python -c "import server; print('OK')"
```

---

## Example prompts (once connected to Claude)

- *"What CrossFit classes are available tomorrow?"*
- *"What is tomorrow's WOD?"*
- *"What classes am I signed up for this week?"*
- *"What is tomorrow's WOD?"*
- *"Book the 19:00 class on 2026-03-25 (class ID 12345)."*
- *"Cancel my booking for class ID 12345 on 2026-03-25."*
