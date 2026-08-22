import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from supabase import create_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "companies.json")

ROLE_PATTERNS = [
    r"\bsoftware engineer\b",
    r"\bsoftware developer\b",
    r"\bsoftware test engineer\b",
    r"\btest engineer\b",
    r"\bqa engineer\b",
    r"\bquality assurance\b",
    r"\bsdet\b",
    r"\btest automation\b",
    r"\bautomation engineer\b",
    r"\bnetwork engineer\b",
    r"\bnetwork test engineer\b",
    r"\bnetwork automation\b",
]

LOCATION_PATTERNS = [
    r"\bbangalore\b",
    r"\bbengaluru\b",
    r"\bhyderabad\b",
    r"\bindia\b",
    r"\bremote\b",
]

HEADERS = {
    "User-Agent": "JobReferralDashboard/1.0 (+personal job tracking)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def matches_role(title, description=""):
    hay = f"{title} {description}".lower()
    return any(re.search(p, hay, re.I) for p in ROLE_PATTERNS)


def matches_location(location, title="", description=""):
    hay = f"{location} {title} {description}".lower()
    return any(re.search(p, hay, re.I) for p in LOCATION_PATTERNS)


def parse_date(value):
    if not value:
        return None
    try:
        dt = date_parser.parse(str(value))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def normalize_job(company, external_id, title, location, employment_type,
                  department, description, apply_url, posted_at):
    return {
        "company_name": company["name"],
        "company_slug": company["slug"],
        "external_id": str(external_id),
        "title": text(title)[:500],
        "location": text(location)[:500],
        "employment_type": text(employment_type)[:100],
        "department": text(department)[:200],
        "description": text(description)[:10000],
        "apply_url": apply_url,
        "career_url": company.get("career_url"),
        "source_type": company["source_type"],
        "posted_at": parse_date(posted_at),
        "last_seen_at": now_iso(),
        "is_active": True,
        "updated_at": now_iso(),
    }


def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company['board']}?mode=json"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    jobs = []
    for item in r.json():
        cats = item.get("categories") or {}
        location = cats.get("location") or ""
        description = item.get("descriptionPlain") or item.get("description") or ""
        title = item.get("text") or ""
        if not matches_role(title, description):
            continue
        if not matches_location(location, title, description):
            continue

        jobs.append(normalize_job(
            company,
            item.get("id"),
            title,
            location,
            cats.get("commitment"),
            cats.get("team"),
            description,
            item.get("hostedUrl") or item.get("applyUrl"),
            item.get("createdAt"),
        ))
    return jobs


def fetch_greenhouse(company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['board']}/jobs?content=true"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    jobs = []
    for item in r.json().get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        title = item.get("title") or ""
        description = item.get("content") or ""
        if not matches_role(title, description):
            continue
        if not matches_location(location, title, description):
            continue

        jobs.append(normalize_job(
            company,
            item.get("id"),
            title,
            location,
            None,
            None,
            BeautifulSoup(description, "html.parser").get_text(" ", strip=True),
            item.get("absolute_url"),
            item.get("updated_at"),
        ))
    return jobs


def fetch_ashby(company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company['board']}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    jobs = []
    for item in r.json().get("jobs", []):
        location = item.get("location") or ""
        title = item.get("title") or ""
        description = item.get("descriptionPlain") or item.get("description") or ""
        if not matches_role(title, description):
            continue
        if not matches_location(location, title, description):
            continue

        jobs.append(normalize_job(
            company,
            item.get("jobUrl") or item.get("applyUrl") or item.get("id"),
            title,
            location,
            item.get("employmentType"),
            item.get("departmentName"),
            BeautifulSoup(description, "html.parser").get_text(" ", strip=True),
            item.get("jobUrl") or item.get("applyUrl"),
            item.get("publishedAt"),
        ))
    return jobs


def fetch_generic(company):
    url = company.get("search_url") or company.get("career_url")
    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    jobs = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(r.url, a["href"])
        title = text(a.get_text(" ", strip=True))
        href_lower = href.lower()

        looks_like_job = any(x in href_lower for x in [
            "/job/", "/jobs/", "/job-", "/position/", "/requisition/",
            "jobid", "jobid=", "myworkdayjobs", "greenhouse.io", "lever.co"
        ])

        if not looks_like_job or len(title) < 4:
            continue

        if href in seen:
            continue
        seen.add(href)

        if not matches_role(title, ""):
            continue
        if not matches_location("", title, ""):
            continue

        external_id = re.sub(r"[^a-zA-Z0-9]+", "-", href).strip("-")[-180:]

        jobs.append(normalize_job(
            company,
            external_id,
            title,
            "",
            "",
            "",
            "",
            href,
            None,
        ))

    return jobs


def fetch_company(company):
    source = company["source_type"].lower()
    if source == "lever":
        return fetch_lever(company)
    if source == "greenhouse":
        return fetch_greenhouse(company)
    if source == "ashby":
        return fetch_ashby(company)
    return fetch_generic(company)


def upsert_jobs(client, jobs):
    if not jobs:
        return 0
    for i in range(0, len(jobs), 100):
        batch = jobs[i:i+100]
        client.table("jobs").upsert(
            batch,
            on_conflict="company_slug,external_id"
        ).execute()
    return len(jobs)


def mark_stale(client):
    # Jobs not seen for 72 hours are hidden from the public dashboard.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    client.table("jobs").update(
        {"is_active": False, "updated_at": now_iso()}
    ).lt("last_seen_at", cutoff).eq("is_active", True).execute()


def upsert_company_status(client, company, error=None):
    payload = {
        "name": company["name"],
        "slug": company["slug"],
        "career_url": company.get("career_url"),
        "source_type": company["source_type"],
        "updated_at": now_iso(),
    }
    if error:
        payload["last_error"] = str(error)[:1000]
    else:
        payload["last_success_at"] = now_iso()
        payload["last_error"] = None

    client.table("companies").upsert(
        payload,
        on_conflict="slug"
    ).execute()


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)

    client = create_client(url, key)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        companies = json.load(f)

    total = 0
    failed = 0

    for company in companies:
        try:
            jobs = fetch_company(company)
            count = upsert_jobs(client, jobs)
            upsert_company_status(client, company)
            total += count
            print(f"[OK] {company['name']}: {count} matching jobs")
        except Exception as exc:
            failed += 1
            print(f"[ERROR] {company['name']}: {exc}", file=sys.stderr)
            try:
                upsert_company_status(client, company, exc)
            except Exception:
                pass

    mark_stale(client)

    print(f"Finished. Matching jobs: {total}; failed sources: {failed}")

    # Do not fail the entire daily run just because one career source is unavailable.
    if failed == len(companies):
        sys.exit(1)


if __name__ == "__main__":
    main()
