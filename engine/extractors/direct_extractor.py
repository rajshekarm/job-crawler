from engine.utils import is_role_match

class DirectExtractor:

    async def extract(self, page):
        results = []
        links = page.locator("a")
        count = await links.count()

        for i in range(count):
            el = links.nth(i)
            text = (await el.inner_text() or "").strip()
            href = await el.get_attribute("href")

            if text and href and is_role_match(text):
                results.append({"title": text, "url": href})

        return results
