# Job Referral Dashboard

A low-code personal job dashboard for tracking **active Software Engineer, Software Test Engineer / QA / SDET, and Network Engineer roles** from company career sources.

## Architecture

```text
Official career source
        ↓
GitHub Actions (daily)
        ↓
Python collector
        ↓
Supabase Postgres
        ↓
Vercel static dashboard
        ↓
Direct company Apply link
```

GitHub Actions supports scheduled workflows, including timezone-aware schedules. This project runs the collector once every 24 hours. citeturn0search3

Supabase's Python client supports `select`, `insert`, `upsert`, and filtered updates, which is what the collector uses. citeturn0search0turn0search1turn0search2

Vercel supports static frontends and Python serverless functions; this version deliberately keeps the frontend static because the scheduled collector already runs in GitHub Actions. citeturn0search10turn0search18

---

## 1. Create the Supabase database

Create a free Supabase project.

Open **SQL Editor** and run:

```sql
-- Copy everything from supabase/schema.sql into the Supabase SQL Editor.
```

The schema creates:
- `jobs` table
- `companies` table
- public read-only access for the dashboard
- indexes for company, location, role and active status

### Get these two values

From Supabase project settings:

- Project URL
- Anon/public key

For the GitHub Action you will also need the **service-role key**.

**Never put the service-role key in `public/app.js`.**
Only store it as a GitHub Actions secret.

---

## 2. Upload the project to GitHub

Create a new GitHub repository, for example:

`job-referral-dashboard`

Upload this entire project.

Important files:

```text
.github/workflows/update-jobs.yml
config/companies.json
scraper/scrape.py
supabase/schema.sql
public/index.html
public/app.js
public/styles.css
requirements.txt
```

---

## 3. Add GitHub Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret

Add:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Values:

```text
SUPABASE_URL = your Supabase project URL
SUPABASE_SERVICE_ROLE_KEY = your Supabase service-role key
```

Do NOT commit these values to GitHub.

---

## 4. Configure companies

Edit:

```text
config/companies.json
```

The project supports:

- `lever`
- `greenhouse`
- `ashby`
- `generic`

For the first run, the config contains several India-focused product companies using public Lever boards plus career-page entries for larger companies.

### Lever example

```json
{
  "name": "Example Company",
  "slug": "example-company",
  "source_type": "lever",
  "board": "example-company",
  "career_url": "https://jobs.lever.co/example-company"
}
```

### Greenhouse example

```json
{
  "name": "Example Company",
  "slug": "example-company",
  "source_type": "greenhouse",
  "board": "examplecompany",
  "career_url": "https://boards.greenhouse.io/examplecompany"
}
```

### Ashby example

```json
{
  "name": "Example Company",
  "slug": "example-company",
  "source_type": "ashby",
  "board": "examplecompany",
  "career_url": "https://jobs.ashbyhq.com/examplecompany"
}
```

### Generic career page

Use this when the company does not expose a supported public jobs API:

```json
{
  "name": "Example Company",
  "slug": "example-company",
  "source_type": "generic",
  "career_url": "https://company.com/careers",
  "search_url": "https://company.com/careers/jobs"
}
```

Generic scraping is intentionally conservative: it only keeps links that look like job/application links. Some Workday/SPA sites may require a dedicated adapter later.

---

## 5. Run the collector manually

Go to:

**GitHub → Actions → Daily Job Collector → Run workflow**

The workflow also runs automatically once every 24 hours.

The collector:
1. Fetches jobs
2. Filters for your target role keywords
3. Filters for India/Bangalore/Hyderabad/remote India
4. Deduplicates by company + external job ID
5. Upserts jobs into Supabase
6. Marks jobs not seen recently as inactive
7. Stores the direct company application URL

---

## 6. Deploy the dashboard to Vercel

Import the GitHub repository into Vercel.

Set these Vercel environment variables:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
```

For this static dashboard, the values are also supported through the small config section at the top of `public/app.js`.

After deployment, open the Vercel URL.

---

## 7. Dashboard features

The dashboard includes:

- Software Engineer
- Software Test Engineer
- QA Engineer
- SDET
- Network Engineer
- Network Test Engineer
- Bangalore
- Hyderabad
- India remote
- Company filter
- Search
- Active-only filter
- Newest-first sorting
- Direct **Apply** button
- Last updated timestamp
- Source/career page link

The Apply button goes to the job URL stored from the company source, so you can send that link to an employee for referral.

---

## 8. Important limitation

No scraper can reliably extract every company's jobs from a single generic HTML method.

Large companies often use Workday, custom career portals, anti-bot protection, or JavaScript-rendered search pages. For those companies, use a dedicated adapter when necessary.

This project is therefore designed with a **source adapter architecture**. Adding a new company does not require rewriting the dashboard.

---

## 9. Recommended next upgrades

After the basic dashboard works, add:

1. Resume/JD match score
2. "Applied" status
3. Referral contact field
4. Email/Telegram alerts
5. New-job-only notifications
6. Company priority
7. Experience-year filter
8. Salary filter when published
9. Dedicated Workday adapter
10. Daily email digest

