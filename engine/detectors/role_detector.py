class RoleDetector:

    BASIC_ROLE_INPUTS = [
        "input[placeholder*='Role' i]",
        "input[placeholder*='Keyword' i]",
        "input[aria-label*='Role' i]",
        "input[name*='keyword' i]"
    ]

    @staticmethod
    async def detect(page):
        # Detect role/title filter box
        for sel in RoleDetector.BASIC_ROLE_INPUTS:
            el = page.locator(sel)
            if await el.count() > 0:
                return ("input", el.first)

        # Some sites reuse the same search box for roles → fallback
        search_box = page.locator("input[type='search']")
        if await search_box.count() > 0:
            return ("search", search_box.first)

        return (None, None)
