"""Stdio transport only; the app's authentication and audit apply to every tool."""

from mcp.server import MCPServer

from .agent import call_tool

server = MCPServer("Research Desk")


@server.tool()
def dashboard() -> dict:
    """Read the explicit investor profile, dashboard and activity before doing research."""
    return call_tool("dashboard")


@server.tool()
def search_library(query: str = "", topic: str = "", ticker: str = "", source: str = "",
                   kind: str = "", date_from: str = "", date_to: str = "", limit: int = 20,
                   offset: int = 0) -> dict:
    """Search saved sources by text and metadata. Read original sources before citing them."""
    return call_tool("search_library", locals())


@server.tool()
def read_source(id: str, offset: int = 0, length: int = 20000) -> dict:
    """Read a source with citation metadata and pagination; follow next_offset for long records."""
    return call_tool("read_source", locals())


@server.tool()
def save_research(title: str, content: str, source_name: str = "Dot research", kind: str = "note",
                  url: str = "", tags: list[str] | None = None, tickers: list[str] | None = None,
                  ai_generated: bool = True, external_id: str | None = None) -> dict:
    """Save original collected content or a labelled analysis. Preserve source URL and provenance."""
    return call_tool("save_research", {**locals(), "tags": tags or [], "tickers": tickers or []})


@server.tool()
def organize_source(id: str, title: str | None = None, summary: str | None = None,
                    tags: list[str] | None = None, tickers: list[str] | None = None,
                    archived: bool | None = None) -> dict:
    """Organise a source without destroying original content; changes create a version record."""
    return call_tool("organize_source", {k: v for k, v in locals().items() if v is not None})


@server.tool()
def portfolio() -> dict:
    """Read holdings and watchlist. Quote dates and currency groups must accompany valuations."""
    return call_tool("portfolio")


@server.tool()
def save_stock(symbol: str, quote_symbol: str, category: str = "watchlist", shares: float = 0,
               currency: str = "USD", exchange: str = "US", average_cost: float | None = None,
               notes: str = "", id: str | None = None) -> dict:
    """Add/edit a recorded holding or watchlist stock. Does not place trades."""
    return call_tool("save_stock", locals())


@server.tool()
def tasks() -> list:
    """Read calendar tasks and their linked research."""
    return call_tool("tasks")


@server.tool()
def save_task(title: str, due_at: str, notes: str = "", done: bool = False,
              document_id: str | None = None, id: str | None = None) -> dict:
    """Add or update a review task. due_at must be ISO 8601 including timezone."""
    return call_tool("save_task", locals())


@server.tool()
def sources() -> list:
    """List registered source connections and retrieval status."""
    return call_tool("sources")


@server.tool()
def save_connection(name: str, kind: str, url: str = "", topics: list[str] | None = None,
                    enabled: bool = True, id: str | None = None) -> dict:
    """Register/edit an RSS, web, email or manual research source."""
    return call_tool("save_connection", {**locals(), "topics": topics or []})


@server.tool()
def refresh_source(id: str) -> dict:
    """Queue a registered RSS/Atom source retrieval. Inspect jobs for results."""
    return call_tool("refresh_source", locals())


@server.tool()
def refresh_quotes() -> dict:
    """Queue configured US quotes. Inspect the provider timestamp, currency and any errors."""
    return call_tool("refresh_quotes")


@server.tool()
def publish_digest(day: str, title: str, content: str, document_ids: list[str]) -> dict:
    """Publish an AI research digest, linking actual saved-source IDs. Cite passages, dates and uncertainty."""
    return call_tool("publish_digest", locals())


@server.tool()
def jobs() -> list:
    """Read import/retrieval progress, failures, duplicate counts and issues."""
    return call_tool("jobs")


@server.tool()
def activity(limit: int = 30) -> list:
    """Review recorded app, user and dot actions."""
    return call_tool("activity", locals())


@server.tool()
def prepare_import(path: str) -> dict:
    """Upload a chosen local research file and preview it. Does not start indexing."""
    return call_tool("prepare_import", locals())


@server.tool()
def start_import(upload_id: str, selected_ids: list[str] | None = None, include_files: bool = False) -> dict:
    """Import reviewed conversations/files. null selects all conversations; explicitly choose archive-file indexing."""
    return call_tool("start_import", locals())


@server.tool()
def workspace_action(action: str, arguments: dict) -> dict:
    """Less frequent operations: remove_stock, set_stock_price, remove_task, remove_connection,
    retry_job, undo_import, import_url, save_preferences, save_layout, reset_layout.
    Use only an operation authorised by the owner; app validation and audit apply."""
    allowed = {"remove_stock", "set_stock_price", "remove_task", "remove_connection", "retry_job",
               "undo_import", "import_url", "save_preferences", "save_layout", "reset_layout"}
    if action not in allowed:
        raise ValueError("Use the dedicated tool for this action")
    return call_tool(action, arguments)


def main():
    server.run()


if __name__ == "__main__":
    main()
