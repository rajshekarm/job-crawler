import asyncio
from playwright.async_api import async_playwright

# ============================================================
# GLOBAL ROLE KEYWORDS
# ============================================================
ROLE_KEYWORDS = [
    "software", "engineer", "developer", "full stack",
    "backend", ".net", "c#", "swe", "sde", "platform"
]


def is_swe_role(text, keywords):
    t = text.lower()
    return any(k.lower() in t for k in keywords)


# ============================================================
# BASE EXTRACTOR (SHARED UTILITIES)
# ============================================================
class BaseExtractor:

    async def find_search_box(self, page):
        selectors = [
            "input[type='search']",
            "input[placeholder*='Search']",
            "input[placeholder*='keyword']",
            "input[aria-label*='Search']"
        ]

        for sel in selectors:
            el = page.locator(sel)
            if await el.count() > 0:
                return el.first
        return None
    
    async def apply_location_filter(self, page):
        print("🔍 Checking for location filter UI...")

        # 1. Normal input fields
        selectors = [
            "input[placeholder*='Location' i]",
            "input[aria-label*='Location' i]",
            "input[name*='location' i]",
            "input[id*='location' i]"
        ]

        for sel in selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                print(f"📍 Location input found: {sel}")
                await loc.first.click()
                await loc.first.fill("United States")
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle")
                return True

        # 2. React / custom widgets (Disney, Tesla, Netflix)
        react_selectors = [
            "[role='combobox']",                       # Disney
            "div[role='combobox']",
            "button[role='combobox']",
            "div[aria-label*='Location' i]",
            "button[aria-label*='Location' i]",
            "label:has-text('Location')",              # Many ATS sites
            "text=Location"
        ]

        for sel in react_selectors:
            widget = page.locator(sel)
            if await widget.count() > 0:
                print(f"📍 React widget found: {sel}")
                await widget.first.click()
                await page.wait_for_timeout(300)

                # Try to type into ANY input that appears
                input_box = page.locator("input[type='text'], input")
                if await input_box.count() > 0:
                    print("⌨ Typing 'United States' inside widget...")
                    await input_box.first.fill("United States")
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("networkidle")
                    return True

                # Fallback: type directly (Disney supports this)
                print("⌨ Typing via keyboard fallback...")
                await page.keyboard.type("United States")
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle")
                return True

        # 3. Standard dropdown <select>
        dropdown_selectors = [
            "select[name*='location' i]",
            "select[aria-label*='Location' i]"
        ]

        for sel in dropdown_selectors:
            sel_box = page.locator(sel)
            if await sel_box.count() > 0:
                print(f"📍 Dropdown found: {sel}")
                await sel_box.first.select_option(label="United States")
                await page.wait_for_load_state("networkidle")
                return True

        print("❌ No location filter detected on this site.")
        return False



    async def has_next_button(self, page):
        btn = page.locator(
            "button:has-text('Next'), a:has-text('Next'), button[aria-label='Next Page']"
        )
        return await btn.count() > 0

    async def click_next(self, page):
        btn = page.locator(
            "button:has-text('Next'), a:has-text('Next'), button[aria-label='Next Page']"
        )
        if await btn.count() == 0:
            return False
        try:
            await btn.first.click()
            await page.wait_for_load_state("networkidle")
            return True
        except:
            return False

    async def scroll_full_page(self, page):
        last_height = None
        for _ in range(25):
            height = await page.evaluate("document.body.scrollHeight")
            if height == last_height:
                break
            last_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

    


# ============================================================
# DIRECT EXTRACTOR (fallback plain HTML parsing)
# ============================================================
class DirectExtractor(BaseExtractor):

    async def extract(self, page, keywords):
        jobs = []
        links = page.locator("a")

        count = await links.count()
        for i in range(count):
            el = links.nth(i)
            text = (await el.inner_text()).strip()
            href = await el.get_attribute("href")

            if not text or not href:
                continue

            if is_swe_role(text, keywords):
                jobs.append({"title": text, "url": href})

        return jobs


# ============================================================
# LINK-BUTTON BASED EXTRACTOR (View Job, Apply)
# ============================================================
class LinkExtractor(BaseExtractor):

    async def extract(self, page, keywords):
        jobs = []

        btns = page.locator(
            "a:has-text('View'), a:has-text('Job'), button:has-text('View')"
        )
        count = await btns.count()

        for i in range(count):
            b = btns.nth(i)
            href = await b.get_attribute("href")
            if not href:
                continue

            card = b.locator("xpath=ancestor::div[1]")
            t = card.locator("h1, h2, h3, span")

            if await t.count() == 0:
                continue

            title = (await t.first.inner_text()).strip()

            if is_swe_role(title, keywords):
                jobs.append({"title": title, "url": href})

        return jobs


# ============================================================
# PAGINATION EXTRACTOR
# ============================================================
class PaginationExtractor(BaseExtractor):

    async def extract(self, page, keywords):
        all_jobs = []

        while True:
            direct_jobs = await DirectExtractor().extract(page, keywords)
            all_jobs.extend(direct_jobs)

            if not await self.has_next_button(page):
                break

            moved = await self.click_next(page)
            if not moved:
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
# SEARCH EXTRACTOR (keyword + pagination)
# ============================================================
class SearchExtractor(BaseExtractor):

    async def extract(self, page, keywords):
            
        search = await self.find_search_box(page)
        if not search:
            return []

        await search.fill("software")
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")

        results = []

        while True:
            direct_jobs = await DirectExtractor().extract(page, keywords)
            results.extend(direct_jobs)

            if not await self.has_next_button(page):
                break

            moved = await self.click_next(page)
            if not moved:
                break

        return results


# ============================================================
# ATS DETECTION (Workday, Greenhouse, Lever, Default)
# ============================================================
class ExtractorRouter:

    def get_extractor(self, url):
        if "myworkdayjobs" in url:
            return WorkdayExtractor()
        if "greenhouse" in url:
            return GreenhouseExtractor()
        if "lever.co" in url:
            return LeverExtractor()
        return UniversalExtractor()


# Placeholder ATS extractors — will replace later
class WorkdayExtractor(DirectExtractor): pass
class GreenhouseExtractor(DirectExtractor): pass
class LeverExtractor(DirectExtractor): pass


# ============================================================
# UNIVERSAL EXTRACTOR (main logic)
# ============================================================
class UniversalExtractor(BaseExtractor):

    async def extract(self, page, keywords):
        # 0. Apply location filter BEFORE any extraction strategy
        try:
            applied = await self.apply_location_filter(page)
            if applied:
                print("📍 Location filter applied: United States")
            else:
                print("📍 No location filter UI → will filter manually later")
        except Exception as e:
            print(f"⚠ Location filter failed: {e}")


        # 1. Search extractor
        search = await self.find_search_box(page)
        if search:
            print("🔍 Using search extractor...")
            res = await SearchExtractor().extract(page, keywords)
            if res:
                return res

        # 2. Pagination extractor
        if await self.has_next_button(page):
            print("➡ Using pagination extractor...")
            res = await PaginationExtractor().extract(page, keywords)
            if res:
                return res

        # 3. Scroll extractor
        print("⬇ Using scroll extractor...")
        res = await ScrollExtractor().extract(page, keywords)
        if res:
            return res

        # 4. Fallback
        print("📄 Using direct extractor...")
        return await DirectExtractor().extract(page, keywords)


# ============================================================
# MAIN CRAWLING ENGINE ENTRYPOINT
# ============================================================
async def crawl(url, keywords):

    router = ExtractorRouter()
    extractor = router.get_extractor(url)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
                        permissions=["geolocation"],
                        geolocation={"latitude": 41.88, "longitude": -87.63},  # Chicago example
                        locale="en-US"
                    )

        page = await context.new_page()

        print(f"\n🌐 Loading: {url}")
        await page.goto(url, wait_until="networkidle")

        jobs = await extractor.extract(page, keywords)

        await browser.close()
        return jobs


# ============================================================
# COMMAND LINE TEST RUNNER
# ============================================================
async def main():
    print("\n===== UNIVERSAL CRAWLER ENGINE =====\n")

    url = input("Enter career page URL: ").strip()
    keywords = ROLE_KEYWORDS

    jobs = await crawl(url, keywords)

    print("\n===== RESULTS =====")
    if not jobs:
        print("❌ No matching jobs found.")
    else:
        print(f"✅ Found {len(jobs)} jobs:")
        for j in jobs:
            print(f"- {j['title']} → {j['url']}")


if __name__ == "__main__":
    asyncio.run(main())
