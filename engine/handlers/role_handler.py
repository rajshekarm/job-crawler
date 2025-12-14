from engine.utils import best_match_query

class RoleHandler:

    async def apply(self, page, detector_type, el):
        if detector_type in ("input", "search"):
            await el.fill(best_match_query())
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle")
            return True

        return False
