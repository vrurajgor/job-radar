# Job Radar

A dashboard of **Project Manager, Associate Project Manager, Consultant, and Business Analyst** roles posted in the **last 7 days** at the 1,932 H-1B sponsoring employers in `H1B_Database_2026.pdf`. Healthcare and healthcare-adjacent companies (245 of them) are Tier 1 and float to the top. Everyone else is Tier 2.

It runs on GitHub for free: every morning at **7 AM New York time** a GitHub Action pulls postings straight from each company's own job board and republishes the dashboard as a web page you can bookmark.

---

## One-time setup (about 30 minutes)

You need a free GitHub account. You won't need a terminal; everything below happens in the browser.

### 1. Create the repository
1. Go to <https://github.com/new>.
2. Name it `job-radar`. Choose **Public**. Free GitHub Pages only works on public repos. Only the job listings become public; your Save/Applied marks stay in your browser.
3. Click **Create repository**.

### 2. Upload the files
1. On the new repo page, click **uploading an existing file**.
2. Unzip `job-radar.zip` on your computer and drag **the contents of the folder** (not the folder itself) into the upload box. Include the hidden `.github` folder:
   - **Mac:** press `Cmd + Shift + .` in Finder to show hidden files.
   - **Windows:** in File Explorer, go to View → Show → Hidden items.
3. Click **Commit changes**.
4. Check that you can see a `.github/workflows` folder in the repo. If it's missing, click **Add file → Create new file**, type `.github/workflows/daily.yml` as the name, paste in that file's contents, and commit. Do the same for `discover.yml`.

### 3. Let the workflows save their results
**Settings → Actions → General → Workflow permissions →** select **Read and write permissions** → **Save**.

### 4. Find each company's job feed (first scan)
**Actions** tab → if prompted, click **I understand my workflows, go ahead and enable them** → choose **Discover job feeds** → **Run workflow** → keep "all" → **Run workflow**.

This checks every company and takes roughly 20 to 60 minutes. The log's last line reports how many feeds it found (for example, `Feeds found for 410/1932 companies (140/245 in Tier 1)`).

> In a hurry? Run it with **tier = 1** first (about 10 minutes, healthcare only), then run "all" later.

### 5. Run the radar once
**Actions → Daily job radar → Run workflow.** This takes about 5 to 15 minutes.

### 6. Turn on the web page
**Settings → Pages →** under *Build and deployment*, set Source to **Deploy from a branch**, Branch to **main**, and folder to **/docs** → **Save**.

After a minute, the page shows your address, which looks like `https://<your-username>.github.io/job-radar/`. Bookmark it; that's your dashboard.

From now on, it updates itself every morning.

---

## Using the dashboard

- **The seven bars at the top** show one column per day. Each stripe is a posting: teal for healthcare, grey for other companies, and outlined in yellow if it's new since the previous morning. Click a day to show only that day's postings.
- **Filters:** Healthcare / Other, sector, role, US locations only, and hide "no sponsorship" postings.
- **Save / Applied / Not for me** removes a job from the default view so you only see what you haven't acted on. These marks are stored in your browser. They don't sync between your laptop and your phone.
- **"Says no sponsorship"** means the job description contains wording like *unable to sponsor* or *without the need for sponsorship*. It's a text match, not a verdict. Some postings use boilerplate that HR will waive, so the filter is off by default.
- **Not covered** lists the healthcare companies whose careers sites the radar can't read. Each one has a ready-made LinkedIn search for the past week.
- **Feed health** shows which company feeds failed on the last run. Failures are usually temporary and get retried the next day.

---

## What it can and can't see (please read)

The radar reads the public job feeds of five systems that power most corporate career sites: **Workday, Greenhouse, Lever, Ashby, and SmartRecruiters**. It hits those feeds directly, so the links go to the real posting on the company's site.

It **can't** read careers sites built on iCIMS, Oracle Taleo, SAP SuccessFactors, Eightfold, Phenom, or custom in-house sites. Many large hospitals, Mayo Clinic, J&J, and the big consulting firms (Deloitte, EY, Accenture, PwC) fall in this group. I couldn't test live coverage while building this, so treat the first discovery log as the real number; partial coverage of the healthcare list is expected. Everything else shows up under **Not covered** with a search link, so nothing silently disappears.

A few more things to know:
- **Guessing feeds isn't perfect.** Discovery guesses each company's job-board ID from its name. It checks Greenhouse guesses against the board's company name, but Lever, Ashby, and Workday don't expose one, so an occasional wrong match is possible. If a company shows odd jobs, set it to `skip` (see below).
- **Workday feeds need three details** (tenant, data center, site name) that often can't be guessed. `sources_manual.csv` comes pre-filled with starter URLs for about 30 large healthcare employers. **These are my best guesses and haven't been tested.** Discovery confirms each one, and any that fail show up as "your URL didn't respond" on the Not covered tab.
- **Posting dates:** Workday dates are confirmed from the job's detail page. When a Greenhouse board doesn't publish its original post date, the radar uses the "last updated" date and marks the job *Date approximate*.
- **Timing:** GitHub sometimes starts scheduled jobs 5 to 30 minutes late at busy times, so "7 AM" really means "shortly after 7".
- **H-1B numbers** on each card come from your PDF (FY2025 filings). They show a company's sponsorship history, not whether this particular role is eligible.

---

## Making changes

Every file can be edited on github.com: open the file, click the pencil icon, edit, and **Commit changes**.

| I want to… | Edit |
|---|---|
| Add a company's careers site, or fix a wrong one | `sources_manual.csv`: add a row `COMPANY NAME,https://…careers url…,use`. The company name must match `companies.csv` exactly. Saving the file triggers a re-scan automatically. |
| Stop tracking a company | `sources_manual.csv`: add a row with `skip` as the action |
| Move a company into or out of healthcare | `companies.csv`: change `tier` to 1 or 2 and set `sector` |
| Change role titles, excluded titles (e.g. drop "Senior"), or the 7-day window | `config.yaml` |
| Only scan healthcare companies each day | `config.yaml`: `tiers: [1]` |
| Refresh right now | **Actions → Daily job radar → Run workflow** |
| Change the time | `config.yaml` → `run_hour`, and shift the two UTC cron lines in `.github/workflows/daily.yml` by the same amount |

**Finding a careers URL to paste:** open the company's careers page, click into any job, and copy the address bar. Addresses containing `myworkdayjobs.com`, `greenhouse.io`, `lever.co`, `ashbyhq.com`, or `smartrecruiters.com` work. Anything else, such as `icims.com` or `taleo.net`, can't be read, and pasting it only records the link for the Not covered tab.

**Getting a new year's H-1B list:** export the h1bdata.info top-companies page to PDF again, then run `python scripts/build_companies.py path/to/file.pdf` on a computer with Python and poppler installed. This rebuilds `companies.csv`.

---

## Keeping it running

- GitHub disables scheduled workflows after 60 days with no repository activity. The daily commits count as activity, so this normally never triggers. If the dashboard stops updating, check the **Actions** tab for a banner and re-enable the workflow.
- Discovery re-runs every Sunday to pick up companies that switch job systems.

## Files

```
companies.csv            1,932 employers from your PDF, with tier + sector
sources_manual.csv       careers URLs you add or override (starter guesses included)
config.yaml              roles, exclusions, lookback window, sponsorship phrases
radar/                   the Python code (discover.py, run.py, ats.py …)
dashboard/template.html  the dashboard page design
data/                    discovered feeds + "seen before" history (written by the workflows)
docs/                    the published dashboard (written by the workflows)
.github/workflows/       the 7 AM schedule and the weekly discovery
tests/test_offline.py    offline self-check with sample feed responses
```

To run it on your own computer instead: `pip install -r requirements.txt`, then `python -m radar.discover --tier 1`, then `python -m radar.run`, and open `docs/index.html`.
