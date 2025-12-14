from engine.extractors.direct_extractor import DirectExtractor

class PaginationExtractor:

    async def extract(self, page):
        all_jobs = []
        direct = DirectExtractor()

        while True:
            all_jobs.extend(await direct.extract(page))

            next_btn = page.locator("button:has-text('Next'), a:has-text('Next')")
            if await next_btn.count() == 0:
                break

            await next_btn.first.click()
            await page.wait_for_load_state("networkidle")

        return all_jobs
