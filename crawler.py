import asyncio
import re
from urllib.parse import urljoin, urldefrag
from playwright.async_api import async_playwright


# ============================================================
# ROLE MATCHING (LESS NOISY)
# ============================================================
ROLE_WORDS = [
    "engineer", "developer", "programmer", "swe", "sde", "software engineer", "software developer"
]

DOMAIN_WORDS = [
    "software", "backend", "back-end", "full stack", "full-stack", "platform",
    "systems", "infrastructure", "cloud", "distributed", "services",
    ".net", "dotnet", "c#", "csharp", "api"
]

# These are used for search queries (Step 5)
SEARCH_QUERIES = [
    "software engineer",
    "backend engineer",
    "full stack engineer",
    "platform engineer",
    "dotnet engineer",
    "c# engineer",
]

ROLE_KEYWORDS = [
    # kept for compatibility with your structure (not used directly for matching anymore)
    "software", "engineer", "developer", "full stack",
    "backend", ".net", "c#", "swe", "sde", "platform"
]

def _has_token(text: str, token: str) -> bool:
    """
    Token-aware matching:
    - word-boundary match for normal words
    - special handling for tokens like 'c#' and '.net'
    """
    t = text.lower()
    tok = token.lower().strip()

    if tok in ("c#", ".net", "dotnet", "csharp"):
        return tok in t

    # Treat multi-word tokens normally
    if " " in tok or "-" in tok:
        return tok in t

    return re.search(rf"\b{re.escape(tok)}\b", t) is not None

def is_swe_role(text: str) -> bool:
    """
    Reduce false positives:
    Must contain at least one ROLE_WORD and one DOMAIN_WORD.
    """
    if not text:
        return False
    t = text.strip().lower()
    if len(t) < 3:
        return False

    has_role = any(_has_token(t, w) for w in ROLE_WORDS)
    has_domain = any(_has_token(t, w) for w in DOMAIN_WORDS)
    return has_role and has_domain


# ============================================================
# URL NORMALIZATION
# ============================================================
def normalize_href(base_url: str, href: str) -> str | None:
    if not href:
        return None
    h = href.strip()

    # skip junk
    lowered = h.lower()
    if lowered.startswith("#"):
        return None
    if lowered.startswith("javascript:"):
        return None
    if lowered.startswith("mailto:"):
        return None
    if lowered.startswith("tel:"):
        return None

    abs_url = urljoin(base_url, h)
    abs_url, _frag = urldefrag(abs_url)  # remove #fragment
    return abs_url


# ============================================================
# BASE EXTRACTOR — shared utilities
# ============================================================
class BaseExtractor:
    # ---------------------------- SAFE WAIT HELPERS ----------------------------
    async def safe_networkidle(self, page, timeout_ms: int = 8000):
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except:
            pass

    # ---------------------------- SEARCH BOX DETECTION ----------------------------
    async def find_search_box(self, page):
        selectors = [
            "input[type='search']",
            "input[placeholder*='search' i]",
            "input[placeholder*='keyword' i]",
            "input[aria-label*='search' i]",
            "input[id*='search' i]"
        ]
        for sel in selectors:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                print(f"🔎 Search box found: {sel}")
                return el.first
        return None

    # ---------------------------- LOCATION FILTER DETECTION (IMPROVED) ----------------------------
    async def apply_location_filter(self, page):
        print("\n🔍 Checking for location filter UI...\n")

        # 0) Best case: <label for="...">Location</label> -> input#...
        label = page.locator("label:has-text('Location')").first
        try:
            if await label.count() > 0 and await label.is_visible():
                for_id = await label.get_attribute("for")
                if for_id:
                    target = page.locator(f"#{for_id}").first
                    if await target.count() > 0 and await target.is_visible():
                        print("📍 Location input found via label[for] association")
                        await target.click()
                        await target.fill("United States")
                        await page.wait_for_timeout(300)

                        suggestion = page.locator("li[role='option'], div[role='option']")
                        if await suggestion.count() > 0:
                            await suggestion.first.click()
                        else:
                            await page.keyboard.press("Enter")

                        await self.safe_networkidle(page)
                        return True
        except:
            pass

        # 1) Basic <input>
        selectors = [
            "input[placeholder*='location' i]",
            "input[aria-label*='location' i]",
            "input[name*='location' i]",
            "input[id*='location' i]"
        ]

        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                print(f"📍 Location filter found: {sel}")
                await loc.click()
                await loc.fill("United States")
                await page.wait_for_timeout(300)

                suggestion = page.locator("li[role='option'], div[role='option']")
                if await suggestion.count() > 0:
                    print("📌 Selecting first suggested US location...")
                    await suggestion.first.click()
                else:
                    print("⚠ No suggestions → pressing Enter")
                    await page.keyboard.press("Enter")

                await self.safe_networkidle(page)
                return True

        # 2) React / JS combobox components (still broad, but kept as fallback)
        react_selectors = [
            "div[aria-label*='location' i] [role='combobox']",
            "button[aria-label*='location' i]",
            "div[aria-label*='location' i]",
            "[role='combobox']"
        ]

        for sel in react_selectors:
            widget = page.locator(sel).first
            if await widget.count() > 0 and await widget.is_visible():
                print(f"📍 React widget found: {sel}")
                try:
                    await widget.click()
                except:
                    pass
                await page.wait_for_timeout(250)

                input_box = page.locator("input[type='text'], input").first
                if await input_box.count() > 0 and await input_box.is_visible():
                    await input_box.fill("United States")
                    await page.wait_for_timeout(250)

                    suggestion = page.locator("li[role='option'], div[role='option']")
                    if await suggestion.count() > 0:
                        print("📌 Selecting suggestion...")
                        await suggestion.first.click()
                    else:
                        await page.keyboard.press("Enter")

                    await self.safe_networkidle(page)
                    return True

        # 3) <select> dropdown
        dropdowns = [
            "select[name*='location' i]",
            "select[aria-label*='Location' i]"
        ]

        for sel in dropdowns:
            box = page.locator(sel).first
            if await box.count() > 0 and await box.is_visible():
                print(f"📍 Dropdown found: {sel}")
                try:
                    await box.select_option(label="United States")
                except:
                    # fallback: sometimes values are like "US"
                    try:
                        await box.select_option(value="US")
                    except:
                        return False
                await self.safe_networkidle(page)
                return True

        print("❌ No location filter detected.\n")
        return False

    # ---------------------------- PAGINATION HELPERS ----------------------------
    async def _next_locator(self, page):
        return page.locator("""
            button:has-text("Next"),
            a:has-text("Next"),
            button[aria-label*='Next' i],
            a[aria-label*='Next' i]
        """).first

    async def has_next_button(self, page) -> bool:
        btn = await self._next_locator(page)
        if await btn.count() == 0:
            return False
        try:
            return await btn.is_visible()
        except:
            return False

    async def click_next(self, page, prev_signature: str | None = None) -> tuple[bool, str | None]:
        btn = await self._next_locator(page)
        if await btn.count() == 0:
            return (False, prev_signature)

        # check disabled-ish state
        try:
            if not await btn.is_visible():
                return (False, prev_signature)
        except:
            return (False, prev_signature)

        try:
            aria_disabled = await btn.get_attribute("aria-disabled")
            if aria_disabled and aria_disabled.lower() in ("true", "1"):
                return (False, prev_signature)
        except:
            pass

        # record before click
        old_url = page.url

        try:
            await btn.click()
        except:
            return (False, prev_signature)

        # safer waits: don't rely on networkidle forever
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except:
            pass
        await self.safe_networkidle(page, timeout_ms=8000)

        # verify change (URL OR signature change)
        new_sig = await self.first_result_signature(page)
        if page.url != old_url:
            return (True, new_sig)
        if prev_signature and new_sig and new_sig != prev_signature:
            return (True, new_sig)

        # no detectable change -> stop
        return (False, new_sig)

    async def has_numeric_pagination(self, page) -> bool:
        pager = page.locator("""
            nav[aria-label*="pagination" i],
            .pagination,
            ul.pagination,
            [role="navigation"] .pagination
        """)
        try:
            if await pager.count() == 0:
                return False
            # any numeric link visible?
            links = pager.locator("a")
            if await links.count() == 0:
                return False
            # quick check: at least one link with digit text
            for i in range(min(await links.count(), 30)):
                txt = ((await links.nth(i).inner_text()) or "").strip()
                if txt.isdigit():
                    return True
            return False
        except:
            return False

    async def click_next_page_number(self, page) -> bool:
        """
        Clicks current_page + 1 if detectable.
        """
        pager = page.locator("""
            nav[aria-label*="pagination" i],
            .pagination,
            ul.pagination,
            [role="navigation"] .pagination
        """).first
        if await pager.count() == 0:
            return False

        # detect current page
        current_num = None
        try:
            cur = pager.locator('[aria-current="page"]').first
            if await cur.count() > 0:
                txt = ((await cur.inner_text()) or "").strip()
                if txt.isdigit():
                    current_num = int(txt)
        except:
            pass

        # gather numeric links
        links = pager.locator("a")
        n = await links.count()
        nums = []
        for i in range(min(n, 80)):
            a = links.nth(i)
            try:
                txt = ((await a.inner_text()) or "").strip()
                if txt.isdigit():
                    nums.append((int(txt), a))
            except:
                continue

        if not nums:
            return False

        # if current not found, assume smallest is current-ish
        if current_num is None:
            current_num = min(x[0] for x in nums)

        target = None
        for num, loc in nums:
            if num == current_num + 1:
                target = loc
                break

        if not target:
            return False

        old_url = page.url
        try:
            await target.click()
        except:
            return False

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except:
            pass
        await self.safe_networkidle(page, timeout_ms=8000)

        # basic change check
        return page.url != old_url or (await self.first_result_signature(page)) is not None

    # ---------------------------- SCROLL ----------------------------
    async def scroll_full_page(self, page, max_rounds: int = 25):
        last_height = None
        for _ in range(max_rounds):
            try:
                height = await page.evaluate("document.body.scrollHeight")
            except:
                break
            if height == last_height:
                break
            last_height = height
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except:
                break
            await page.wait_for_timeout(500)

    # ---------------------------- RESULT SIGNATURE ----------------------------
    async def first_result_signature(self, page) -> str | None:
        """
        A lightweight 'did content change?' signal.
        We scan a few anchors and pick the first one that looks like a SWE role.
        """
        try:
            links = page.locator("a[href]")
            count = await links.count()
            for i in range(min(count, 80)):
                a = links.nth(i)
                txt = ((await a.inner_text()) or "").strip()
                if txt and is_swe_role(txt):
                    href = await a.get_attribute("href")
                    if href:
                        return f"{txt}::{href}"
        except:
            pass
        return None


# ============================================================
# DIRECT EXTRACTOR — raw HTML link scanning (IMPROVED)
# ============================================================
class DirectExtractor(BaseExtractor):
    async def extract(self, page, keywords):
        jobs = []
        seen = set()

        base_url = page.url
        links = page.locator("a[href]")
        count = await links.count()

        for i in range(count):
            a = links.nth(i)
            try:
                text = ((await a.inner_text()) or "").strip()
                href = await a.get_attribute("href")
            except:
                continue

            if not text or not href:
                continue

            if not is_swe_role(text):
                continue

            abs_url = normalize_href(base_url, href)
            if not abs_url:
                continue

            if abs_url in seen:
                continue
            seen.add(abs_url)

            jobs.append({"title": text, "url": abs_url})

        return jobs


# ============================================================
# SEARCH EXTRACTOR (MULTI-QUERY + DEDUPE)
# ============================================================
class SearchExtractor(BaseExtractor):
    async def extract(self, page, keywords):
        search = await self.find_search_box(page)
        if not search:
            return []

        all_results = []
        seen = set()

        for q in SEARCH_QUERIES:
            try:
                await search.click()
                await search.fill(q)
                await page.keyboard.press("Enter")
            except:
                continue

            await page.wait_for_timeout(300)
            await self.safe_networkidle(page, timeout_ms=8000)

            prev_sig = await self.first_result_signature(page)

            while True:
                batch = await DirectExtractor().extract(page, keywords)
                for j in batch:
                    if j["url"] not in seen:
                        seen.add(j["url"])
                        all_results.append(j)

                # Try Next button first
                if await self.has_next_button(page):
                    ok, prev_sig = await self.click_next(page, prev_sig)
                    if ok:
                        continue

                # Then try numeric pagination
                if await self.has_numeric_pagination(page):
                    ok = await self.click_next_page_number(page)
                    if ok:
                        prev_sig = await self.first_result_signature(page)
                        continue

                break

        return all_results


# ============================================================
# PAGINATION EXTRACTOR (NEXT + NUMERIC)
# ============================================================
class PaginationExtractor(BaseExtractor):
    async def extract(self, page, keywords):
        all_jobs = []
        seen = set()

        prev_sig = await self.first_result_signature(page)

        while True:
            batch = await DirectExtractor().extract(page, keywords)
            for j in batch:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    all_jobs.append(j)

            # Try Next button
            if await self.has_next_button(page):
                ok, prev_sig = await self.click_next(page, prev_sig)
                if ok:
                    continue

            # Try numeric pagination
            if await self.has_numeric_pagination(page):
                ok = await self.click_next_page_number(page)
                if ok:
                    prev_sig = await self.first_result_signature(page)
                    continue

            break

        return all_jobs


# ============================================================
# SCROLL EXTRACTOR
# ============================================================
class ScrollExtractor(BaseExtractor):
    async def extract(self, page, keywords):
        await self.scroll_full_page(page)
        return await DirectExtractor().extract(page, keywords)


# ============================================================
# UNIVERSAL EXTRACTOR — orchestrates everything
# ============================================================
class UniversalExtractor(BaseExtractor):
    async def extract(self, page, keywords):
        # 1) Apply location filter first
        await self.apply_location_filter(page)

        # 2) Search extractor
        search = await self.find_search_box(page)
        if search:
            print("🔍 Using SearchExtractor…")
            res = await SearchExtractor().extract(page, keywords)
            if res:
                return res

        # 3) Pagination extractor (Next OR numeric)
        if await self.has_next_button(page) or await self.has_numeric_pagination(page):
            print("➡ Using PaginationExtractor…")
            res = await PaginationExtractor().extract(page, keywords)
            if res:
                return res

        # 4) Scroll extractor
        print("⬇ Using ScrollExtractor…")
        res = await ScrollExtractor().extract(page, keywords)
        if res:
            return res

        # 5) Fallback direct extraction
        print("📄 Using DirectExtractor…")
        return await DirectExtractor().extract(page, keywords)


# ============================================================
# MAIN CRAWLING ENGINE
# ============================================================
async def crawl(url, keywords):
    extractor = UniversalExtractor()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)

        context = await browser.new_context(
            permissions=["geolocation"],
            geolocation={"latitude": 41.88, "longitude": -87.63},
            locale="en-US"
        )

        # Timeouts (Step 6)
        context.set_default_timeout(15000)
        context.set_default_navigation_timeout(45000)

        page = await context.new_page()

        print(f"\n🌐 Loading: {url}\n")
        # Safer navigation (Step 6)
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except:
            pass

        jobs = await extractor.extract(page, keywords)

        await browser.close()
        return jobs


# ============================================================
# CLI ENTRY POINT
# ============================================================
async def main():
    print("\n===== UNIVERSAL CRAWLER ENGINE =====\n")
    url = input("Enter career page URL: ").strip()

    jobs = await crawl(url, ROLE_KEYWORDS)

    print("\n===== RESULTS =====")
    if not jobs:
        print("❌ No matching jobs found.")
    else:
        print(f"✅ Found {len(jobs)} jobs:")
        for j in jobs:
            print(f"- {j['title']} → {j['url']}")


if __name__ == "__main__":
    asyncio.run(main())
