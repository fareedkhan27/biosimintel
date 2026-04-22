from __future__ import annotations

import asyncio

from app.db.seeds import run_seeds

if __name__ == "__main__":
    asyncio.run(run_seeds())
