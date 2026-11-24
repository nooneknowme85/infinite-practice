# PW Infinite Practice - Smart Automated Downloader

Automated scraper and pipeline to harvest all questions with answers, explanations, and video solutions from Physics Wallah Infinite Practice across **11th JEE**, **12th JEE**, **11th NEET**, and **12th NEET**.

---

## Key Features

1. **Maximum Batch Size (90 Questions):**
   * Automatically bypasses the frontend 20-question limit and queries the backend limit of **90 questions per batch** across all difficulty levels `[1, 2, 3]`.

2. **Full Question Packages:**
   * Question HTML content with LaTeX/KaTeX formulas.
   * Options with `isCorrect: true/false`.
   * Step-by-step text solutions (HTML).
   * Video solutions (direct YouTube and Cloudfront links).

3. **Smart 10-Batch Exhaustion & No-Duplicate Filter:**
   * **JEE Batches (11th & 12th):** Extracts all subjects (`Maths`, `Chemistry`, `Physics`).
   * **NEET Batches (11th & 12th):** Automatically extracts **Biology only** (`Botany` and `Zoology`), skipping `Physics` and `Chemistry` because they are 100% identical to JEE (saving 107,000+ duplicate downloads). Use `--include-all-neet` locally if you ever want them too.
   * Keeps fetching tests for each chapter until **10 consecutive batches (900 requested questions) yield 0 new questions**, with no artificial batch cap.

4. **Smart State Tracking & Auto-Resume:**
   * Tracks progress in `downloaded_questions/state_tracker.json`.
   * If the script or connection stops at any point (even midway through a chapter), restarting it immediately reads existing question IDs and only fetches new ones.
   * Chapters that are already completed are automatically skipped.

5. **Resilience to Poor / Slow Networks:**
   * Configured with an `HTTPAdapter` session with automatic 3x retries.
   * Handles timeouts, connection drops, and DNS issues with exponential backoff.
   * Automatically cools down if the backend throws `#You've made too many requests#` (HTTP 403).

6. **GitHub Releases Publishing:**
   * Runs in the cloud for up to 6 hours on GitHub Actions.
   * Automatically packages the results into **4 separate `.zip` files** and publishes them directly to your repository's **Releases** page (permanent, direct download links that never expire).

---

## Option 1: Running Locally

### 1. Install Requirements
```bash
pip install -r requirements.txt
```

### 2. Run Interactively
```bash
python master_downloader.py
```
Select your desired batch from the menu:
* `1` $\rightarrow$ 11th JEE
* `2` $\rightarrow$ 12th JEE
* `3` $\rightarrow$ 11th NEET
* `4` $\rightarrow$ 12th NEET
* `5` $\rightarrow$ All Batches

### 3. Run with CLI Flags (Headless)
```bash
# Download 11th JEE only:
python master_downloader.py --batch "11th JEE"

# Download everything:
python master_downloader.py --batch all
```

---

## Option 2: Running via GitHub Actions & Auto-Publishing to Releases

1. In your GitHub repository:
   * Copy the updated `master_downloader.py` and `.github/workflows/download_questions.yml` files into your repo.
2. Go to the **Actions** tab on GitHub.
3. Select **"Download & Release PW Questions"** from the left sidebar.
4. Click **Run workflow**:
   * Select your batch (`all`, `11th JEE`, `12th JEE`, `11th NEET`, `12th NEET`).
   * Click **Run workflow**.
5. Once the workflow finishes:
   * Go to the **Releases** page of your repository.
   * Download the `.zip` files attached:
     * `11th_JEE.zip`
     * `12th_JEE.zip`
     * `11th_NEET.zip`
     * `12th_NEET.zip`
     * `state_tracker.json`

---

## Folder Structure

```
downloaded_questions/
├── state_tracker.json
├── 11th JEE/
│   ├── Physics/
│   │   ├── Work, Energy and Power.json
│   │   └── Laws of Motion.json
│   ├── Chemistry/
│   └── Maths/
├── 12th JEE/
├── 11th NEET/
└── 12th NEET/
```
