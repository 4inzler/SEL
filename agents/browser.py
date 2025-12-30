"""
Browser Agent for SEL

Headless browser automation for web searches and content extraction.
Uses Playwright to search the web, navigate pages, and extract content.

Usage examples:
- "search for python tutorials"
- "go to https://example.com and tell me what it says"
- "find information about X"
"""

import asyncio
from typing import Optional

try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

DESCRIPTION = "Search web, navigate pages, extract content (requires Playwright)"

# Global browser instance
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None

async def _ensure_browser():
    """Ensure browser is initialized"""
    global _playwright, _browser, _page

    if not PLAYWRIGHT_AVAILABLE:
        raise Exception("Playwright not installed. Run: pip install playwright && playwright install chromium")

    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        _page = await _browser.new_page()

    return _page

async def _search_web(query: str, limit: int = 5) -> str:
    """Search Google and return results"""
    try:
        page = await _ensure_browser()

        # Go to Google
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=10000)

        # Wait for results
        await page.wait_for_selector("h3", timeout=5000)

        # Extract results
        results = []
        elements = await page.query_selector_all("div.g")

        for i, element in enumerate(elements[:limit]):
            try:
                # Get title
                title_el = await element.query_selector("h3")
                title = await title_el.inner_text() if title_el else "No title"

                # Get link
                link_el = await element.query_selector("a")
                link = await link_el.get_attribute("href") if link_el else "No link"

                # Get snippet
                snippet_el = await element.query_selector("div[data-sncf]")
                if not snippet_el:
                    snippet_el = await element.query_selector("div.VwiC3b")
                snippet = await snippet_el.inner_text() if snippet_el else ""

                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet[:150]
                })
            except:
                continue

        if not results:
            return f"No results found for: {query}"

        # Format results
        output = f"**Search results for '{query}':**\n\n"
        for i, r in enumerate(results, 1):
            output += f"**{i}. {r['title']}**\n"
            output += f"   {r['url']}\n"
            if r['snippet']:
                output += f"   {r['snippet']}...\n"
            output += "\n"

        return output

    except Exception as e:
        return f"Search error: {e}"

async def _navigate_to(url: str) -> str:
    """Navigate to URL and extract content"""
    try:
        page = await _ensure_browser()

        # Navigate
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # Get page info
        title = await page.title()
        current_url = page.url

        # Extract content
        text = await page.evaluate("""() => {
            const body = document.body.cloneNode(true);
            const remove = body.querySelectorAll('script, style, nav, header, footer');
            remove.forEach(el => el.remove());
            return body.innerText;
        }""")

        # Limit text length
        if len(text) > 1500:
            text = text[:1500] + "...\n[Content truncated - page is longer]"

        return f"**{title}**\nURL: {current_url}\n\n{text}"

    except Exception as e:
        return f"Navigation error: {e}"

def run(query: str, **kwargs) -> str:
    """
    Browser agent - search web or navigate to URLs

    Examples:
        "search for python tutorials" -> Google search
        "https://example.com" -> Navigate and extract content
        "find information about AI" -> Search and return results
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "❌ Browser agent requires Playwright. Install with:\n```\npip install playwright\nplawright install chromium\n```"

    query = query.strip()

    # Check if it's a URL
    if query.startswith("http://") or query.startswith("https://"):
        return asyncio.run(_navigate_to(query))

    # Otherwise, search
    # Remove common search prefixes
    search_query = query
    for prefix in ["search for ", "search ", "find ", "look up ", "google "]:
        if query.lower().startswith(prefix):
            search_query = query[len(prefix):]
            break

    return asyncio.run(_search_web(search_query, limit=5))
