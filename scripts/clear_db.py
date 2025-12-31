"""
Interactively inspect and optionally clear the database.

Usage:
    python scripts/clear_db.py

The script shows row counts for core tables, then prompts for confirmation
before truncating them (with CASCADE).
"""

import asyncio
from typing import Iterable

from sqlalchemy import func, select, text
from sqlalchemy.engine.url import make_url

from app.config import settings
from app.db import models
from app.db.session import AsyncSessionLocal

TABLES: list[tuple[str, type]] = [
    ("raw_events", models.RawEvent),
    ("conversations", models.Conversation),
    ("participants", models.Participant),
    ("participant_aliases", models.ParticipantAlias),
    ("messages", models.Message),
    ("documents", models.Document),
    ("customers", models.Customer),
    ("participant_customer_map", models.ParticipantCustomerMap),
    ("audit_log", models.AuditLog),
    ("watchdog_runs", models.WatchdogRun),
]


def _safe_db_url() -> str:
    """Render the configured DB URL without leaking the password."""
    try:
        url = make_url(settings.DATABASE_URL)
        safe_url = url.set(password="***")
        return safe_url.render_as_string(hide_password=True)
    except Exception:
        return "<unable to parse DATABASE_URL>"


async def get_counts(session) -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    for table_name, model in TABLES:
        res = await session.execute(select(func.count()).select_from(model))
        counts.append((table_name, res.scalar_one()))
    return counts


def print_counts(counts: Iterable[tuple[str, int]]) -> None:
    print("\nCurrent row counts:")
    for name, count in counts:
        print(f"  - {name}: {count}")
    print("")


async def truncate_tables(session) -> None:
    # Use TRUNCATE ... CASCADE to satisfy FK constraints and reset IDs.
    table_names = ", ".join(name for name, _ in TABLES)
    stmt = text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE;")
    await session.execute(stmt)
    await session.commit()


async def main():
    print(f"Database target: {_safe_db_url()}")

    async with AsyncSessionLocal() as session:
        counts_before = await get_counts(session)
        print_counts(counts_before)

        confirm = input("Type 'yes' to clear all tables above (anything else to abort): ").strip().lower()
        if confirm != "yes":
            print("Aborted. No changes made.")
            return

        print("Clearing tables...")
        await truncate_tables(session)
        counts_after = await get_counts(session)
        print("Done. Counts after truncate:")
        print_counts(counts_after)


if __name__ == "__main__":
    asyncio.run(main())
