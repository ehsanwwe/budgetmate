"""
Cleanup script for duplicate future_commitments created by the history-replay bug
(Phase 5.7 fix). This bug caused the same commitment (e.g. "ماشین لباسشویی") to be
inserted multiple times because prior chat turns triggered re-execution.

Run ONCE after deploying the Phase 5.7 backend fix:
    cd backend
    python scripts/cleanup_duplicate_commitments.py [--dry-run] [--user-id N]

Safety:
- Dry-run by default (pass --execute to actually delete).
- Keeps the OLDEST row (lowest id) per (user_id, title, amount) group.
- Never touches the goals table.
- Prints a full diff of what it will delete before doing anything.
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running from repo root or backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.future_commitment import FutureCommitment


def find_duplicates(session, user_id: int | None = None):
    """Return groups with more than one row sharing (user_id, title, amount)."""
    q = (
        session.query(
            FutureCommitment.user_id,
            FutureCommitment.title,
            FutureCommitment.amount,
            func.count(FutureCommitment.id).label("cnt"),
            func.min(FutureCommitment.id).label("keep_id"),
        )
        .group_by(FutureCommitment.user_id, FutureCommitment.title, FutureCommitment.amount)
        .having(func.count(FutureCommitment.id) > 1)
    )
    if user_id is not None:
        q = q.filter(FutureCommitment.user_id == user_id)
    return q.all()


def main():
    parser = argparse.ArgumentParser(description="Remove duplicate future_commitments from history-replay bug")
    parser.add_argument("--execute", action="store_true", help="Actually delete rows (default: dry-run)")
    parser.add_argument("--user-id", type=int, default=None, help="Restrict to a single user_id")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL or "sqlite:///./budgetmate.db", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    session = Session()

    groups = find_duplicates(session, args.user_id)
    if not groups:
        print("No duplicates found.")
        return

    total_to_delete = 0
    for row in groups:
        dupes = (
            session.query(FutureCommitment)
            .filter(
                FutureCommitment.user_id == row.user_id,
                FutureCommitment.title == row.title,
                FutureCommitment.amount == row.amount,
                FutureCommitment.id != row.keep_id,
            )
            .all()
        )
        print(f"\n[user={row.user_id}] title='{row.title}' amount={row.amount:,} — keeping id={row.keep_id}, deleting {len(dupes)} duplicate(s):")
        for d in dupes:
            print(f"  DELETE id={d.id} created_at={d.created_at} status={d.status}")
            total_to_delete += 1
        if args.execute:
            for d in dupes:
                session.delete(d)

    print(f"\n{'[DRY RUN] Would delete' if not args.execute else 'Deleted'} {total_to_delete} duplicate future_commitment row(s).")

    if args.execute:
        session.commit()
        print("Committed.")
    else:
        print("Re-run with --execute to apply deletions.")

    session.close()


if __name__ == "__main__":
    main()
