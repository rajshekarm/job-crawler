from engine.extractors.direct_extractor import DirectExtractor

class ScrollExtractor:

    async def extract(self, page):
        last_height = None

        for _ in range(20):
            height = await page.evaluate("document.body.scrollHeight")
            if height == last_height:
                break
            last_height = height

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)

        return await DirectExtractor().extract(page)
