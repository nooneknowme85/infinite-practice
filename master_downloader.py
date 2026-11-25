import os
import sys
import json
import time
import zipfile
import requests
import re
import argparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Default API and Headers
BASE_API = "https://pwsecure.gourav23032009.workers.dev/api/pw/v3"

HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://pwx.pages.dev",
    "referer": "https://pwx.pages.dev/batch/676e4dee1ec923bc192f38c9/infinite-practice",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36"
}

BATCHES = {
    "11th JEE": "676e4dee1ec923bc192f38c9",
    "12th JEE": "65dc6fbabb55350018d555b7",
    "11th NEET": "676e5677418e84037bd6247c",
    "12th NEET": "65dc6fbaf5bcd500180102cd"
}

OUTPUT_ROOT = "downloaded_questions"
STATE_FILE = os.path.join(OUTPUT_ROOT, "state_tracker.json")
CONSECUTIVE_EMPTY_LIMIT = 10  # Stop only after 10 consecutive batches give 0 new questions
NEET_ALLOWED_SUBJECTS = {"botany", "zoology"}  # NEET Physics & Chemistry are identical to JEE

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def create_resilient_session():
    """Create a requests session with low-level HTTP retry for bad connections."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

SESSION = create_resilient_session()

def safe_api_call(method, url, json_data=None, max_retries=3, base_delay=3.0):
    """
    Resilient network wrapper:
    - Retries 3 times on connection drops, timeouts, DNS errors.
    - Handles HTTP 403 'too many requests' rate-limits with exponential backoff.
    """
    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = SESSION.get(url, headers=HEADERS, timeout=30)
            else:
                resp = SESSION.post(url, headers=HEADERS, json=json_data, timeout=30)

            # Check if rate-limited by backend proxy
            if resp.status_code == 403 and "too many requests" in resp.text.lower():
                pause = 15 * attempt
                print(f"\n  [Rate Limited] Server busy. Cooling down for {pause}s (Attempt {attempt}/{max_retries})...")
                time.sleep(pause)
                continue

            return resp

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as net_err:
            wait_time = base_delay * (2 ** (attempt - 1))
            print(f"\n  [Bad Network] {type(net_err).__name__}. Retrying in {wait_time:.1f}s (Attempt {attempt}/{max_retries})...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"\n  [Network Exception] {e}. Retrying in {base_delay}s (Attempt {attempt}/{max_retries})...")
            time.sleep(base_delay)

    return None

class StateTracker:
    """Tracks overall download progress so the script can resume anytime seamlessly."""
    def __init__(self, filepath=STATE_FILE):
        self.filepath = filepath
        self.state = {
            "completed_chapters": {},
            "in_progress_chapters": {}
        }
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                # Purge any broken 0-question entries from earlier runs
                comp = self.state.get("completed_chapters", {})
                self.state["completed_chapters"] = {
                    k: v for k, v in comp.items() if v.get("downloaded_count", 0) > 0
                }
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        temp_file = self.filepath + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, self.filepath)

    def is_chapter_completed(self, batch_id, chapter_id, out_file=None):
        key = f"{batch_id}:{chapter_id}"
        entry = self.state.get("completed_chapters", {}).get(key)
        if not entry or entry.get("downloaded_count", 0) <= 0:
            return False
        if out_file and not os.path.exists(out_file):
            return False
        return True

    def mark_chapter_in_progress(self, batch_id, chapter_id, batch_name, subject_name, chapter_name, count):
        key = f"{batch_id}:{chapter_id}"
        self.state.setdefault("in_progress_chapters", {})[key] = {
            "batch_name": batch_name,
            "subject_name": subject_name,
            "chapter_name": chapter_name,
            "downloaded_count": count,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save()

    def mark_chapter_completed(self, batch_id, chapter_id, batch_name, subject_name, chapter_name, count):
        key = f"{batch_id}:{chapter_id}"
        self.state.setdefault("completed_chapters", {})[key] = {
            "batch_name": batch_name,
            "subject_name": subject_name,
            "chapter_name": chapter_name,
            "downloaded_count": count,
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        if key in self.state.get("in_progress_chapters", {}):
            del self.state["in_progress_chapters"][key]
        self.save()

TRACKER = StateTracker()


def atomic_write_json(filepath, data):
    """Write JSON atomically to prevent file corruption if stopped midway."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    temp_file = filepath + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, filepath)


def load_existing_questions(filepath):
    """Load existing questions keyed by questionId and count them by difficulty."""
    questions_dict = {}
    diff_counts = {1: 0, 2: 0, 3: 0}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for q in existing:
                    qid = q.get("questionId")
                    if qid and qid not in questions_dict:
                        questions_dict[qid] = q
                        d = q.get("difficulty")
                        if d in diff_counts:
                            diff_counts[d] += 1
        except Exception as e:
            print(f"  [Warning] Could not read {filepath}: {e}")
    return questions_dict, diff_counts


def merge_zip_into_folder(zip_path, dest_root):
    """Extract a batch zip into dest_root, merging any overlapping chapter JSONs."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir() or not member.filename.endswith(".json"):
                continue
            target_path = os.path.join(dest_root, member.filename)
            raw_bytes = zf.read(member.filename)
            if not os.path.exists(target_path):
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "wb") as out_f:
                    out_f.write(raw_bytes)
            else:
                try:
                    incoming = json.loads(raw_bytes.decode("utf-8"))
                    if isinstance(incoming, list):
                        existing_dict, _ = load_existing_questions(target_path)
                        for q in incoming:
                            qid = q.get("questionId")
                            if qid and qid not in existing_dict:
                                existing_dict[qid] = q
                        atomic_write_json(target_path, list(existing_dict.values()))
                except Exception:
                    pass


def download_existing_releases(repo, token, dest_root=OUTPUT_ROOT):
    """Download existing batch zips and state_tracker.json from GitHub Releases to resume seamlessly."""
    if not repo:
        print("[Release Sync] No repo specified, skipping release download.")
        return
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
    print(f"[Release Sync] Checking existing releases in {repo}...")
    r = requests.get(api_url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"[Release Sync] Could not fetch releases ({r.status_code}): {r.text[:150]}")
        return

    releases = r.json()
    os.makedirs("temp_release_zips", exist_ok=True)
    os.makedirs(dest_root, exist_ok=True)

    seen_assets = set()
    target_zip_names = {"11th_JEE.zip", "12th_JEE.zip", "11th_NEET.zip", "12th_NEET.zip"}
    merged_completed = {}

    # Process oldest to newest so newer releases merge cleanly on top of older ones
    for rel in reversed(releases):
        rel_id = rel.get("id", rel.get("tag_name", ""))
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            dl_url = asset.get("url")
            dl_headers = dict(headers)
            dl_headers["Accept"] = "application/octet-stream"

            # Merge completed chapters from all state_tracker.json assets across releases (ignore 0-count entries)
            if name == "state_tracker.json":
                resp = requests.get(dl_url, headers=dl_headers, timeout=30)
                if resp.status_code == 200:
                    try:
                        st = resp.json()
                        for k, v in st.get("completed_chapters", {}).items():
                            if v.get("downloaded_count", 0) > 0:
                                merged_completed[k] = v
                    except Exception:
                        pass
            elif (name in target_zip_names or name.startswith("updated_") or name == "new_questions_only.zip") and (rel_id, name) not in seen_assets:
                seen_assets.add((rel_id, name))
                print(f"  -> Downloading {name} from release '{rel.get('tag_name')}'...")
                resp = requests.get(dl_url, headers=dl_headers, stream=True, timeout=120)
                if resp.status_code == 200:
                    local_zip = os.path.join("temp_release_zips", f"{rel_id}_{name}")
                    with open(local_zip, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    print(f"     Extracting/merging {name} into '{dest_root}/'...")
                    merge_zip_into_folder(local_zip, dest_root)
                else:
                    print(f"     [Warning] Failed to download {name} ({resp.status_code})")

    if merged_completed:
        TRACKER.state.setdefault("completed_chapters", {}).update(merged_completed)
        TRACKER.save()
        print(f"[Release Sync] Loaded {len(merged_completed)} already-completed chapters from state_tracker.json.")

    print(f"[Release Sync] Finished syncing {len(seen_assets)} release archive(s).\n")

def get_subjects(batch_id):
    """Fetch subjects and examCategory for a batch."""
    url = f"{BASE_API}/batches/{batch_id}/infinitePractice/subjects"
    r = safe_api_call("GET", url)
    if r and r.status_code == 200:
        res = r.json()
        if res.get("success"):
            data = res.get("data", {})
            return data.get("examCategory"), data.get("subjects", [])
    return None, []

def get_chapters(batch_id, subject_id):
    """Fetch chapters for a subject."""
    url = f"{BASE_API}/batches/{batch_id}/infinitePractice/chapters?subjectId={subject_id}"
    r = safe_api_call("GET", url)
    if r and r.status_code == 200:
        res = r.json()
        if res.get("success"):
            return res.get("data", [])
    return []

def start_test(batch_id, exam_category, chapter_id, class_id, subject_id, count=90, difficulty_level=None):
    """Generate a 90-question practice test."""
    if difficulty_level is None:
        difficulty_level = [1, 2, 3]
    url = f"{BASE_API}/test-service/{batch_id}/infinitePractice/v2/start-test"
    payload = {
        "exams": [],
        "examCategory": exam_category,
        "testMode": "EXAM",
        "questionsCount": count,
        "chapters": [{"chapterId": chapter_id, "classId": class_id}],
        "subject": subject_id,
        "difficultyLevel": difficulty_level,
        "isReattempt": False,
        "language": "English"
    }
    r = safe_api_call("POST", url, json_data=payload)
    if r and r.status_code == 201:
        data = r.json().get("data", {})
        return data.get("_id"), data.get("questions", [])
    return None, []

def submit_test(test_id):
    """Submit test session to unlock solutions."""
    url = f"{BASE_API}/test-service/{test_id}/infinitePractice/submit-test"
    r = safe_api_call("POST", url, json_data={})
    return r is not None and r.status_code == 201

def get_solutions(test_id):
    """Retrieve full questions with marked correct answers & solutions."""
    url = f"{BASE_API}/test-service/{test_id}/infinitePractice/test-solution"
    r = safe_api_call("GET", url)
    if r and r.status_code == 200:
        return r.json().get("data", {}).get("questionsResponses", [])
    return []

def download_chapter(batch_name, batch_id, exam_category, subject_name, chapter, delay=2.5):
    chapter_id = chapter["chapterId"]
    class_id = chapter["classId"]
    chapter_name = chapter["englishName"]
    subject_id = chapter["subjectId"]
    total_bank_count = int(chapter.get("questionCount", 0))

    out_dir = os.path.join(OUTPUT_ROOT, sanitize_filename(batch_name), sanitize_filename(subject_name))
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{sanitize_filename(chapter_name)}.json")

    # Fast skip only if marked completed AND file actually exists with >0 questions
    if TRACKER.is_chapter_completed(batch_id, chapter_id, out_file=out_file):
        print(f"  [Skipping] '{chapter_name}' is already marked COMPLETED in state tracker.")
        return

    # Load existing questions for this chapter
    questions_dict = {}
    if os.path.exists(out_file):
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for q in existing:
                    qid = q.get("questionId")
                    if qid:
                        questions_dict[qid] = q
        except Exception:
            pass

    current_count = len(questions_dict)

    if current_count >= total_bank_count and total_bank_count > 0:
        print(f"  [Completed] '{chapter_name}' already has {current_count}/{total_bank_count} questions.")
        TRACKER.mark_chapter_completed(batch_id, chapter_id, batch_name, subject_name, chapter_name, current_count)
        return

    print(f"\n=======================================================")
    print(f"Target: [{batch_name}] > [{subject_name}] > [{chapter_name}]")
    print(f"Available Bank: {total_bank_count} | Currently Downloaded: {current_count}")
    print(f"Exhaustion Rule: Runs without batch limit until {CONSECUTIVE_EMPTY_LIMIT} consecutive batches yield 0 new questions")
    print(f"=======================================================")

    consecutive_empty_batches = 0
    batch_idx = 1
    aborted_on_error = False

    # No hard ceiling: runs purely until completion or 10 consecutive zero-new batches
    while len(questions_dict) < total_bank_count:
        print(f"  -> Batch {batch_idx}: Requesting 90 Qs...", end=" ", flush=True)
        test_id, fallback_qs = start_test(batch_id, exam_category, chapter_id, class_id, subject_id, count=90)

        if not test_id:
            print("Failed to start test (rate-limit/network). Leaving chapter incomplete for retry.")
            aborted_on_error = True
            time.sleep(5)
            break

        time.sleep(delay)

        # Submit & extract full solutions
        solutions_extracted = False
        if submit_test(test_id):
            time.sleep(1.5)
            solved_qs = get_solutions(test_id)
            if solved_qs:
                incoming_qs = solved_qs
                solutions_extracted = True
            else:
                incoming_qs = fallback_qs
        else:
            incoming_qs = fallback_qs

        new_added = 0
        for q in incoming_qs:
            qid = q.get("questionId")
            if qid and qid not in questions_dict:
                questions_dict[qid] = q
                new_added += 1

        status_tag = "[Solutions & Video]" if solutions_extracted else "[Questions Only]"
        print(f"{status_tag} Received: {len(incoming_qs)} | New: {new_added} | Total: {len(questions_dict)}/{total_bank_count}")

        # Atomic write to save progress continuously (prevents any data loss or corruption)
        temp_file = out_file + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(list(questions_dict.values()), f, ensure_ascii=False, indent=2)
        os.replace(temp_file, out_file)

        # Update in-progress tracker
        TRACKER.mark_chapter_in_progress(batch_id, chapter_id, batch_name, subject_name, chapter_name, len(questions_dict))

        # Check for 10 consecutive empty batches
        if new_added == 0:
            consecutive_empty_batches += 1
            print(f"     ↳ [Notice] 0 new questions in this batch ({consecutive_empty_batches}/{CONSECUTIVE_EMPTY_LIMIT} consecutive)")
            if consecutive_empty_batches >= CONSECUTIVE_EMPTY_LIMIT:
                print(f"  [Chapter Pool Exhausted] {CONSECUTIVE_EMPTY_LIMIT} consecutive batches had 0 new questions.")
                print(f"  All available questions in rotation for this chapter are captured! Moving to next chapter.")
                break
        else:
            consecutive_empty_batches = 0

        batch_idx += 1
        time.sleep(delay)

    final_count = len(questions_dict)
    if not aborted_on_error and final_count > 0:
        TRACKER.mark_chapter_completed(batch_id, chapter_id, batch_name, subject_name, chapter_name, final_count)
        print(f"  [DONE] Finished '{chapter_name}'! Total saved: {final_count} questions.\n")
    else:
        TRACKER.mark_chapter_in_progress(batch_id, chapter_id, batch_name, subject_name, chapter_name, final_count)
        print(f"  [INCOMPLETE] '{chapter_name}' stopped early ({final_count} saved) — will resume automatically next run.\n")

def parse_args():
    parser = argparse.ArgumentParser(description="Smart Resilient PW Infinite Practice Question Downloader")
    parser.add_argument(
        "--batch",
        type=str,
        default=None,
        help="Batch to download: '11th JEE', '12th JEE', '11th NEET', '12th NEET', or 'all'"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Delay in seconds between requests (default: 2.5)"
    )
    parser.add_argument(
        "--include-all-neet",
        action="store_true",
        default=False,
        help="Also download Physics & Chemistry for NEET (skipped by default since identical to JEE)"
    )
    parser.add_argument(
        "--download-releases",
        action="store_true",
        default=False,
        help="Download existing batch zips & state_tracker.json from GitHub Releases before running"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="GitHub repo 'owner/name' for --download-releases"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    if args.download_releases:
        token = os.environ.get("GITHUB_TOKEN", "")
        download_existing_releases(args.repo, token, OUTPUT_ROOT)

    batch_arg = args.batch
    if not batch_arg:
        if sys.stdin.isatty():
            print("==================================================")
            print("   PW INFINITE PRACTICE - SMART RESILIENT RUNNER  ")
            print("==================================================")
            print("Select target batch:")
            for idx, name in enumerate(BATCHES.keys(), 1):
                note = " (Bio Only: Botany & Zoology)" if "NEET" in name else " (All Subjects: PCM)"
                print(f"  {idx}. {name}{note}")
            print("  5. All Batches (Unique Bank: 11th/12th JEE PCM + 11th/12th NEET Bio)")
            
            user_input = input("\nEnter choice (1-5) [Default: 1]: ").strip() or "1"
            if user_input == "5":
                batch_arg = "all"
            else:
                try:
                    batch_arg = list(BATCHES.keys())[int(user_input) - 1]
                except Exception:
                    batch_arg = "11th JEE"
        else:
            batch_arg = "all"

    if batch_arg.lower() == "all":
        target_batches = list(BATCHES.items())
    else:
        matched = [(k, v) for k, v in BATCHES.items() if k.lower() == batch_arg.lower()]
        if matched:
            target_batches = matched
        else:
            print(f"Unknown batch '{batch_arg}'. Valid options: {list(BATCHES.keys())} or 'all'. Defaulting to 11th JEE.")
            target_batches = [("11th JEE", BATCHES["11th JEE"])]

    print(f"\nStarting Pipeline for: {[b[0] for b in target_batches]}")
    print(f"Exhaustion Rule: Stop chapter after {CONSECUTIVE_EMPTY_LIMIT} consecutive zero-new batches (No batch ceiling) | Delay: {args.delay}s")
    if not args.include_all_neet:
        print("Subject Filter: JEE = All Subjects | NEET = Biology Only (Botany & Zoology; skips duplicate Physics/Chemistry)\n")
    else:
        print("Subject Filter: Downloading ALL subjects for both JEE and NEET\n")

    for batch_name, batch_id in target_batches:
        print(f"\n#######################################################")
        print(f"  STARTING BATCH: {batch_name}")
        print(f"#######################################################")

        exam_category, subjects = get_subjects(batch_id)
        if not subjects:
            print(f"Could not load subjects for {batch_name}. Skipping.")
            continue

        time.sleep(2.0)

        for sub in subjects:
            sub_name = sub["englishName"]
            sub_id = sub["subjectId"]

            # Filter NEET to Biology only (Botany & Zoology) unless overridden
            if "neet" in batch_name.lower() and not args.include_all_neet:
                if sub_name.strip().lower() not in NEET_ALLOWED_SUBJECTS:
                    print(f"\n>>> [Skipped] '{sub_name}' in {batch_name} (100% duplicate of JEE {sub_name}).")
                    continue

            print(f"\n>>> Subject: {sub_name}")
            chapters = get_chapters(batch_id, sub_id)
            time.sleep(2.0)

            if not chapters:
                print(f"No chapters found for {sub_name}.")
                continue

            for chap in chapters:
                download_chapter(
                    batch_name=batch_name,
                    batch_id=batch_id,
                    exam_category=exam_category,
                    subject_name=sub_name,
                    chapter=chap,
                    delay=args.delay
                )
                time.sleep(1.5)

    print("\n=======================================================")
    print("All tasks completed! Check 'downloaded_questions/' folder.")
    print("=======================================================")

if __name__ == "__main__":
    main()