import argparse
import os
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient


DATE_FIELDS = {
    "creation_date",
    "assignment_date",
    "exit_date",
    "date",
}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(UTC).replace(tzinfo=None)

    return None


def _normalize_doc(ticket: dict[str, Any]) -> dict[str, Any]:
    updated: dict[str, Any] = {}

    creation_date = _parse_datetime(ticket.get("creation_date"))
    if creation_date is not None:
        if ticket.get("creation_date") != creation_date:
            updated["creation_date"] = creation_date

    comments = ticket.get("comments") or []
    updated_comments = []
    comments_changed = False
    for comment in comments:
        if not isinstance(comment, dict):
            updated_comments.append(comment)
            continue
        new_comment = dict(comment)
        if "date" in new_comment:
            normalized = _parse_datetime(new_comment.get("date"))
            if normalized is not None and new_comment.get("date") != normalized:
                new_comment["date"] = normalized
                comments_changed = True
        updated_comments.append(new_comment)

    if comments_changed:
        updated["comments"] = updated_comments

    history = ticket.get("agent_history") or []
    updated_history = []
    history_changed = False
    for entry in history:
        if not isinstance(entry, dict):
            updated_history.append(entry)
            continue
        new_entry = dict(entry)
        for field in ("assignment_date", "exit_date"):
            if field in new_entry:
                normalized = _parse_datetime(new_entry.get(field))
                if normalized is not None and new_entry.get(field) != normalized:
                    new_entry[field] = normalized
                    history_changed = True
        updated_history.append(new_entry)

    if history_changed:
        updated["agent_history"] = updated_history

    return updated


def _build_mongo_uri() -> str:
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    user = os.getenv("MONGO_USER", "")
    password = os.getenv("MONGO_PASSWORD", "")

    if user and password:
        return (
            f"mongodb://{user}:{password}@{host}:{port}/"
            "?authSource=admin"
        )
    return f"mongodb://{host}:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize ticket datetime fields to UTC naive datetimes."
    )
    parser.add_argument("--apply", action="store_true", help="Apply updates")
    args = parser.parse_args()

    db_name = os.getenv("MONGO_DB", "syncdesk_db")
    client = MongoClient(_build_mongo_uri())
    db = client[db_name]
    tickets = db["tickets"]

    scanned = 0
    updated = 0

    for ticket in tickets.find({}):
        scanned += 1
        changes = _normalize_doc(ticket)
        if not changes:
            continue
        updated += 1
        if args.apply:
            tickets.update_one({"_id": ticket["_id"]}, {"$set": changes})

    mode = "applied" if args.apply else "dry-run"
    print(f"Tickets scanned: {scanned}")
    print(f"Tickets needing updates: {updated}")
    print(f"Mode: {mode}")


if __name__ == "__main__":
    main()
