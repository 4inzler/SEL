"""Optimized agent registry with caching and performance monitoring."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from .agent_cache import get_agent_cache

logger = logging.getLogger(__name__)


@dataclass
class LoadedAgent:
    name: str
    path: Path
    run: Optional[Callable]
    tool: Optional[object] = None
    description: str = ""
    cacheable: bool = True  # Whether this agent's results can be cached
    cache_ttl: float = 300  # Default 5 minutes


class AgentsManager:
    def __init__(self, agents_dir: str, enable_cache: bool = True) -> None:
        self.agents_dir = self._resolve_agents_dir(agents_dir)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.enable_cache = enable_cache
        self.agent_cache = get_agent_cache() if enable_cache else None

        # Agent module cache (loaded once, reused)
        self._agent_registry: Dict[str, LoadedAgent] = {}
        self._registry_loaded = False

    def _resolve_agents_dir(self, agents_dir: str) -> Path:
        """
        Resolve the agents directory, falling back to the repo-level ./agents if the
        provided path is missing (common when running from project_echo/ instead of repo root).
        """
        def has_agents(path: Path) -> bool:
            return path.exists() and any(path.glob("*.py"))

        primary = Path(agents_dir).expanduser()
        if not primary.is_absolute():
            primary = (Path.cwd() / primary).resolve()

        repo_agents = Path(__file__).resolve().parents[2] / "agents"

        if has_agents(primary):
            return primary
        if has_agents(repo_agents):
            return repo_agents
        # If neither contains agents, prefer primary but ensure it exists
        return primary

    def list_agents(self, force_reload: bool = False) -> List[LoadedAgent]:
        """
        List all available agents, loading from cache if possible.

        Args:
            force_reload: If True, reload all agent modules from disk

        Returns:
            List of loaded agent objects
        """
        if force_reload or not self._registry_loaded:
            logger.info("Loading agents from %s", self.agents_dir)
            self._agent_registry.clear()
            for file in sorted(self.agents_dir.glob("*.py")):
                agent = self._load_agent(file)
                if agent:
                    self._agent_registry[agent.name] = agent
            self._registry_loaded = True
            logger.info("Loaded %d agents", len(self._agent_registry))

        return list(self._agent_registry.values())

    def _load_agent(self, path: Path) -> Optional[LoadedAgent]:
        """Load a single agent module from disk."""
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning("Failed to import agent %s: %s", path.name, exc)
            return None

        run_fn = getattr(module, "run", None)
        desc = getattr(module, "DESCRIPTION", "")
        tool = getattr(module, "tool", None)

        # Agent-specific cache configuration
        cacheable = getattr(module, "CACHEABLE", True)
        cache_ttl = getattr(module, "CACHE_TTL", 300)  # 5 minutes default

        # Handle modules that expose a list/dict of tools
        if tool is None:
            tools_attr = getattr(module, "tools", None)
            if isinstance(tools_attr, list) and tools_attr:
                tool = tools_attr[0]

        return LoadedAgent(
            name=path.stem,
            path=path,
            run=run_fn,
            tool=tool,
            description=str(desc),
            cacheable=cacheable,
            cache_ttl=cache_ttl,
        )

    async def run_agent_async(self, name: str, *args, **kwargs):
        """
        Execute an agent asynchronously with caching and performance tracking.

        Args:
            name: Agent name to execute
            *args: Positional arguments passed to agent
            **kwargs: Keyword arguments passed to agent

        Returns:
            Agent execution result (string)
        """
        # Find agent in registry
        agent = self._agent_registry.get(name)
        if not agent:
            # Try loading if not in cache
            self.list_agents()
            agent = self._agent_registry.get(name)
            if not agent:
                raise ValueError(f"Agent '{name}' not found")

        # Prepare input for caching (first positional arg or empty string)
        input_data = str(args[0]) if args else ""

        # Check cache if enabled and agent is cacheable
        if self.agent_cache and agent.cacheable:
            cached_result = await self.agent_cache.get(
                name, input_data, ttl_seconds=agent.cache_ttl
            )
            if cached_result:
                # Log metrics for cached execution
                await self.agent_cache.log_execution(
                    name, input_data, 0.0, True, cached=True
                )
                return cached_result

        # Execute agent
        start_time = time.perf_counter()
        success = False
        error_msg = None
        result = None

        try:
            if agent.run:
                result = agent.run(*args, **kwargs)
                # Handle async agents
                if asyncio.iscoroutine(result):
                    result = await result
            elif agent.tool:
                tool_obj = agent.tool
                if hasattr(tool_obj, "run"):
                    result = tool_obj.run(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
                elif hasattr(tool_obj, "invoke"):
                    result = tool_obj.invoke(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
                elif callable(tool_obj):
                    result = tool_obj(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
            else:
                raise ValueError(f"Agent '{name}' has no runnable entrypoint")

            success = True
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Agent execution failed agent=%s error=%s", name, exc)
            result = f"Agent execution failed: {exc}"
        finally:
            execution_time_ms = (time.perf_counter() - start_time) * 1000

            # Log metrics
            if self.agent_cache:
                await self.agent_cache.log_execution(
                    name, input_data, execution_time_ms, success, error_msg
                )

            # Cache successful results if cacheable
            if (
                success
                and self.agent_cache
                and agent.cacheable
                and result is not None
            ):
                await self.agent_cache.put(
                    name, input_data, str(result), ttl_seconds=agent.cache_ttl
                )

        return result

    def run_agent(self, name: str, *args, **kwargs):
        """
        Synchronous wrapper for run_agent_async.

        Note: This blocks the event loop. Prefer run_agent_async when possible.
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, use create_task
            return asyncio.create_task(self.run_agent_async(name, *args, **kwargs))
        except RuntimeError:
            # No running loop, use asyncio.run
            return asyncio.run(self.run_agent_async(name, *args, **kwargs))

    def get_agent_stats(self) -> Dict:
        """Get performance statistics for all agents."""
        if not self.agent_cache:
            return {}
        return self.agent_cache.get_agent_stats()
