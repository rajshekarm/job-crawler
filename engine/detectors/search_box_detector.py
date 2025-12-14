class SearchBoxDetector:

    SEARCH_SELECTORS = [
        "input[type='search']",
        "input[placeholder*='Search' i]",
        "input[placeholder*='Keyword' i]",
        "input[aria-label*='Search' i]",
        "input[id*='search' i]",
    ]

    @staticmethod
    async def detect(page):
        for sel in SearchBoxDetector.SEARCH_SELECTORS:
            box = page.locator(sel)
            if await box.count() > 0:
                return box.first
        return None
