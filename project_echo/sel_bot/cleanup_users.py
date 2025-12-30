"""
Script to remove all memories and data for specific user IDs from SEL's database.
"""

import asyncio
import logging
from sqlalchemy import delete
from config import Settings
from models import create_engine, create_session_factory, UserState, FeedbackEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# User IDs to remove
USER_IDS_TO_REMOVE = [
    "1169904784422211614",
    "1368386369004503072"
]


async def cleanup_user_data(user_ids: list[str]):
    """Remove all data associated with specific user IDs."""
    settings = Settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        # Delete user state
        result = await session.execute(
            delete(UserState).where(UserState.user_id.in_(user_ids))
        )
        user_state_count = result.rowcount
        logger.info(f"Deleted {user_state_count} user_state entries")

        # Delete feedback events
        result = await session.execute(
            delete(FeedbackEvent).where(FeedbackEvent.user_id.in_(user_ids))
        )
        feedback_count = result.rowcount
        logger.info(f"Deleted {feedback_count} feedback_event entries")

        await session.commit()
        logger.info(f"Cleanup complete for user IDs: {user_ids}")
        logger.info(f"Total entries removed: {user_state_count + feedback_count}")

    await engine.dispose()


if __name__ == "__main__":
    logger.info(f"Starting cleanup for user IDs: {USER_IDS_TO_REMOVE}")
    asyncio.run(cleanup_user_data(USER_IDS_TO_REMOVE))
    logger.info("Done!")
