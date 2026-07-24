import os
import json
import time
import yaml
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# NOTE: adjust this path to wherever your consolidated profile YAML lives
PROFILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../Data/profile.yaml")
)

# Minimum match percentage to keep a job in the candidates list
MATCH_THRESHOLD = 65


class AIProcessor:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.profile_text = self._load_profile()

    def _load_profile(self) -> str:
        """Loads the professional profile YAML as raw text to inject into the prompt."""
        if not os.path.exists(PROFILE_PATH):
            raise FileNotFoundError(
                f"Profile file not found at {PROFILE_PATH}. "
                "Set PROFILE_PATH to your consolidated profile YAML."
            )
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            # Loaded and re-dumped to strip comments/anchors, keep token usage lean
            data = yaml.safe_load(f)
            return yaml.dump(data, allow_unicode=True, sort_keys=False)

    def get_match_score(self, raw_description: str) -> int:
        """
        SINGLE STAGE: scores the raw job description directly against the
        user's profile in one Gemini call. No compression pass — analyzing
        the full raw text once is cheaper than compress-then-analyze, and
        the output is a bare integer to minimize output tokens.
        """
        system_instruction = (
            "You are a strict job-matching scorer. You will receive a raw job "
            "description and a candidate professional profile (YAML). "
            "Compare the job's hard requirements, tech stack, seniority, and "
            "location/modality fit against the profile. "
            "Return ONLY a JSON object matching the schema: an integer "
            "match_percentage from 0 to 100. No explanation, no extra text."
        )

        response_schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "match_percentage": types.Schema(type=types.Type.INTEGER),
            },
            required=["match_percentage"],
        )

        prompt = (
            f"CANDIDATE PROFILE:\n{self.profile_text}\n\n"
            f"RAW JOB DESCRIPTION:\n{raw_description}"
        )

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            return json.loads(response.text)["match_percentage"]
        except Exception as e:
            print(f"[AI Error] Gemini 2.5 Flash processing failed: {e}")
            raise e

    def process_jobs_file(self):
        """Orchestrates the combined compression + match pipeline on jobs.json."""
        base_dir = os.path.dirname(__file__)
        jobs_path = os.path.abspath(os.path.join(base_dir, "../Data/jobs.json"))
        output_path = os.path.abspath(os.path.join(base_dir, "../Data/compressed_jobs.json"))

        if not os.path.exists(jobs_path):
            print(f"[AI Process] No active jobs.json file found at {jobs_path}. Run the scraper first.")
            return

        with open(jobs_path, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not jobs:
            print("[AI Process] The jobs.json file is empty. Nothing to process.")
            return

        print(f"\n[AI Process] Starting match-scoring pipeline for {len(jobs)} vacancies.")
        results = []

        for index, job in enumerate(jobs):
            print(f"\n--- Processing [{index + 1}/{len(jobs)}]: {job['role']} at {job['company']} ---")
            try:
                score = self.get_match_score(job["jobDescription"])

                processed_job = {
                    "role": job["role"],
                    "company": job["company"],
                    "link": job["link"],
                    "scrapedAt": job["scrapedAt"],
                    "jobDescription": job["jobDescription"],
                    "match": score,
                }
                results.append(processed_job)

                match_flag = "PASS" if score >= MATCH_THRESHOLD else "FAIL"
                print(f"[Match] {score}% ({match_flag})")

                # Spacer to stay within the free tier quota (15 RPM)
                print("[AI - Spacer] Waiting 5 seconds before the next API request...")
                time.sleep(5)

            except Exception as err:
                print(f"[Skipped] Failed to process job {job['role']}: {err}")
                continue

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n[AI Process] Pipeline completed. Output saved to: Data/compressed_jobs.json")


if __name__ == "__main__":
    processor = AIProcessor()
    processor.process_jobs_file()