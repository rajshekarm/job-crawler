from engine.utils import best_match_query

class SearchHandler:

    async def run_search(self, page, box):
        query = best_match_query()
        await box.fill(query)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
