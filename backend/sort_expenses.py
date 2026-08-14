#!/usr/bin/env python3
"""
Move existing expense receipts into tax year subfolders.
Run inside the backend container:
  docker exec new-weddings-backend python sort_expenses.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
import os, shutil

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = os.environ.get("DB_NAME", "weddings_by_mark")

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    expenses = await db.expenses.find({}, {"_id": 0}).to_list(10000)
    print(f"Found {len(expenses)} expenses")

    moved = 0
    skipped = 0
    for exp in expenses:
        file_path = exp.get("file_path")
        tax_year = exp.get("tax_year")
        if not file_path or not tax_year:
            skipped += 1
            continue

        old_path = Path(file_path)
        if not old_path.exists():
            print(f"  SKIP (file missing): {old_path}")
            skipped += 1
            continue

        # Already in a tax year folder?
        if tax_year in str(old_path):
            skipped += 1
            continue

        new_dir = old_path.parent / tax_year
        new_dir.mkdir(parents=True, exist_ok=True)
        new_path = new_dir / old_path.name

        shutil.move(str(old_path), str(new_path))
        await db.expenses.update_one(
            {"id": exp["id"]},
            {"$set": {"file_path": str(new_path)}}
        )
        print(f"  MOVED: {old_path.name} -> expenses/{tax_year}/")
        moved += 1

    print(f"\nDone! Moved {moved}, skipped {skipped}")

asyncio.run(main())
