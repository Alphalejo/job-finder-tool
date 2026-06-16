import os
import json
from datetime import datetime
from config import SCRAPER_CONFIG

class StorageManager:
    def __init__(self):
        # Resolve relative paths safely based on this specific file execution location
        base_dir = os.path.dirname(__file__)
        self.cache_path = os.path.abspath(os.path.join(base_dir, SCRAPER_CONFIG["storage"]["cache_file_name"]))
        self.jobs_path = os.path.abspath(os.path.join(base_dir, SCRAPER_CONFIG["storage"]["jobs_file_name"]))
        self.legacy_path = os.path.abspath(os.path.join(base_dir, SCRAPER_CONFIG["storage"]["legacy_file_name"]))
        
        # Ensure the destination data directory exists (Data/)
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

    def load_existing_links(self) -> set:
        """Initializes empty structures if they don't exist and returns the cache Set."""
        # Safety initialization guardrail for empty test batches
        for path in [self.cache_path, self.jobs_path, self.legacy_path]:
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2, ensure_ascii=False)

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cached_links = json.load(f)
                print(f"[Storage] Loaded {len(cached_links)} unique job IDs from cache.")
                return set(cached_links)
        except Exception as e:
            print(f"[Storage] Error reading cache file, starting fresh: {e}")
            return set()

    def process_and_save_new_batches(self, new_jobs: list):
        """Orchestrates the multi-file persistence streaming pipeline."""
        if not new_jobs:
            print("\n[Storage] Process finished. No new vacancies discovered to save this session.")
            return

        # 1. BACKUP REPLACED ACTIVE JOBS TO LEGACY.JSON
        legacy_data = []
        if os.path.exists(self.legacy_path):
            try:
                with open(self.legacy_path, "r", encoding="utf-8") as f:
                    legacy_data = json.load(f)
            except Exception:
                print("[Storage] Could not parse legacy file, resetting list.")

        if os.path.exists(self.jobs_path):
            try:
                with open(self.jobs_path, "r", encoding="utf-8") as f:
                    current_jobs = json.load(f)
                
                # Map active list into simplified historical legacy schema
                mapped_legacy_items = [{
                    "scrapedAt": job["scrapedAt"],
                    "company": job["company"],
                    "role": job["role"],
                    "link": job["link"]
                } for job in current_jobs]

                legacy_data.extend(mapped_legacy_items)
                with open(self.legacy_path, "w", encoding="utf-8") as f:
                    json.dump(legacy_data, f, indent=2, ensure_ascii=False)
                print(f"[Storage] Sent {len(mapped_legacy_items)} previous jobs to legacy.json")
            except Exception as e:
                print(f"[Storage] Failed to migrate active jobs to legacy archive: {e}")

        # 2. WRITE FRESH OFFERS TO JOBS.JSON (REPLACING PREVIOUS CONTENT)
        try:
            with open(self.jobs_path, "w", encoding="utf-8") as f:
                json.dump(new_jobs, f, indent=2, ensure_ascii=False)
            print(f"[Storage] Fresh batch of {len(new_jobs)} offers written to jobs.json")
        except Exception as e:
            print(f"[Storage] Failed to write fresh jobs file: {e}")

        # 3. APPEND NEW IDENTIFIERS TO HISTORICAL CACHE.JSON
        historical_cache = []
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    historical_cache = json.load(f)
            except Exception:
                pass

        new_links = [job["link"] for job in new_jobs]
        historical_cache.extend(new_links)

        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(historical_cache, f, indent=2, ensure_ascii=False)
            print(f"[Storage] Cache updated. Total indexed identifiers: {len(historical_cache)}")
        except Exception as e:
            print(f"[Storage] Failed to update identifier cache: {e}")