import asyncio
import logging
import os

from .config import Settings
from .discord_client import SelDiscordClient
from .llm_factory import create_llm_client, get_provider_info
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

    # Log LLM provider information
    provider_info = get_provider_info(settings)
    logger.info("=" * 60)
    logger.info(f"LLM Provider: {provider_info['provider']} ({provider_info['type']})")
    if provider_info.get('base_url'):
        logger.info(f"  Base URL: {provider_info['base_url']}")
    logger.info(f"  Main Model: {provider_info.get('main_model', 'N/A')}")
    logger.info(f"  Util Model: {provider_info.get('util_model', 'N/A')}")
    logger.info(f"  Vision Model: {provider_info.get('vision_model', 'N/A')}")
    logger.info("=" * 60)

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
    llm_client = create_llm_client(settings)
    memory_manager = MemoryManager(
        state_manager,
        him_root=settings.him_memory_dir,
        max_level=settings.him_memory_levels,
    )
    # Debug: Log the actual HIM path being used
    from pathlib import Path
    him_path_abs = Path(settings.him_memory_dir).absolute()
    him_db_exists = (him_path_abs / "him.db").exists()
    logger.info(f"MemoryManager initialized with HIM root: {settings.him_memory_dir}")
    logger.info(f"  Absolute path: {him_path_abs}")
    logger.info(f"  Database exists: {him_db_exists}")
    if him_db_exists:
        import sqlite3
        db_path = him_path_abs / "him.db"
        conn = sqlite3.connect(db_path)
        tile_count = conn.execute("SELECT COUNT(*) FROM tiles WHERE level=0").fetchone()[0]
        snapshot_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        conn.close()
        logger.info(f"  Database contains: {snapshot_count} snapshots, {tile_count} L0 tiles")

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
