from engine.detectors.search_box_detector import SearchBoxDetector
from engine.detectors.location_detector import LocationDetector
from engine.detectors.role_detector import RoleDetector

from engine.handlers.search_handler import SearchHandler
from engine.handlers.location_handler import LocationHandler
from engine.handlers.role_handler import RoleHandler

from engine.extractors.search_extractor import SearchExtractor
from engine.extractors.pagination_extractor import PaginationExtractor
from engine.extractors.scroll_extractor import ScrollExtractor
from engine.extractors.direct_extractor import DirectExtractor


class UniversalExtractor:

    async def extract(self, page):

        # 1. LOCATION FILTER
        loc_type, loc_el = await LocationDetector.detect(page)
        if loc_type:
            await LocationHandler().apply(page, loc_type, loc_el)

        # 2. ROLE FILTER
        r_type, r_el = await RoleDetector.detect(page)
        if r_type:
            await RoleHandler().apply(page, r_type, r_el)

        # 3. SEARCH BOX (fallback)
        search_box = await SearchBoxDetector.detect(page)
        if search_box:
            await SearchHandler().run_search(page, search_box)
            return await SearchExtractor().extract(page)

        # 4. PAGINATION
        next_btn = page.locator("button:has-text('Next'), a:has-text('Next')")
        if await next_btn.count() > 0:
            return await PaginationExtractor().extract(page)

        # 5. SCROLL
        sc_res = await ScrollExtractor().extract(page)
        if sc_res:
            return sc_res

        # 6. DIRECT PARSE
        return await DirectExtractor().extract(page)
