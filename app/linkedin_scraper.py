import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright
from config import SCRAPER_CONFIG
from storage_manager import StorageManager

def run_scraper():
    storage = StorageManager()
    existing_links_set = storage.load_existing_links()
    
    # Dynamic cross-border target URL compilation
    raw_query = f"{SCRAPER_CONFIG['search']['roles']} {SCRAPER_CONFIG['search']['global_remote_keywords']}"
    encoded_keywords = urllib.parse.quote(raw_query)
    encoded_location = urllib.parse.quote(SCRAPER_CONFIG["search"]["location"])
    search_url = f"https://www.linkedin.com/jobs/search?keywords={encoded_keywords}&location={encoded_location}&{SCRAPER_CONFIG['search']['time_range_param']}"
    
    print(f"\n[Scraper] Navigating to Cross-Border Remote Feed:\n{search_url}\n")
    
    with sync_playwright() as p:
        # headless=True avoids spawning the Chromium window to preserve hardware resources
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_selector(".jobs-search__results-list", timeout=SCRAPER_CONFIG["tuning"]["page_load_timeout_ms"])
        except Exception as e:
            print(f"[Scraper] Failed to load job list. CAPTCHA might be required or link failed: {e}")
            browser.close()
            return

        # Simulate programmatic scrolling to lazy-load extra job listings
        print("[Scraper] Triggering page scroll to load more listings...")
        for _ in range(SCRAPER_CONFIG["tuning"]["max_scroll_iterations"]):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            page.wait_for_timeout(SCRAPER_CONFIG["delays"]["scroll_wait_ms"])

        job_cards = page.query_selector_all(".jobs-search__results-list li")
        print(f"[Scraper] Detected {len(job_cards)} potential job listings.")

        new_scraped_jobs = []
        target_processing_limit = min(len(job_cards), SCRAPER_CONFIG["tuning"]["max_offers_to_process"])

        # CORE PROCESSING LOOP
        for i in range(target_processing_limit):
            try:
                card = job_cards[i]
                card.scroll_into_view_if_needed()

                # Resiliently wait for any anchor link element to render inside the card markup
                try:
                    card.wait_for_selector("a", timeout=4000)
                except Exception:
                    print(f"[Warning] No anchor links found inside card listing [{i + 1}]. Skipping...")
                    continue

                # Extract cleaned target URL via evaluation scripts inside the page context
                cleaned_url = card.evaluate("""
                    (el) => {
                        const anchors = Array.from(el.querySelectorAll('a'));
                        for (const a of anchors) {
                            const href = a.getAttribute('href');
                            if (href && (href.includes('/jobs/') || href.includes('currentJobId'))) {
                                return href.split('?')[0];
                            }
                        }
                        const firstAnchor = el.querySelector('a');
                        return firstAnchor ? (firstAnchor.getAttribute('href') || '').split('?')[0] : '';
                    }
                """)

                if not cleaned_url:
                    print(f"[Skipped] Link extraction failed for job card [{i + 1}/{target_processing_limit}].")
                    continue

                if cleaned_url in existing_links_set:
                    print(f"[Skipped] Job [{i + 1}/{target_processing_limit}] already exists in historical cache.")
                    continue

                # --- NEW MODAL DISMISSAL & FORCED CLICK GUARD ---
                # Check if LinkedIn threw a sign-in wall/modal and dismiss it by clicking its close button
                try:
                    close_modal_btn = page.query_selector("button.modal__dismiss, .modal__overlay .modal__dismiss")
                    if close_modal_btn and close_modal_btn.is_visible():
                        close_modal_btn.click()
                        page.wait_for_timeout(500)
                        print("[Scraper] Dismissed LinkedIn sign-in modal barrier.")
                except Exception:
                    pass # No modal discovered, carry on safely

                # Force the click action by bypassing top-level overlay pointer interceptions
                try:
                    card.click(force=True, timeout=5000)
                    page.wait_for_timeout(SCRAPER_CONFIG["delays"]["card_click_wait_ms"])
                except Exception as click_err:
                    print(f"[Warning] Standard card click intercepted, retrying via JS dispatcher: {click_err}")
                    # Ultimate fallback: Trigger click directly via browser JavaScript engine context
                    page.evaluate("(el) => el.click()", card)
                    page.wait_for_timeout(SCRAPER_CONFIG["delays"]["card_click_wait_ms"])
                # --- END OF MODAL GUARD ---

                # Scraping extraction of metadata fields inside the open description context
                job_data = page.evaluate("""
                    (targetLink) => {
                        const titleEl = document.querySelector('.top-card-layout__title') || document.querySelector('.base-search-card__title') || document.querySelector('h2');
                        const companyEl = document.querySelector('.topcard__org-name-link') || document.querySelector('.base-search-card__subtitle') || document.querySelector('.topcard__flavor');
                        const descriptionEl = document.querySelector('.description__text') || document.querySelector('.show-more-less-html__markup') || document.querySelector('.jobs-description');

                        return {
                            "role": titleEl ? titleEl.innerText.trim() : 'Unknown Role',
                            "company": companyEl ? companyEl.innerText.trim() : 'Unknown Company',
                            "link": targetLink,
                            "jobDescription": descriptionEl ? descriptionEl.innerText.trim() : 'No Description Available'
                        };
                    }
                """, cleaned_url)

                # Append execution time metric
                job_data["scrapedAt"] = datetime.utcnow().isoformat() + "Z"
                
                print(f"[Extracted] -> {job_data['role']} at {job_data['company']}")
                
                existing_links_set.add(cleaned_url)
                new_scraped_jobs.append(job_data)

            except Exception as error:
                print(f"[Error] Failed to process card index {i}: {error}")

        # Execute downstream pipeline storage updates
        storage.process_and_save_new_batches(new_scraped_jobs)
        browser.close()
        print("[Scraper] Global workflow execution finished.")

if __name__ == "__main__":
    run_scraper()