import asyncio
import logging
import os

from .config import Settings
from .discord_client import SelDiscordClient
from .llm_client import OpenRouterClient
from .memory import MemoryManager
from .models import Base, create_engine, create_session_factory, ensure_schema
from .state_manager import StateManager
from .agents_manager import AgentsManager
from .hormone_state_manager import HormoneStateManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def init_app() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema(engine)
    session_factory = create_session_factory(engine)
    state_manager = StateManager(
        session_factory,
        persona_seed=settings.persona_seed,
        continuation_keywords=settings.continuation_keywords,
    )
    llm_client = OpenRouterClient(settings)
    memory_manager = MemoryManager(
        state_manager,
        him_root=settings.him_memory_dir,
        max_level=settings.him_memory_levels,
    )
    agents_manager = AgentsManager(settings.agents_dir)

    # Initialize HormoneStateManager for HIM-based hormone storage
    hormone_manager = None
    if settings.use_him_hormones:
        hormone_manager = HormoneStateManager(
            him_root=settings.him_memory_dir,
            max_level=settings.him_memory_levels,
            snapshot_interval=settings.hormone_snapshot_interval,
        )
        await hormone_manager.start()
        logger.info("HormoneStateManager started (HIM-based hormone storage enabled)")
    else:
        logger.info("Using legacy SQLAlchemy hormone storage")

    discord_client = SelDiscordClient(
        settings=settings,
        state_manager=state_manager,
        llm_client=llm_client,
        memory_manager=memory_manager,
        agents_manager=agents_manager,
        hormone_manager=hormone_manager,
    )
    try:
        await discord_client.start(settings.discord_bot_token)
    finally:
        if hormone_manager:
            await hormone_manager.stop()
        await discord_client.close()


def main() -> None:
    asyncio.run(init_app())


if __name__ == "__main__":
    main()
