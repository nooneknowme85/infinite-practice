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

3. **Smart State Tracking & Auto-Resume:**
   * Tracks progress in `downloaded_questions/state_tracker.json`.
   * If the script or connection stops at any point (even midway through a chapter), restarting it immediately reads existing question IDs and only fetches new ones.
   * Chapters that are already completed are automatically skipped.

4. **Resilience to Poor / Slow Networks:**
   * Configured with an `HTTPAdapter` session with automatic 3x retries.
   * Handles timeouts, connection drops, and DNS issues with exponential backoff.
   * Automatically cools down if the backend throws `#You've made too many requests#` (HTTP 403).

5. **GitHub Releases Publishing:**
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
python master_downloader.py --batch "11th JEE" --max-batches 25

# Download everything:
python master_downloader.py --batch all --max-batches 30
```

---

## Option 2: Running via GitHub Actions & Auto-Publishing to Releases

1. Push this folder to your GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "Add smart PW downloader with GitHub Release publishing"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
2. On GitHub, go to your repository and click the **Actions** tab.
3. Select **"Download & Release PW Questions"** from the left sidebar.
4. Click **Run workflow**:
   * Select your batch (`all`, `11th JEE`, `12th JEE`, `11th NEET`, `12th NEET`).
   * Set `max_batches` (default: 25).
   * Click **Run workflow**.
5. Once the workflow finishes:
   * Go to the **Releases** page of your repository (`https://github.com/<user>/<repo>/releases`).
   * You will see the new release with all **4 `.zip` files attached** ready for one-click download!
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
