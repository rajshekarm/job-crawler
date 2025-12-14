class LocationDetector:

    BASIC_INPUT_SELECTORS = [
        "input[placeholder*='Location' i]",
        "input[aria-label*='Location' i]",
        "input[name*='location' i]",
        "input[id*='location' i]"
    ]

    REACT_WIDGET_SELECTORS = [
        "[role='combobox']",
        "div[role='combobox']",
        "button[role='combobox']",
        "div[aria-label*='Location' i]",
        "button[aria-label*='Location' i]",
        "label:has-text('Location')",
        "text=Location"
    ]

    DROPDOWN_SELECTORS = [
        "select[name*='location' i]",
        "select[aria-label*='Location' i]"
    ]

    @staticmethod
    async def detect(page):
        # Return tuple: (type, locator)
        for sel in LocationDetector.BASIC_INPUT_SELECTORS:
            el = page.locator(sel)
            if await el.count() > 0:
                return ("input", el.first)

        for sel in LocationDetector.REACT_WIDGET_SELECTORS:
            el = page.locator(sel)
            if await el.count() > 0:
                return ("react", el.first)

        for sel in LocationDetector.DROPDOWN_SELECTORS:
            el = page.locator(sel)
            if await el.count() > 0:
                return ("dropdown", el.first)

        return (None, None)
