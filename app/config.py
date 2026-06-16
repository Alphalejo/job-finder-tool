import os

SCRAPER_CONFIG = {
    "search": {
        # Pure analytics roles (Data Engineer completely excluded)
        "roles": '("Data Analyst" OR "Analista de datos" OR "Data Scientist" OR "Cientifico de datos" OR "BI Analyst" OR "Analista BI")',
        
        # Keywords to capture cross-border remote and hybrid vacancies
        "global_remote_keywords": 'AND ("Remote" OR "Remoto" OR "Latam" OR "Latin America" OR "Worldwide" OR "Anywhere")',
        
        # Anchored to Colombia to ensure legal and time-zone compatibility
        "location": "Colombia",
        
        # Time range: Past 24 hours (f_TPR=r86400) or Past week (f_TPR=r604800)
        "time_range_param": "f_TPR=r604800"
    },
    "tuning": {
        "max_scroll_iterations": 3,
        "max_offers_to_process": 2,
        "page_load_timeout_ms": 20000
    },
    "delays": {
        "scroll_wait_ms": 2000,
        "card_click_wait_ms": 1500
    },
    "storage": {
        "cache_file_name": "../Data/cache.json",
        "jobs_file_name": "../Data/jobs.json",
        "legacy_file_name": "../Data/legacy.json"
    }
}