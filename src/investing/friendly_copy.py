"""Plain-English labels and user-safe error messages."""

from __future__ import annotations

TERM_HELP = {
    "xirr": (
        "Annual growth rate of your money, accounting for when you invested. "
        "Think of it as “how hard your portfolio worked per year.”"
    ),
    "cagr": (
        "Average yearly growth over a period, as if growth were steady each year. "
        "Useful for comparing mutual funds."
    ),
    "nav": "Net Asset Value — the price of one unit of a mutual fund.",
    "pnl": "Profit or loss — how much you are up or down in rupees.",
    "benchmark": "A market index (e.g. Nifty 50) used to compare how you did versus the broader market.",
    "sebi_category": "The official fund type assigned by regulators (e.g. Large Cap, Flexi Cap).",
}


def friendly_import_error(kind: str, detail: str | None = None) -> str:
    guides = {
        "equity-holdings": (
            "We could not read this equity holdings file. "
            "In Zerodha Console go to **Reports → Holdings → Equity**, export CSV or Excel, "
            "and upload that file without editing it."
        ),
        "tradebook": (
            "We could not read this tradebook file. "
            "In Console go to **Reports → Tradebook**, pick a date range, export CSV/Excel, "
            "and upload it here."
        ),
        "mf-holdings": (
            "We could not read this mutual fund file. "
            "In Console go to **Reports → Holdings → Mutual funds**, export, and upload."
        ),
        "mf-transactions": (
            "We could not read this mutual fund transaction file. "
            "In Zerodha Coin or Console export your **MF transaction / SIP history** "
            "(CSV or Excel) and upload it without editing."
        ),
        "cas": (
            "We could not read this CAS file. Use the **original** CAMS/KFintech PDF "
            "with its password, or a CSV export from a CAS parser tool."
        ),
        "mf-disclosure": (
            "We could not read this portfolio disclosure. Use the monthly Excel/CSV "
            "from your AMC with ISIN and % to NAV columns (one scheme per file)."
        ),
    }
    base = guides.get(kind, "We could not import this file. Please use a Zerodha Console export.")
    if detail:
        short = detail.strip().splitlines()[0][:120]
        return f"{base} (Details: {short})"
    return base


def friendly_runtime_error(error: BaseException) -> str:
    text = str(error).strip()
    lowered = text.lower()
    if "database" in lowered and "locked" in lowered:
        return "The app is still saving your data. Wait a moment and refresh the page."
    if "timeout" in lowered or "timed out" in lowered:
        return "The market data website took too long to respond. Try again in a minute."
    if "connection" in lowered or "network" in lowered:
        return "We could not reach the internet. Check your connection and try again."
    if "yahoo" in lowered or "finance" in lowered:
        return "Live share prices are temporarily unavailable. Your uploaded holdings are still saved."
    if "amfi" in lowered or "mfapi" in lowered:
        return "Mutual fund data is temporarily unavailable. Try again later or use the demo portfolio."
    if text:
        return (
            "Something went wrong on our side. Your files are usually still safe. "
            f"If this keeps happening, note this message: {text[:160]}"
        )
    return "Something went wrong. Please refresh the page and try again."
