import asyncio
from playwright.async_api import async_playwright
from engine.router import ExtractorRouter
from engine.utils import ROLE_KEYWORDS

async def crawl(url, keywords):

    router = ExtractorRouter()
    extractor = router.get_extractor(url)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)

        context = await browser.new_context(
            permissions=["geolocation"],
            geolocation={"latitude": 41.88, "longitude": -87.63},
            locale="en-US"
        )

        page = await context.new_page()

        print(f"\n🌐 Loading: {url}\n")
        await page.goto(url, wait_until="networkidle")

        jobs = await extractor.extract(page, keywords)

        await browser.close()
        return jobs


async def main():
    print("\n===== UNIVERSAL CRAWLER ENGINE =====\n")
    url = input("Enter career page URL: ").strip()

    jobs = await crawl(url, ROLE_KEYWORDS)

    print("\n===== RESULTS =====")
    if not jobs:
        print("❌ No matching jobs found.")
    else:
        print(f"✅ Found {len(jobs)} jobs:")
        for j in jobs:
            print(f"- {j['title']} → {j['url']}")

if __name__ == "__main__":
    asyncio.run(main())
