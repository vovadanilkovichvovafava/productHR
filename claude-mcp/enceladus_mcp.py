#!/usr/bin/env python3
"""Enceladus MCP server — exposes Enceladus task creation to Claude Code / Desktop.

Setup
-----
1. Install dependencies:
       pip install "mcp[cli]" httpx

2. Generate an API token in Enceladus:
       curl -X POST https://enceladus-ns9s2o.saturn.ac/api/integrations/api-tokens \\
            -H "Cookie: <your login cookie>" \\
            -H "Content-Type: application/json" \\
            -d '{"name": "Claude on my laptop"}'
   Copy the `token` field from the response (shown ONCE).

3. Add to your Claude Code config (~/.claude.json or via /mcp):
       {
         "mcpServers": {
           "enceladus": {
             "command": "python3",
             "args": ["/absolute/path/to/enceladus_mcp.py"],
             "env": {
               "ENCELADUS_URL": "https://enceladus-ns9s2o.saturn.ac",
               "ENCELADUS_TOKEN": "enc_xxxxxxxxxxxx..."
             }
           }
         }
       }

4. Restart Claude Code. Try: "List my Enceladus projects" or
   "Create a task in Saturn: fix the broken healthcheck."

Tools exposed
-------------
- `list_projects` — show all projects in the workspace.
- `create_enceladus_task` — create one or more tasks from NL text. Same
  pipeline as the Telegram bot (`/blocker`, status reports), so project
  matching tolerates Cyrillic ↔ Latin (Сатурн ↔ Saturn) and typos.
"""
import asyncio
import os
import sys
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


BASE = os.environ.get("ENCELADUS_URL", "").rstrip("/")
TOKEN = os.environ.get("ENCELADUS_TOKEN", "")
if not BASE or not TOKEN:
    print(
        "ERROR: ENCELADUS_URL and ENCELADUS_TOKEN env vars are required.",
        file=sys.stderr,
    )
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}
server = Server("enceladus")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_projects",
            description=(
                "List all projects in the user's Enceladus workspace. "
                "Use this to disambiguate when the user mentions a project "
                "by an approximate or partial name."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="create_enceladus_task",
            description=(
                "Create one or more tasks in an Enceladus project from a "
                "natural-language description. Pass the project name in "
                "`project_hint` for reliable matching. The server matches "
                "the project tolerantly (Cyrillic ↔ Latin, minor typos) "
                "and uses the same task-extraction pipeline as the team's "
                "Telegram bot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": (
                            "Natural-language description of what needs to "
                            "be done. May include the project name inline."
                        ),
                    },
                    "project_hint": {
                        "type": "string",
                        "description": (
                            "Project name (e.g. 'Saturn'). Optional but "
                            "strongly recommended — improves matching."
                        ),
                    },
                },
                "required": ["message"],
            },
        ),
    ]


async def _list_projects() -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BASE}/api/integrations/projects", headers=HEADERS)
        r.raise_for_status()
        projects = r.json()
    if not projects:
        return "No projects found in your workspace."
    lines = ["Projects:"]
    for p in projects:
        desc = f" — {p['description']}" if p.get("description") else ""
        lines.append(f"  #{p['id']}  {p['name']}{desc}")
    return "\n".join(lines)


async def _create_task(message: str, project_hint: Optional[str]) -> str:
    payload = {"message": message}
    if project_hint:
        payload["project_hint"] = project_hint
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{BASE}/api/integrations/create-task",
            headers=HEADERS,
            json=payload,
        )
    if r.status_code == 422:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        return f"Could not extract a task. {detail}"
    if r.status_code >= 400:
        return f"Error {r.status_code}: {r.text[:500]}"
    created = r.json().get("created", [])
    if not created:
        return "Server accepted the request but created no tasks."
    lines = ["Created:"]
    for t in created:
        key = t.get("task_key") or f"#{t.get('task_id')}"
        assignee = t.get("assignee") or "—"
        lines.append(f"  ✓ {key} «{t['title']}» → {t['project']} (assignee: {assignee})")
    return "\n".join(lines)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "list_projects":
            text = await _list_projects()
        elif name == "create_enceladus_task":
            text = await _create_task(
                message=arguments["message"],
                project_hint=arguments.get("project_hint"),
            )
        else:
            text = f"Unknown tool: {name}"
    except httpx.HTTPError as e:
        text = f"Network error: {type(e).__name__}: {e}"
    except Exception as e:
        text = f"Error: {type(e).__name__}: {e}"
    return [TextContent(type="text", text=text)]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
