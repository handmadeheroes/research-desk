import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from .db import connect, get_setting, now, set_setting
from .jobs import publish_digest
from .library import save_document


def seed_demo():
    if get_setting("demo", False):
        return
    ids = []
    for title, kind, source, text, tags in [
        ("Cloud earnings call — transcript", "transcript", "Sample investor relations",
         "DEMONSTRATION ONLY. Compare Microsoft cloud margin commentary and capital expenditure assumptions. "
         "This is illustrative source text for exploring the interface, not an actual earnings transcript.",
         ["Cloud", "Earnings"]),
        ("Weekly macro briefing", "email", "Sample newsletter",
         "DEMONSTRATION ONLY. A research checklist covering inflation, interest rates and portfolio exposure. "
         "Verify current figures against original publications before forming a view.", ["Macro", "Rates"]),
        ("Semiconductor supply chain review", "article", "Sample research article",
         "DEMONSTRATION ONLY. Compare Nvidia demand commentary across independent sources. "
         "Separate reported facts, forecasts and assumptions in each investment thesis.", ["AI", "Semiconductors"]),
        ("Portfolio thesis — October", "note", "Sample manual upload",
         "DEMONSTRATION ONLY. Document the thesis, supporting evidence, risks, invalidation conditions and "
         "the date for the next portfolio review.", ["Portfolio"]),
    ]:
        item, _ = save_document(title=title, content=text, kind=kind, source_name=source, tags=tags,
                                external_id="demo:" + title, demo=True, actor="System")
        ids.append(item["id"])
    with connect() as db:
        for symbol, shares, cost, price, previous in [
            ("AAPL", 20, 180, 228.40, 226.50), ("MSFT", 10, 400, 462.10, 459.25),
            ("NVDA", 0, None, 182.30, 182.87),
        ]:
            db.execute("INSERT OR IGNORE INTO stocks(id,symbol,quote_symbol,exchange,currency,category,shares,"
                       "average_cost,last_price,previous_price,price_at,provider,demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
                       (uuid.uuid4().hex, symbol, symbol.lower() + ".us", "US", "USD",
                        "holding" if shares else "watchlist", shares, cost, price, previous,
                        now()[:10], "Sample data"))
        task_ids = []
        current = datetime.now(ZoneInfo(get_setting("timezone")))
        for title, hour in [("Review portfolio exposure", 10), ("Read saved earnings notes", 14)]:
            identity = uuid.uuid4().hex
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                       (identity, title, current.replace(hour=hour, minute=0, second=0).isoformat(), 0, "", ids[0], now()))
            task_ids.append(identity)
    content = "# Your morning brief\n\n> DEMONSTRATION DATA · Illustrative research only.\n\n"
    for title, description, identity in zip(
        ["AI infrastructure spending", "Rates and portfolio exposure", "Items needing a closer look"],
        ["Compare capex commentary across the latest earnings notes.",
         "Review the implications of rate changes for your watchlist.",
         "Compare differing outlooks and identify assumptions to verify."], ids,
    ):
        content += "## " + title + "\n\n" + description + "\n\n[Read saved source](#document/" + identity + ")\n\n"
    digest_id = publish_digest(current.date().isoformat(), "Your morning brief", content, ids[:3], "Sample digest", "System")
    set_setting("demo_tasks", task_ids)
    set_setting("demo_digests", [digest_id])
    set_setting("demo", True)
