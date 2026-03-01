"""
Browser Agent for SEL

Headless Chromium automation for web searches and content extraction.
Outputs structured metadata blocks so Sel can apply vision analysis and
self-adapt search behavior over time.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin, urlparse

try:
    from playwright.async_api import Browser, Page, Playwright, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Prefer the system chromium when Playwright hasn't downloaded its own.
_SYSTEM_CHROMIUM = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")

DESCRIPTION = "Search web, navigate pages, and extract visual context (requires Playwright Chromium)"

# Global browser instance
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None

_SELDATA = Path(os.environ.get("SEL_DATA_DIR", "./sel_data")).expanduser()
_SCREENSHOT_DIR = _SELDATA / "browser_shots"
_WEB_LOG_PATH = _SELDATA / "web_behavior_log.jsonl"


def _ensure_dirs() -> None:
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _WEB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower()
    except Exception:
        return ""


def _append_web_log(event: dict) -> None:
    try:
        _ensure_dirs()
        payload = dict(event)
        payload.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        with _WEB_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        # Avoid breaking agent execution on telemetry failure.
        pass


def _cleanup_text(text: str, *, max_chars: int = 1600) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


async def _ensure_browser() -> Page:
    """Ensure browser/page are initialized."""
    global _playwright, _browser, _page

    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    if _browser is None:
        _playwright = await async_playwright().start()
        launch_kwargs: dict = {"headless": True}
        if _SYSTEM_CHROMIUM:
            launch_kwargs["executable_path"] = _SYSTEM_CHROMIUM
        _browser = await _playwright.chromium.launch(**launch_kwargs)
        _page = await _browser.new_page(viewport={"width": 1440, "height": 900})

    assert _page is not None
    return _page


async def _take_screenshot(page: Page, *, label: str) -> str:
    _ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_") or "page"
    path = _SCREENSHOT_DIR / f"{safe_label}_{stamp}.png"
    await page.screenshot(path=str(path), full_page=True)
    return str(path)


async def _extract_image_candidates(page: Page, base_url: str, *, limit: int = 8) -> list[dict[str, str]]:
    raw = await page.evaluate(
        """() => {
            const images = Array.from(document.images || []);
            return images.slice(0, 60).map((img) => ({
                src: img.currentSrc || img.src || "",
                alt: (img.alt || "").trim(),
                width: img.naturalWidth || img.width || 0,
                height: img.naturalHeight || img.height || 0,
            }));
        }"""
    )

    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        src = str(entry.get("src", "")).strip()
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(base_url, src)
        if absolute in seen:
            continue
        try:
            width = int(entry.get("width", 0) or 0)
            height = int(entry.get("height", 0) or 0)
        except Exception:
            width = 0
            height = 0
        if width and height and (width < 80 or height < 80):
            continue
        seen.add(absolute)
        candidates.append(
            {
                "url": absolute,
                "alt": _cleanup_text(str(entry.get("alt", "")).strip(), max_chars=140),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


async def _extract_page_text(page: Page) -> str:
    text = await page.evaluate(
        """() => {
            const body = document.body ? document.body.cloneNode(true) : null;
            if (!body) return "";
            const remove = body.querySelectorAll("script, style, nav, header, footer, noscript");
            remove.forEach((el) => el.remove());
            return (body.innerText || "").trim();
        }"""
    )
    return _cleanup_text(text, max_chars=1800)


def _format_browser_block(
    *,
    mode: str,
    query: str,
    current_url: str,
    screenshot_path: str,
    domains: list[str],
    image_candidates: list[dict[str, str]],
) -> str:
    lines = [
        "[WEB_BROWSER]",
        f"MODE: {mode}",
        f"QUERY: {query}",
        f"URL: {current_url}",
        f"SCREENSHOT_PATH: {screenshot_path}",
        "DOMAINS:",
    ]
    if domains:
        for domain in domains[:12]:
            lines.append(f"- {domain}")
    else:
        lines.append("- (none)")

    lines.append("IMAGE_URLS:")
    if image_candidates:
        for candidate in image_candidates[:8]:
            url = candidate.get("url", "")
            alt = candidate.get("alt", "")
            if alt:
                lines.append(f"- {url} | alt={alt}")
            else:
                lines.append(f"- {url}")
    else:
        lines.append("- (none)")
    lines.append("[/WEB_BROWSER]")
    return "\n".join(lines)


async def _search_web(query: str, limit: int = 5) -> str:
    """Search with headless Chromium and return text + structured metadata."""
    page = await _ensure_browser()

    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)

    try:
        await page.wait_for_selector(".result", timeout=7000)
    except Exception:
        await page.wait_for_timeout(1200)

    elements = await page.query_selector_all(".result")
    results: list[dict[str, str]] = []
    domains: list[str] = []
    for element in elements:
        if len(results) >= limit:
            break
        title_el = await element.query_selector(".result__a")
        if title_el is None:
            continue
        title = _cleanup_text(await title_el.inner_text(), max_chars=160)
        link = await title_el.get_attribute("href") or ""
        link = link.strip()
        if not link:
            continue
        snippet_el = await element.query_selector(".result__snippet")
        snippet = _cleanup_text(await snippet_el.inner_text(), max_chars=220) if snippet_el else ""
        results.append({"title": title, "url": link, "snippet": snippet})
        domain = _extract_domain(link)
        if domain:
            domains.append(domain)

    screenshot_path = await _take_screenshot(page, label="search")
    image_candidates = await _extract_image_candidates(page, page.url, limit=6)

    if not results:
        _append_web_log(
            {
                "mode": "search",
                "query": query,
                "domains": [],
                "image_count": len(image_candidates),
                "vision_used": False,
            }
        )
        return f"No results found for: {query}\n\n" + _format_browser_block(
            mode="search",
            query=query,
            current_url=page.url,
            screenshot_path=screenshot_path,
            domains=[],
            image_candidates=image_candidates,
        )

    output_lines = [f"Search results for '{query}':", ""]
    for i, result in enumerate(results, 1):
        output_lines.append(f"{i}. {result['title']}")
        output_lines.append(f"   {result['url']}")
        if result["snippet"]:
            output_lines.append(f"   {result['snippet']}")
        output_lines.append("")

    unique_domains = list(dict.fromkeys(domains))
    _append_web_log(
        {
            "mode": "search",
            "query": query,
            "domains": unique_domains,
            "image_count": len(image_candidates),
            "vision_used": False,
        }
    )

    output_lines.append(
        _format_browser_block(
            mode="search",
            query=query,
            current_url=page.url,
            screenshot_path=screenshot_path,
            domains=unique_domains,
            image_candidates=image_candidates,
        )
    )
    return "\n".join(output_lines).strip()


async def _navigate_to(url: str, *, query_label: str = "navigate") -> str:
    """Navigate to URL and extract content + visual metadata."""
    page = await _ensure_browser()

    await page.goto(url, wait_until="domcontentloaded", timeout=18000)
    await page.wait_for_timeout(900)

    title = _cleanup_text(await page.title(), max_chars=180)
    current_url = page.url
    text = await _extract_page_text(page)
    screenshot_path = await _take_screenshot(page, label="page")
    image_candidates = await _extract_image_candidates(page, current_url, limit=8)

    domain = _extract_domain(current_url)
    domains = [domain] if domain else []
    _append_web_log(
        {
            "mode": "navigate",
            "query": query_label,
            "domains": domains,
            "image_count": len(image_candidates),
            "vision_used": False,
        }
    )

    payload = [
        f"{title}",
        f"URL: {current_url}",
        "",
        text or "(No visible text found on page.)",
        "",
        _format_browser_block(
            mode="navigate",
            query=query_label,
            current_url=current_url,
            screenshot_path=screenshot_path,
            domains=domains,
            image_candidates=image_candidates,
        ),
    ]
    return "\n".join(payload).strip()


def run(query: str, **kwargs) -> str:
    """
    Browser agent: headless Chromium search/navigation with structured metadata.

    Examples:
    - "search for python tutorials"
    - "https://example.com"
    - "find latest patch notes"
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Browser agent unavailable: Playwright is not installed."

    text = (query or "").strip()
    if not text:
        return "Empty query. Provide a URL or a search phrase."

    try:
        # Direct URL navigation.
        if text.startswith("http://") or text.startswith("https://"):
            return asyncio.run(_navigate_to(text, query_label=text))

        # Strip common prefixes.
        search_query = text
        lowered = text.lower()
        for prefix in ("search for ", "search ", "find ", "look up ", "google "):
            if lowered.startswith(prefix):
                search_query = text[len(prefix) :].strip()
                break
        if not search_query:
            search_query = text

        return asyncio.run(_search_web(search_query, limit=5))
    except Exception as exc:
        _append_web_log(
            {
                "mode": "error",
                "query": text,
                "domains": [],
                "image_count": 0,
                "vision_used": False,
                "error": str(exc),
            }
        )
        return f"Browser error: {exc}"
