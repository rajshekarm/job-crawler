class LocationHandler:

    async def apply(self, page, detector_type, el):
        if detector_type == "input":
            await el.fill("United States")
            await page.wait_for_timeout(200)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle")
            return True

        if detector_type == "react":
            await el.click()
            await page.wait_for_timeout(300)
            box = page.locator("input[type='text']")
            if await box.count() > 0:
                await box.first.fill("United States")
                await page.wait_for_timeout(200)
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle")
                return True

        if detector_type == "dropdown":
            await el.select_option(label="United States")
            await page.wait_for_load_state("networkidle")
            return True

        return False
