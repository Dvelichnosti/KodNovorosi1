"""Mark expired listings as ``expired``.

Run periodically, e.g. every 15 minutes from cron or a scheduler::

    python -m scripts.expire_listings
"""
from __future__ import annotations

import asyncio
import logging

from app.core.database import SessionLocal, engine
from app.services.listing_service import expire_listings

logger = logging.getLogger(__name__)


async def main() -> None:
    async with SessionLocal() as session:
        count = await expire_listings(session)
    await engine.dispose()
    logger.info("Expired listings updated: %s", count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
