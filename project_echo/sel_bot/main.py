import asyncio
import logging
import os
import threading

from .config import Settings
from .discord_client import SelDiscordClient
from .llm_factory import create_llm_client, get_provider_info
from .memory import MemoryManager
from .models import Base, create_engine, create_session_factory, ensure_schema
from .state_manager import StateManager
from .hormone_state_manager import HormoneStateManager
from .process_lock import AlreadyRunningError, SingleInstanceLock


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _run_him_api_server(store, host: str, port: int) -> None:
    """Run the HIM API server in a separate thread."""
    import uvicorn
    from him.api import create_app

    app = create_app(store)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


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
        llm_client=llm_client,
    )

    # Start HIM API server in background thread if enabled
    him_api_thread = None
    if settings.him_api_enabled:
        logger.info(f"Starting HIM API server on {settings.him_api_host}:{settings.him_api_port}")
        him_api_thread = threading.Thread(
            target=_run_him_api_server,
            args=(memory_manager.store, settings.him_api_host, settings.him_api_port),
            daemon=True,
            name="him-api-server",
        )
        him_api_thread.start()
        # Give the API server time to start before other components try to connect
        await asyncio.sleep(2)
        logger.info("HIM API server started in background thread")

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

    # Initialize HormoneStateManager for HIM API-based hormone storage
    hormone_manager = None
    if settings.use_him_hormones:
        # Build API URL from settings
        api_url = f"http://{settings.him_api_host}:{settings.him_api_port}"
        if settings.him_api_host == "0.0.0.0":
            # Use localhost for internal connections when bound to all interfaces
            api_url = f"http://127.0.0.1:{settings.him_api_port}"

        hormone_manager = HormoneStateManager(
            api_base_url=api_url,
            snapshot_interval=settings.hormone_snapshot_interval,
        )
        await hormone_manager.start()
        logger.info("HormoneStateManager started (HIM API at %s)", api_url)
    else:
        logger.info("Using legacy SQLAlchemy hormone storage")

    discord_client = SelDiscordClient(
        settings=settings,
        state_manager=state_manager,
        llm_client=llm_client,
        memory_manager=memory_manager,
        hormone_manager=hormone_manager,
    )
    try:
        await discord_client.start(settings.discord_bot_token)
    finally:
        if hormone_manager:
            await hormone_manager.stop()
        await discord_client.close()


def main() -> None:
    lock_path = os.getenv("SEL_INSTANCE_LOCK_FILE")
    try:
        with SingleInstanceLock(lock_path):
            asyncio.run(init_app())
    except AlreadyRunningError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
