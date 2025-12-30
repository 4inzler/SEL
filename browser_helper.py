"""
Headless browser automation for SEL Desktop
Uses Playwright for web searches, navigation, and content extraction
"""
import asyncio
from typing import Optional, Dict, List

try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  playwright not installed. Browser features disabled.")
    print("   Install with: pip install playwright")
    print("   Then run: playwright install chromium")

# Global browser instance (reused across calls)
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None

async def _ensure_browser():
    """Ensure browser is initialized"""
    global _playwright, _browser, _page

    if not PLAYWRIGHT_AVAILABLE:
        raise Exception("Playwright not installed")

    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        _page = await _browser.new_page()

    return _page

async def close_browser():
    """Close browser and cleanup"""
    global _playwright, _browser, _page

    if _page:
        await _page.close()
        _page = None

    if _browser:
        await _browser.close()
        _browser = None

    if _playwright:
        await _playwright.stop()
        _playwright = None

async def search_web(query: str, limit: int = 5) -> str:
    """
    Search Google and return results

    Args:
        query: Search query
        limit: Number of results to return

    Returns:
        Formatted search results
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed. Install with: pip install playwright"

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
        output = f"Search results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['title']}\n"
            output += f"   {r['url']}\n"
            if r['snippet']:
                output += f"   {r['snippet']}...\n"
            output += "\n"

        return output

    except Exception as e:
        return f"Search error: {e}"

async def navigate_to(url: str, extract_text: bool = True) -> str:
    """
    Navigate to a URL and optionally extract content

    Args:
        url: URL to navigate to
        extract_text: Whether to extract page text

    Returns:
        Page info and content
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        page = await _ensure_browser()

        # Navigate
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # Get page info
        title = await page.title()
        current_url = page.url

        result = f"Navigated to: {title}\nURL: {current_url}\n\n"

        if extract_text:
            # Extract main content
            text = await page.evaluate("""() => {
                // Remove scripts, styles, etc.
                const body = document.body.cloneNode(true);
                const remove = body.querySelectorAll('script, style, nav, header, footer');
                remove.forEach(el => el.remove());
                return body.innerText;
            }""")

            # Limit text length
            if len(text) > 2000:
                text = text[:2000] + "...\n[Content truncated]"

            result += f"Content:\n{text}"

        return result

    except Exception as e:
        return f"Navigation error: {e}"

async def extract_page_content() -> str:
    """
    Extract text content from current page

    Returns:
        Page text content
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        if _page is None:
            return "Error: No page loaded. Navigate to a URL first."

        title = await _page.title()
        url = _page.url

        # Extract content
        text = await _page.evaluate("""() => {
            const body = document.body.cloneNode(true);
            const remove = body.querySelectorAll('script, style, nav, header, footer');
            remove.forEach(el => el.remove());
            return body.innerText;
        }""")

        result = f"Page: {title}\nURL: {url}\n\nContent:\n{text[:2000]}"
        if len(text) > 2000:
            result += "...\n[Content truncated]"

        return result

    except Exception as e:
        return f"Extract error: {e}"

async def find_on_page(search_text: str) -> str:
    """
    Find text on current page

    Args:
        search_text: Text to search for

    Returns:
        Found locations and context
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        if _page is None:
            return "Error: No page loaded. Navigate to a URL first."

        # Search for text
        elements = await _page.query_selector_all(f"text={search_text}")

        if not elements:
            return f"Text '{search_text}' not found on page"

        result = f"Found {len(elements)} occurrences of '{search_text}':\n\n"

        for i, el in enumerate(elements[:5], 1):
            # Get element context
            text = await el.inner_text()
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            result += f"{i}. <{tag}>: {text[:100]}\n"

        if len(elements) > 5:
            result += f"\n... and {len(elements) - 5} more"

        return result

    except Exception as e:
        return f"Find error: {e}"

async def click_element(selector: str) -> str:
    """
    Click an element on the page

    Args:
        selector: CSS selector or text selector

    Returns:
        Result message
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        if _page is None:
            return "Error: No page loaded. Navigate to a URL first."

        # Try to click
        await _page.click(selector, timeout=5000)

        # Wait for navigation if any
        await _page.wait_for_load_state("domcontentloaded", timeout=5000)

        title = await _page.title()
        return f"Clicked '{selector}'. Now on: {title}"

    except Exception as e:
        return f"Click error: {e}"

async def fill_input(selector: str, text: str) -> str:
    """
    Fill an input field

    Args:
        selector: CSS selector for input
        text: Text to fill

    Returns:
        Result message
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        if _page is None:
            return "Error: No page loaded. Navigate to a URL first."

        await _page.fill(selector, text, timeout=5000)
        return f"Filled '{selector}' with: {text}"

    except Exception as e:
        return f"Fill error: {e}"

async def get_page_info() -> Dict:
    """
    Get information about current page

    Returns:
        Dictionary with page info
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "Playwright not installed"}

    try:
        if _page is None:
            return {"error": "No page loaded"}

        title = await _page.title()
        url = _page.url

        # Get links
        links = await _page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a'));
            return anchors.slice(0, 10).map(a => ({
                text: a.innerText.substring(0, 50),
                href: a.href
            }));
        }""")

        return {
            "title": title,
            "url": url,
            "links": links
        }

    except Exception as e:
        return {"error": f"Page info error: {e}"}

async def screenshot_page(path: str = "browser_screenshot.png") -> str:
    """
    Take screenshot of current page

    Args:
        path: Path to save screenshot

    Returns:
        Result message
    """
    if not PLAYWRIGHT_AVAILABLE:
        return "Error: Playwright not installed"

    try:
        if _page is None:
            return "Error: No page loaded"

        await _page.screenshot(path=path)
        return f"Screenshot saved to: {path}"

    except Exception as e:
        return f"Screenshot error: {e}"
