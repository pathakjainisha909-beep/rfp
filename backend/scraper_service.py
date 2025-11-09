import os
import re
import json
import asyncio
import time
from urllib.parse import urljoin, urlparse, unquote
from playwright.sync_api import sync_playwright, Page
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import google.generativeai as genai


class ScraperService:

    def __init__(self, websocket_manager):
        self.manager = websocket_manager
        self.config = self._load_config()
        self.should_stop = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.loop = None

        load_dotenv()
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_gemini = genai.GenerativeModel("gemini-2.5-flash")

    def _load_config(self):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)

    async def stop(self):
        self.should_stop = True
        await self.manager.send_log("warning", "Stop requested")

    async def run(self):
        self.should_stop = False
        self.loop = asyncio.get_event_loop()
        sources = self.config["scraping"]["sources"]

        await self.manager.send_log("info", f"Starting scraper for {len(sources)} sources")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._run_sync_scraper, sources)

        await self.manager.send_log("success", "Scraping completed")

    def _short_message(self, text):
        return text

    def _run_sync_scraper(self, sources):
        with sync_playwright() as playwright:
            for source in sources:
                if self.should_stop:
                    break
                self._scrape_source_sync(source, playwright)

    def _scrape_source_sync(self, source_config, playwright):
        name = source_config["name"]
        output_folder = source_config["output_folder"]
        playwright_code = source_config["playwright_code"]

        self._send_log_sync("info", f"Visiting {name} Site")

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='Asia/Kolkata',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
        )
        
        page = context.new_page()
        
        # Remove 'await' - this is sync API!
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            window.navigator.chrome = {
                runtime: {}
            };
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        page.set_default_timeout(90000)

        tenders_data = []

        try:
            self._execute_playwright_code_sync(page, playwright_code)

            try:
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)
                page.wait_for_selector("table tbody tr", timeout=30000)
            except:
                pass

            pagination_config = source_config.get("pagination", {})
            nested_config = source_config.get("nested_pdf_extraction", {})

            if nested_config.get("enabled", False):
                tenders_data = self._extract_pdfs_from_nested_pages(page, nested_config)
            elif pagination_config.get("enabled", False):
                tenders_data = self._extract_tenders_with_pagination(page, pagination_config)
            else:
                tenders_data = self._extract_tenders_from_page(page)

            if tenders_data:
                self._send_log_sync("info", "Analyzing tenders")
                self._download_tenders_organized(tenders_data, output_folder)
            else:
                self._send_log_sync("warning", "No tenders found")

        except Exception as e:
            self._send_log_sync("error", f"Error scraping {name}: {str(e)}")

        finally:
            context.close()
            browser.close()

    def _send_log_sync(self, level, message, data=None):
        prefix = f"[{level.upper()}]"
        if data:
            print(f"{prefix} {message} | {data}")
        else:
            print(f"{prefix} {message}")

        short = self._short_message(message)

        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.manager.send_log(level, short),
                    self.loop
                )
            except:
                pass

    def _execute_playwright_code_sync(self, page: Page, code: str):
        lines = code.strip().split('\n')
        for line in lines:
            if self.should_stop:
                break
            try:
                exec(line, {"page": page})
                time.sleep(1)
            except Exception as e:
                self._send_log_sync("error", f"Navigation error: {str(e)}")

    def _extract_tenders_from_page(self, page: Page):
        tenders = []
        try:
            rows = page.locator("table tbody tr").all()
            for row in rows:
                cells = row.locator("td").all()
                if len(cells) < 2:
                    continue

                description = cells[0].inner_text().strip()
                ref_number = cells[1].inner_text().strip()
                if not description or not ref_number:
                    continue

                pdf_links = []
                for cell in cells:
                    links = cell.locator("a[href*='.pdf']").all()
                    for link in links:
                        href = link.get_attribute("href")
                        if href:
                            full_url = urljoin(page.url, href)
                            pdf_links.append({'url': full_url, 'name': ref_number})

                if pdf_links:
                    tenders.append({'description': description, 'ref_number': ref_number, 'pdfs': pdf_links})
        except:
            pass

        return tenders

    def _extract_tenders_with_pagination(self, page: Page, config):
        max_pages = config.get("max_pages", 1)
        extract_only_page = config.get("extract_only_page", None)
        out = []

        for p in range(1, max_pages + 1):
            if self.should_stop:
                break
            
            self._send_log_sync("info", f"Searched Page {p}")
            
            if extract_only_page is None or p == extract_only_page:
                extracted = self._extract_tenders_from_page(page)
                if extracted:
                    for tender in extracted:
                        ref = tender['ref_number']
                        desc = tender['description']
                        self._send_log_sync("success", f"Relevant tender found: {ref} - {desc}")
                    out.extend(extracted)
            
            if p < max_pages:
                try:
                    next_page = page.locator(f"a[role='link']:has-text('{p+1}')").first
                    if next_page.is_visible():
                        next_page.click()
                        time.sleep(3)
                    else:
                        break
                except:
                    break

        return out

    def _sanitize_folder_name(self, name):
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name.strip()[:100]

    def _create_tender_folder_name(self, d, r):
        d = ' '.join(d.split()[:8])
        return self._sanitize_folder_name(f"{r} - {d}")

    def _download_tenders_organized(self, tenders_data, base_output_folder):
        os.makedirs(base_output_folder, exist_ok=True)

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        all_downloads = []
        for tender in tenders_data:
            folder = self._create_tender_folder_name(tender['description'], tender['ref_number'])
            tender_path = os.path.join(base_output_folder, folder)
            os.makedirs(tender_path, exist_ok=True)
            
            for pdf in tender['pdfs']:
                url = pdf['url']
                filename = unquote(os.path.basename(urlparse(url).path)) or (pdf['name'] + ".pdf")
                filename = self._sanitize_folder_name(filename)
                if not filename.endswith(".pdf"):
                    filename += ".pdf"
                filepath = os.path.join(tender_path, filename)
                all_downloads.append((url, filepath, tender['ref_number'], filename))
        
        total = len(all_downloads)
        completed = [0]
        
        def download_file(item):
            url, filepath, ref, filename = item
            try:
                self._send_log_sync("info", f"Extracting Annexure ({completed[0]+1}/{total}): {ref}")
                resp = session.get(url, stream=True, timeout=30)
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=32768):
                        if chunk:
                            f.write(chunk)
                completed[0] += 1
                return True
            except Exception as e:
                self._send_log_sync("warning", f"Failed: {filename} - {str(e)}")
                completed[0] += 1
                return False
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(download_file, all_downloads))
        
        session.close()
        success_count = sum(results)
        self._send_log_sync("success", f"Downloaded {success_count}/{total} annexures")