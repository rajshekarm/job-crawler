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
import re
from typing import Optional, Tuple

class BaseExtractor:
    # ---------------------------- SAFE WAIT HELPERS ----------------------------
    async def safe_networkidle(self, page, timeout_ms: int = 8000):
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except:
            pass

    async def _try_click_apply(self, page):
        """
        Some UIs require Apply/Done/Show results after selecting location.
        Best-effort click.
        """
        btn = page.locator("""
            button:has-text("Apply"),
            button:has-text("Done"),
            button:has-text("Show results"),
            button:has-text("Update"),
            button:has-text("Search")
        """).first
        try:
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await self.safe_networkidle(page)
        except:
            pass

    async def _clear_input(self, page, loc):
        try:
            await loc.click()
            # Windows/Linux
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
        except:
            try:
                # macOS fallback
                await page.keyboard.press("Meta+A")
                await page.keyboard.press("Backspace")
            except:
                # last resort
                try:
                    await loc.fill("")
                except:
                    pass

    async def _type_united_and_select_us(
        self,
        page,
        input_locator,
        query: str = "United",
        target_pattern: str = r"\bUnited States\b",
        type_delay_ms: int = 120,
        suggestion_timeout_ms: int = 8000,
    ) -> bool:
        """
        Types only 'United' (or your query), then selects 'United States' from suggestions.
        Does NOT type 'States' unless you change the query.

        Returns True if it clicked the 'United States' suggestion.
        """
        await self._clear_input(page, input_locator)

        # Type like a user (triggers key events / debounce)
        try:
            await input_locator.type(query, delay=type_delay_ms)
        except:
            await page.keyboard.type(query, delay=type_delay_ms)

        # Wait for suggestion list to appear
        options = page.locator("li[role='option'], div[role='option']")
        try:
            await options.first.wait_for(state="visible", timeout=suggestion_timeout_ms)
        except:
            return False

        # Click specifically "United States" if present
        us = options.filter(has_text=re.compile(target_pattern, re.I)).first
        if await us.count() > 0:
            try:
                await us.click()
                await self.safe_networkidle(page)
                return True
            except:
                return False

        # Suggestions exist but US not present -> do NOT press Enter blindly here
        return False

    # ---------------------------- LOCATION FILTER DETECTION (IMPROVED) ----------------------------
    async def apply_location_filter(self, page) -> bool:
        print("\n🔍 Checking for location filter UI...\n")

        async def select_us_from_input(input_locator) -> bool:
            # Type 'United' and select 'United States' if it appears
            picked = await self._type_united_and_select_us(
                page,
                input_locator,
                query="United",
                target_pattern=r"\bUnited States\b",
                type_delay_ms=120,
                suggestion_timeout_ms=8000,
            )

            if picked:
                await self._try_click_apply(page)
                await self.safe_networkidle(page)
                return True

            # Fallback: some widgets accept free text
            try:
                await page.keyboard.press("Enter")
                await self._try_click_apply(page)
                await self.safe_networkidle(page)
                return True
            except:
                return False

        # 0) Best case: <label for="...">Location</label> -> input#...
        label = page.locator("label:has-text('Location')").first
        try:
            if await label.count() > 0 and await label.is_visible():
                for_id = await label.get_attribute("for")
                if for_id:
                    target = page.locator(f"#{for_id}").first
                    if await target.count() > 0 and await target.is_visible():
                        print("📍 Location input found via label[for] association")
                        return await select_us_from_input(target)
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
            try:
                if await loc.count() > 0 and await loc.is_visible():
                    print(f"📍 Location filter found: {sel}")
                    return await select_us_from_input(loc)
            except:
                continue

        # 2) Checkbox-style location panel
        # Try clicking a label that contains "United States" (common in facet filters)
        try:
            checkbox_label = page.locator("""
                label:has-text("United States"),
                div:has(label:has-text("United States"))
            """).first

            if await checkbox_label.count() > 0 and await checkbox_label.is_visible():
                print("📍 Location checkbox option found: United States")
                try:
                    await checkbox_label.click()
                except:
                    # fallback: click/check the first checkbox in that area
                    cb = page.locator("input[type='checkbox']").first
                    if await cb.count() > 0:
                        await cb.check()

                await self._try_click_apply(page)
                await self.safe_networkidle(page)
                return True
        except:
            pass

        # 3) React / JS widgets — try to scope to Location first
        react_selectors = [
            "div:has-text('Location') [role='combobox']",
            "div[aria-label*='location' i] [role='combobox']",
            "button[aria-label*='location' i]",
            "div[aria-label*='location' i]",
            "[role='combobox']"  # broad fallback LAST
        ]

        for sel in react_selectors:
            widget = page.locator(sel).first
            try:
                if await widget.count() > 0 and await widget.is_visible():
                    print(f"📍 React widget found: {sel}")
                    try:
                        await widget.click()
                    except:
                        pass

                    # After opening, try the active text input
                    input_box = page.locator("input[type='text'], input").first
                    if await input_box.count() > 0 and await input_box.is_visible():
                        return await select_us_from_input(input_box)
            except:
                continue

        # 4) <select> dropdown
        dropdowns = [
            "select[name*='location' i]",
            "select[aria-label*='Location' i]"
        ]
        for sel in dropdowns:
            box = page.locator(sel).first
            try:
                if await box.count() > 0 and await box.is_visible():
                    print(f"📍 Dropdown found: {sel}")
                    try:
                        await box.select_option(label="United States")
                    except:
                        try:
                            await box.select_option(value="US")
                        except:
                            return False

                    await self._try_click_apply(page)
                    await self.safe_networkidle(page)
                    return True
            except:
                continue

        print("❌ No location filter detected.\n")
        return False
    
    async def _type_prefix_search_and_submit(
    self,
    page,
    search_input,
    query: str,
    prefix_len: int = 4,
    type_delay_ms: int = 70,
    suggestion_timeout_ms: int = 3000,
    results_timeout_ms: int = 8000,
    strict_suggestion: bool = True, 
) -> bool:
            """
            Job search helper:
            - Clears the search input
            - Types only a prefix first (default 4 chars)
            - If suggestions appear and one matches the FULL query -> click it
            - Otherwise types the rest of the query and presses Enter
            - Enter is only pressed after the full query is present in the input

            Returns True if it attempted the search.
            """
            if not query:
                return False

            # focus + clear
            try:
                await self._clear_input(page, search_input)
            except:
                try:
                    await search_input.click()
                except:
                    return False

            prefix_len = max(1, min(prefix_len, len(query)))
            prefix = query[:prefix_len]
            rest = query[prefix_len:]

            # type prefix like a user
            try:
                await search_input.type(prefix, delay=type_delay_ms)
            except:
                try:
                    await page.keyboard.type(prefix, delay=type_delay_ms)
                except:
                    return False

            options = page.locator("li[role='option'], div[role='option']")
            clicked_suggestion = False

            # wait briefly for suggestions; if present try to click the best match
            try:
                await options.first.wait_for(state="visible", timeout=suggestion_timeout_ms)

                # ✅ only click if exact match (ignoring case + extra spaces)
                if strict_suggestion:
                    want = re.sub(r"\s+", " ", query).strip().lower()

                    # check first N suggestions (avoid scanning hundreds)
                    n = min(await options.count(), 25)
                    for i in range(n):
                        opt = options.nth(i)
                        txt = (await opt.inner_text() or "").strip()
                        got = re.sub(r"\s+", " ", txt).strip().lower()

                        if got == want:
                            await opt.click()
                            clicked_suggestion = True
                            break
                else:
                    # non-strict mode (contains match) — not recommended for your case
                    best = options.filter(has_text=re.compile(re.escape(query), re.I)).first
                    if await best.count() > 0:
                        await best.click()
                        clicked_suggestion = True
            except:
                pass

            # If we didn't click a suggestion, finish typing full query then Enter
            if not clicked_suggestion:
                if rest:
                    try:
                        await search_input.type(rest, delay=type_delay_ms)
                    except:
                        await page.keyboard.type(rest, delay=type_delay_ms)

                try:
                    await page.keyboard.press("Enter")
                except:
                    return False

            # Let results load
            await page.wait_for_timeout(250)
            await self.safe_networkidle(page, timeout_ms=results_timeout_ms)
            return True
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

    async def click_next(self, page, prev_signature=None):
        btn = await self._next_locator(page)
        if await btn.count() == 0:
            return (False, prev_signature)

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

        old_url = page.url

        try:
            # ✅ ensure it's clickable
            await btn.scroll_into_view_if_needed()
            await btn.click(timeout=15000)
        except:
            return (False, prev_signature)

        # ✅ Disney sometimes doesn't trigger full navigations; wait for results instead
        try:
            await page.wait_for_selector("a[href*='/en/job/'], a[href*='/job/']", timeout=15000)
        except:
            pass

        await self.safe_networkidle(page, timeout_ms=8000)

        new_sig = await self.first_result_signature(page)
        if page.url != old_url:
            return (True, new_sig)
        if prev_signature and new_sig and new_sig != prev_signature:
            return (True, new_sig)

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
            links = pager.locator("a")
            if await links.count() == 0:
                return False
            for i in range(min(await links.count(), 30)):
                txt = ((await links.nth(i).inner_text()) or "").strip()
                if txt.isdigit():
                    return True
            return False
        except:
            return False

    async def click_next_page_number(self, page) -> bool:
        pager = page.locator("""
            nav[aria-label*="pagination" i],
            .pagination,
            ul.pagination,
            [role="navigation"] .pagination
        """).first
        if await pager.count() == 0:
            return False

        current_num = None
        try:
            cur = pager.locator('[aria-current="page"]').first
            if await cur.count() > 0:
                txt = ((await cur.inner_text()) or "").strip()
                if txt.isdigit():
                    current_num = int(txt)
        except:
            pass

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
    async def first_result_signature(self, page) -> Optional[str]:
        """
        A lightweight 'did content change?' signal.
        We scan a few anchors and pick the first one that looks like a SWE role.
        (Assumes is_swe_role() exists in your module.)
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

        # ✅ Fast path: job links only (Disney + many boards)
        job_link_locators = [
            "a[href*='/en/job/']",
            "a[href*='/job/']",
        ]

        links = None
        for sel in job_link_locators:
            loc = page.locator(sel)
            if await loc.count() > 0:
                links = loc
                break

        # Fallback: scan all anchors only if needed
        if links is None:
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
            if not abs_url or abs_url in seen:
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
        page_no = 1


        for q in SEARCH_QUERIES:
            try:
                ok = await self._type_prefix_search_and_submit(
                        page,
                        search,
                        q,
                        prefix_len=4,              
                        type_delay_ms=70,
                        suggestion_timeout_ms=3000,
                        results_timeout_ms=8000
                    )
                if not ok:
                    continue
            except:
                continue

            await page.wait_for_timeout(300)
            await self.safe_networkidle(page, timeout_ms=8000)

            prev_sig = await self.first_result_signature(page)

            while True:
                print("scanning the page")
                batch = await DirectExtractor().extract(page, keywords)
                for j in batch:
                    if j["url"] not in seen:
                        seen.add(j["url"])
                        all_results.append(j)
                print(f"📄 Collected {len(batch)} items on this page | total={len(all_results)}")
                if page_no >= 10:
                    print("🛑 Reached max pages (20). Stopping pagination.")
                    #setting page number to 1 to start searching for other key words
                    page_no = 1
                    break
                # Try Next button first
                if await self.has_next_button(page):
                    ok, prev_sig = await self.click_next(page, prev_sig)
                    if ok:
                        page_no += 1
                        continue

                # Then try numeric pagination
                if await self.has_numeric_pagination(page):
                    ok = await self.click_next_page_number(page)
                    if ok:
                        prev_sig = await self.first_result_signature(page)
                        page_no += 1
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
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="pw-profile",
            headless=False,
        )
        page = await context.new_page()
        await page.goto("https://www.tesla.com/careers", wait_until="domcontentloaded")
        page = await context.new_page()

        print(f"\n🌐 Loading: {url}\n")
        # Safer navigation (Step 6)
        resp = await page.goto(url, wait_until="domcontentloaded")
        print("status:", resp.status if resp else None, "final_url:", page.url)
        title = await page.title()
        html = await page.content()

        print("title:", title)
        print("blocked:", ("Access Denied" in html) or ("errors.edgesuite.net" in html))
        print("len(html):", len(html))
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
