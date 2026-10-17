"""Authenticated local tools. Tokens are read from local storage, never placed in prompts."""

import argparse
import json
import os
from pathlib import Path

import httpx

from .db import data_dir

TOOLS = {
    "dashboard": "Read dashboard, explicit investor profile and recent activity.",
    "search_library": "Search library: query, topic, ticker, source, kind, date_from, date_to, limit, offset.",
    "read_source": "Read a saved source: id, offset=0, length=20000. Returns next_offset for long documents.",
    "save_research": "Save title, content, kind, source_name, url, tags, tickers, summary, ai_generated (default true), external_id.",
    "organize_source": "Update a source's id, title, summary, tags, tickers or archived flag. Original versions retained.",
    "portfolio": "Read holdings, watchlist and timestamped prices grouped by currency.",
    "save_stock": "Create/update stock: optional id; symbol, quote_symbol, exchange, currency, category, shares, average_cost, notes.",
    "remove_stock": "Remove stock by id; app audit retains previous values.",
    "refresh_quotes": "Queue Stooq US daily quote refresh. Prices are not live; inspect job results.",
    "tasks": "Read calendar tasks.",
    "save_task": "Create/update task: optional id; title, due_at (ISO with timezone), notes, done, document_id.",
    "sources": "List registered sources and retrieval status.",
    "save_connection": "Create/update source: optional id; name, kind (rss/web/email/manual), url, topics, enabled.",
    "refresh_source": "Queue RSS/Atom retrieval: id.",
    "publish_digest": "Publish cited research: day YYYY-MM-DD, title, content Markdown, document_ids (required saved-source IDs).",
    "digests": "Read saved digest history.",
    "activity": "Read actions: optional q, actor_filter, limit, offset.",
    "jobs": "Read import/feed/quote jobs and issues.",
    "prepare_import": "Upload a local file path and preview its conversations/files. No indexing yet.",
    "start_import": "Index a reviewed upload: upload_id, selected_ids (null=all), include_files (explicit).",
    "set_stock_price": "Save a manual quote: id, price, previous_price (optional), as_of ISO date/time.",
    "remove_task": "Remove a calendar task: id.",
    "remove_connection": "Remove a source connection, retaining research: id.",
    "retry_job": "Retry a failed/partial background job: id.",
    "undo_import": "Archive new unchanged records created by a completed import: id.",
    "import_url": "Queue public article retrieval: url, source_name (optional), title (optional).",
    "save_preferences": "Save explicit profile/preferences: timezone, digest_time, profile, dot_url.",
    "save_layout": "Save all six cards: layout list of id,x,y,w,h with 12-column coordinates.",
    "reset_layout": "Restore the original approved dashboard arrangement.",
}


def request(method, route, body=None, params=None, file_path=None):
    token_path = data_dir() / "agent-token"
    if not token_path.exists():
        raise ValueError("Run the app installer first, using the same RD_DATA_DIR.")
    token = token_path.read_text().strip()
    base = os.getenv("RD_AGENT_URL", "http://127.0.0.1:" + os.getenv("RD_PORT", "8401"))
    # The credential must never be sent to an arbitrary endpoint.
    from urllib.parse import urlsplit
    parts = urlsplit(base)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1") or parts.username or parts.password:
        raise ValueError("The local dot client only connects to a loopback HTTP app URL.")
    with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + token}, timeout=180,
                      trust_env=False) as client:
        if file_path:
            with Path(file_path).expanduser().open("rb") as file:
                response = client.request(method, "/api" + route, files={"file": (Path(file_path).name, file)})
        else:
            response = client.request(method, "/api" + route, json=body, params=params)
        if not response.is_success:
            raise ValueError(str(response.json().get("detail", "App request failed"))[:500])
        return response.json()


def call_tool(name, arguments=None):
    args = dict(arguments or {})
    if name not in TOOLS:
        raise ValueError("Unknown tool. Run tools to list available actions.")
    gets = {"dashboard": "/bootstrap", "portfolio": "/stocks", "tasks": "/tasks", "sources": "/sources",
            "activity": "/activity", "jobs": "/jobs", "digests": "/digests"}
    if name in gets:
        result = request("GET", gets[name], params=args)
        if name == "dashboard":
            result.pop("csrf", None)
        return result
    if name == "search_library":
        if "query" in args:
            args["q"] = args.pop("query")
        return request("GET", "/documents", params=args)
    if name == "read_source":
        identity = args.pop("id")
        offset = max(0, int(args.pop("offset", 0)))
        length = min(50000, max(100, int(args.pop("length", 20000))))
        result = request("GET", "/documents/" + identity)
        content = result["content"]
        result["content"] = content[offset:offset + length]
        result["next_offset"] = offset + length if offset + length < len(content) else None
        result["total_characters"] = len(content)
        result["citation"] = {"id": result["id"], "title": result["title"], "url": result["url"],
                              "published_at": result["published_at"], "research_date": result["created_at"]}
        return result
    if name == "save_research":
        args.setdefault("ai_generated", True)
        args.setdefault("source_name", "Dot research")
        return request("POST", "/documents", args)
    if name == "organize_source":
        identity = args.pop("id")
        return request("PATCH", "/documents/" + identity, args)
    if name in ("save_stock", "save_task", "save_connection"):
        route = {"save_stock": "/stocks", "save_task": "/tasks", "save_connection": "/sources"}[name]
        identity = args.pop("id", None)
        return request("PUT" if identity else "POST", route + ("/" + identity if identity else ""), args)
    if name == "remove_stock":
        return request("DELETE", "/stocks/" + args["id"])
    if name == "refresh_quotes":
        return request("POST", "/quotes/refresh", {})
    if name == "refresh_source":
        return request("POST", "/sources/" + args["id"] + "/refresh", {})
    if name == "publish_digest":
        return request("POST", "/digests", args)
    if name == "prepare_import":
        return request("POST", "/imports/preview", file_path=args["path"])
    if name == "start_import":
        return request("POST", "/imports", args)
    if name in ("remove_task", "remove_connection"):
        route = "/tasks/" if name == "remove_task" else "/sources/"
        return request("DELETE", route + args["id"])
    if name == "set_stock_price":
        identity = args.pop("id")
        return request("POST", "/stocks/" + identity + "/price", args)
    if name in ("retry_job", "undo_import"):
        return request("POST", "/jobs/" + args["id"] + ("/retry" if name == "retry_job" else "/undo"), {})
    if name == "import_url":
        return request("POST", "/import-url", args)
    if name == "save_preferences":
        return request("PUT", "/preferences", args)
    if name == "save_layout":
        return request("PUT", "/layout", args["layout"])
    if name == "reset_layout":
        return request("POST", "/layout/reset", {})
    raise ValueError("Unsupported tool")


def main():
    parser = argparse.ArgumentParser(description="Research Desk tools for your connected dot")
    parser.add_argument("command", choices=["tools", "call"])
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--json", default="{}")
    parser.add_argument("--input", help="Read JSON arguments from a file; useful for long research notes")
    args = parser.parse_args()
    try:
        if args.command == "tools":
            print(json.dumps(TOOLS, indent=2))
        else:
            values = json.loads(Path(args.input).read_text() if args.input else args.json)
            print(json.dumps(call_tool(args.tool, values), ensure_ascii=False, indent=2))
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.exit(1, "Research Desk: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
