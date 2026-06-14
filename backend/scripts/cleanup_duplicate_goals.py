"""
Cleanup script for duplicate active goals.

Groups active goals by (user_id, normalized_title, target_amount, deadline)
and archives all but the earliest (by id) in each duplicate group.

Usage:
  cd backend
  python scripts/cleanup_duplicate_goals.py           # dry-run (safe, default)
  python scripts/cleanup_duplicate_goals.py --apply   # archive duplicates

Never hard-deletes any goal. Use --apply only after reviewing dry-run output.
"""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.goal import Goal
from app.services.personal_cfo.goal_context_service import normalize_goal_text


def find_duplicate_groups(session):
    active_goals = (
        session.query(Goal)
        .filter(Goal.is_active == True)
        .order_by(Goal.user_id, Goal.id)
        .all()
    )
    groups: dict[tuple, list[Goal]] = {}
    for goal in active_goals:
        key = (
            goal.user_id,
            normalize_goal_text(goal.title),
            int(goal.target_amount or 0),
            goal.deadline.isoformat() if goal.deadline else None,
        )
        groups.setdefault(key, []).append(goal)
    return {k: v for k, v in groups.items() if len(v) > 1}


def main():
    parser = argparse.ArgumentParser(description="Cleanup duplicate active goals")
    parser.add_argument("--apply", action="store_true", help="Archive duplicates (default: dry-run)")
    args = parser.parse_args()

    db_url = settings.DATABASE_URL or "sqlite:///./budgetmate.db"
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        duplicates = find_duplicate_groups(session)
        if not duplicates:
            print("No duplicate active goals found.")
            return

        print(f"Found {len(duplicates)} duplicate group(s):\n")
        archived = 0
        for (user_id, norm_title, amount, deadline), goals in duplicates.items():
            keep = goals[0]  # earliest by id
            to_archive = goals[1:]
            print(f"  User {user_id} | '{norm_title}' | {amount:,} تومان | deadline={deadline}")
            print(f"    KEEP    id={keep.id} title='{keep.title}'")
            for g in to_archive:
                print(f"    ARCHIVE id={g.id} title='{g.title}'")
                if args.apply:
                    g.is_active = False
                    g.status = "archived"
                    archived += 1
            print()

        if args.apply:
            session.commit()
            print(f"Archived {archived} duplicate goal(s).")
        else:
            print("DRY-RUN: no changes made. Run with --apply to archive duplicates.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
