import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.canarabank.bank.in/")
    page.get_by_role("button", name="Select English language").click()
    page.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("searchbox", name="Search for content").click()
    page.get_by_role("searchbox", name="Search for content").fill("Tende")
    page.get_by_role("link", name="Tenders", exact=True).click()
    with page.expect_popup() as page1_info:
        page.get_by_role("link", name="Tender (.pdf - 1.27 MB)").click()
    page1 = page1_info.value
    page.get_by_role("link", name="2", exact=True).click()
    page.get_by_role("link", name="3", exact=True).click()
    page1.close()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
