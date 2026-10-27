"""Offline calibration report for the Level-2 soft-identity duplicate detector.

Loads all candidates of an org (active + shadow/archived), scores every pair with
score_soft_identity, and prints the pairs at/above a reporting cutoff, sorted by
confidence, with the contributing signals. WRITES NOTHING to the DB — pure report
so weights/threshold in similarity.py can be tuned against real data before any
flag ships to prod.

Usage:
    cd backend
    python -m scripts.dryrun_duplicate_detection --org 1 --min 40
"""
import argparse
import asyncio
import os
import sys
from itertools import combinations

# Make `from api...` work regardless of how the script is launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.database import Entity, EntityType  # noqa: E402
from api.services.similarity import build_dup_keys, score_soft_identity  # noqa: E402


async def _run(org_id: int, min_conf: int) -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Entity).where(
                Entity.type == EntityType.candidate,
                Entity.org_id == org_id,
            )
        )).scalars().all()

    keyed = []
    for e in rows:
        keys = build_dup_keys(
            name=e.name, email=e.email, phone=e.phone,
            emails=e.emails, phones=e.phones,
            telegram_usernames=e.telegram_usernames,
            extra_data=e.extra_data,
        )
        keyed.append((e, keys))

    hits = []
    for (ea, ka), (eb, kb) in combinations(keyed, 2):
        r = score_soft_identity(ka, kb)
        if r.confidence >= min_conf and r.components >= 2:
            hits.append((r.confidence, r.is_flag, ea, eb, r))

    hits.sort(key=lambda x: x[0], reverse=True)
    print(f"\n{len(hits)} candidate pairs >= {min_conf} (of {len(rows)} candidates)\n")
    for conf, is_flag, ea, eb, r in hits:
        flag = "FLAG" if is_flag else "    "
        arch_a = "A" if getattr(ea, "is_archived", False) else " "
        arch_b = "A" if getattr(eb, "is_archived", False) else " "
        print(f"[{flag}] {conf:3d}%  #{ea.id}{arch_a} «{ea.name}»  <->  "
              f"#{eb.id}{arch_b} «{eb.name}»  | {', '.join(r.detail)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--min", type=int, default=40, help="reporting cutoff confidence")
    args = ap.parse_args()
    asyncio.run(_run(args.org, args.min))


if __name__ == "__main__":
    main()
