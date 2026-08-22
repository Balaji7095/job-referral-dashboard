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

# ============================================================
# TARGET PROFILE
# ============================================================

ROLE_PATTERNS = [
    r"\bsoftware engineer\b",
    r"\bsoftware engineer i\b",
    r"\bsoftware developer\b",
    r"\bsoftware development engineer\b",
    r"\bassociate software engineer\b",
    r"\bjunior software engineer\b",
    r"\bgraduate software engineer\b",
    r"\bbackend engineer\b",
    r"\bfull stack engineer\b",
    r"\bpython developer\b",
    r"\bjava developer\b",

    r"\bsoftware test engineer\b",
    r"\btest engineer\b",
    r"\bqa engineer\b",
    r"\bquality assurance\b",
    r"\bsdet\b",
    r"\btest automation\b",
    r"\bautomation engineer\b",
    r"\bsoftware engineer in test\b",

    r"\bnetwork engineer\b",
    r"\bnetwork test engineer\b",
    r"\bnetwork automation\b",
    r"\bnetwork software engineer\b",
]

LOCATION_PATTERNS = [
    r"\bbangalore\b",
    r"\bbengaluru\b",
    r"\bhyderabad\b",
    r"\bindia\b",
    r"\bremote\b",
]

# Skills relevant to your profile
TARGET_SKILLS = {
    "python": r"\bpython\b",
    "java": r"\bjava\b",
    "pyats": r"\bpyats\b",
    "networking": r"\bnetwork(?:ing)?\b",
    "linux": r"\blinux\b",
    "git": r"\bgit\b",
    "ci/cd": r"\bci\s*/\s*cd\b|\bcontinuous integration\b|\bcontinuous delivery\b",
    "automation": r"\bautomation\b",
    "testing": r"\btesting\b|\btest automation\b|\bsoftware testing\b",
    "api": r"\bapi\b|\brest api\b",
    "javascript": r"\bjavascript\b|\breact\b|\bnode\.?js\b",
}

# Companies known/treated as product/technology companies.
# This is used only for ranking, not for filtering.
PRODUCT_COMPANIES = {
    "cisco",
    "micron",
    "hpe",
    "hewlett packard enterprise",
    "akamai",
    "qualcomm",
    "amd",
    "nvidia",
    "adobe",
    "salesforce",
    "servicenow",
    "oracle",
    "dell technologies",
    "atlassian",
    "palo alto networks",
    "browserstack",
    "postman",
    "razorpay",
    "freshworks",
    "chargebee",
    "phonepe",
    "flipkart",
    "myntra",
    "meesho",
    "swiggy",
    "groww",
    "cred",
    "zoho",
    "makemytrip",
}

HEADERS = {
    "User-Agent": "JobReferralDashboard/1.0 (+personal job tracking)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HELPERS
# ============================================================

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


# ============================================================
# EXPERIENCE MATCHING
# ============================================================

def extract_experience(text_value):
    """
    Returns:
        minimum years
        maximum years
        experience category
    """

    hay = text_value.lower()

    # Fresh graduate / entry level
    fresh_patterns = [
        r"\bfreshers?\b",
        r"\bentry[\s-]?level\b",
        r"\bgraduate\b",
        r"\bnew grad\b",
        r"\bnew graduate\b",
        r"\b0\s*(?:to|-)\s*1\s*years?\b",
        r"\b0\s*(?:to|-)\s*2\s*years?\b",
    ]

    if any(re.search(p, hay) for p in fresh_patterns):
        return 0, 2, "Entry Level"

    # Range: 1-3 years / 1 to 3 years
    range_patterns = [
        r"(\d+)\s*(?:to|-)\s*(\d+)\s*(?:years?|yrs?)",
        r"(\d+)\s*\+\s*(?:years?|yrs?)",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, hay)

        if not match:
            continue

        if len(match.groups()) == 2:
            minimum = int(match.group(1))
            maximum = int(match.group(2))
            return minimum, maximum, "Experience Range"

        minimum = int(match.group(1))
        return minimum, 10, "Experience Required"

    # Single explicit number such as "2 years experience"
    single = re.search(
        r"(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)",
        hay,
    )

    if single:
        minimum = int(single.group(1))
        return minimum, minimum + 2, "Experience Required"

    return None, None, "Not Specified"


def experience_score(minimum, maximum):
    """
    Target user profile:
    approximately 1 year experience.
    """

    if minimum is None:
        return 10

    # Perfect range for the user
    if minimum <= 1 and maximum >= 1:
        return 30

    # 0-2 / 0-3 etc.
    if minimum == 0 and maximum >= 2:
        return 30

    # 1-2 / 1-3
    if minimum == 1 and maximum >= 2:
        return 30

    # 2 years can still be worth applying to
    if minimum == 2:
        return 15

    # 3+ is lower priority
    if minimum == 3:
        return 5

    # 4+ etc.
    return 0


# ============================================================
# ROLE CATEGORY
# ============================================================

def get_role_category(title, description=""):
    hay = f"{title} {description}".lower()

    if any(re.search(p, hay, re.I) for p in [
        r"\bsdet\b",
        r"\bsoftware test\b",
        r"\btest engineer\b",
        r"\bqa\b",
        r"\bquality assurance\b",
        r"\btest automation\b",
        r"\bautomation test\b",
    ]):
        return "Testing / SDET"

    if any(re.search(p, hay, re.I) for p in [
        r"\bnetwork\b",
        r"\bnetworking\b",
        r"\bnetwork automation\b",
    ]):
        return "Networking"

    if any(re.search(p, hay, re.I) for p in [
        r"\bsoftware engineer\b",
        r"\bsoftware developer\b",
        r"\bsoftware development engineer\b",
        r"\bbackend engineer\b",
        r"\bfull stack engineer\b",
        r"\bpython developer\b",
        r"\bjava developer\b",
    ]):
        return "Software Engineering"

    return "Other"


# ============================================================
# SKILL MATCHING
# ============================================================

def find_matching_skills(title, description):
    hay = f"{title} {description}".lower()

    matched = []

    for skill, pattern in TARGET_SKILLS.items():
        if re.search(pattern, hay, re.I):
            matched.append(skill)

    return matched


def skill_score(skills):
    # Maximum 25 points
    return min(len(skills) * 3, 25)


# ============================================================
# COMPANY TYPE
# ============================================================

def get_company_type(company_name):
    name = company_name.lower().strip()

    if name in PRODUCT_COMPANIES:
        return "Product"

    # Default to Technology / Other rather than falsely claiming product.
    return "Technology / Other"


def company_score(company_name):
    return 15 if get_company_type(company_name) == "Product" else 5


# ============================================================
# INTERVIEW MODE
# ============================================================

def detect_interview_mode(description):
    hay = description.lower()

    virtual_patterns = [
        r"\bvirtual interview\b",
        r"\bonline interview\b",
        r"\bremote interview\b",
        r"\bvideo interview\b",
        r"\bvideo call\b",
        r"\bvirtual hiring\b",
    ]

    onsite_patterns = [
        r"\bon[- ]site interview\b",
        r"\bin[- ]person interview\b",
        r"\bin person interview\b",
        r"\bon[- ]site hiring\b",
    ]

    if any(re.search(p, hay, re.I) for p in virtual_patterns):
        return "Virtual"

    if any(re.search(p, hay, re.I) for p in onsite_patterns):
        return "Onsite"

    return "Unknown"


# ============================================================
# MATCH SCORE
# ============================================================

def calculate_match(company_name, title, description):
    minimum, maximum, experience_type = extract_experience(
        f"{title} {description}"
    )

    role_category = get_role_category(title, description)

    skills = find_matching_skills(title, description)

    exp_points = experience_score(minimum, maximum)
    skill_points = skill_score(skills)
    company_points = company_score(company_name)

    # Role relevance
    role_points = 20 if role_category != "Other" else 0

    # Location relevance
    location_points = 10

    total = (
        exp_points
        + skill_points
        + company_points
        + role_points
        + location_points
    )

    return {
        "experience_min": minimum,
        "experience_max": maximum,
        "role_category": role_category,
        "match_score": min(total, 100),
        "company_type": get_company_type(company_name),
        "interview_mode": detect_interview_mode(description),
        "skills_matched": skills,
        "experience_type": experience_type,
    }


# ============================================================
# NORMALIZE JOB
# ============================================================

def normalize_job(
    company,
    external_id,
    title,
    location,
    employment_type,
    department,
    description,
    apply_url,
    posted_at,
):
    title = text(title)[:500]
    location = text(location)[:500]
    description = text(description)[:10000]

    match = calculate_match(
        company["name"],
        title,
        description,
    )

    return {
        "company_name": company["name"],
        "company_slug": company["slug"],
        "external_id": str(external_id),
        "title": title,
        "location": location,
        "employment_type": text(employment_type)[:100],
        "department": text(department)[:200],
        "description": description,
        "apply_url": apply_url,
        "career_url": company.get("career_url"),
        "source_type": company["source_type"],
        "posted_at": parse_date(posted_at),
        "last_seen_at": now_iso(),
        "is_active": True,
        "updated_at": now_iso(),

        # Personal profile matching
        "experience_min": match["experience_min"],
        "experience_max": match["experience_max"],
        "role_category": match["role_category"],
        "match_score": match["match_score"],
        "company_type": match["company_type"],
        "interview_mode": match["interview_mode"],
        "skills_matched": match["skills_matched"],
    }


# ============================================================
# SOURCE FETCHERS
# ============================================================

def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company['board']}?mode=json"

    r = session.get(url, timeout=30)
    r.raise_for_status()

    jobs = []

    for item in r.json():
        cats = item.get("categories") or {}

        location = cats.get("location") or ""
        description = (
            item.get("descriptionPlain")
            or item.get("description")
            or ""
        )
        title = item.get("text") or ""

        if not matches_role(title, description):
            continue

        if not matches_location(location, title, description):
            continue

        jobs.append(
            normalize_job(
                company,
                item.get("id"),
                title,
                location,
                cats.get("commitment"),
                cats.get("team"),
                description,
                item.get("hostedUrl") or item.get("applyUrl"),
                item.get("createdAt"),
            )
        )

    return jobs


def fetch_greenhouse(company):
    url = (
        f"https://boards-api.greenhouse.io/v1/boards/"
        f"{company['board']}/jobs?content=true"
    )

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

        clean_description = BeautifulSoup(
            description,
            "html.parser",
        ).get_text(" ", strip=True)

        jobs.append(
            normalize_job(
                company,
                item.get("id"),
                title,
                location,
                None,
                None,
                clean_description,
                item.get("absolute_url"),
                item.get("updated_at"),
            )
        )

    return jobs


def fetch_ashby(company):
    url = (
        f"https://api.ashbyhq.com/posting-api/job-board/"
        f"{company['board']}"
    )

    r = session.get(url, timeout=30)
    r.raise_for_status()

    jobs = []

    for item in r.json().get("jobs", []):
        location = item.get("location") or ""
        title = item.get("title") or ""

        description = (
            item.get("descriptionPlain")
            or item.get("description")
            or ""
        )

        if not matches_role(title, description):
            continue

        if not matches_location(location, title, description):
            continue

        clean_description = BeautifulSoup(
            description,
            "html.parser",
        ).get_text(" ", strip=True)

        jobs.append(
            normalize_job(
                company,
                item.get("jobUrl")
                or item.get("applyUrl")
                or item.get("id"),
                title,
                location,
                item.get("employmentType"),
                item.get("departmentName"),
                clean_description,
                item.get("jobUrl")
                or item.get("applyUrl"),
                item.get("publishedAt"),
            )
        )

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

        looks_like_job = any(
            x in href_lower
            for x in [
                "/job/",
                "/jobs/",
                "/job-",
                "/position/",
                "/requisition/",
                "jobid",
                "jobid=",
                "myworkdayjobs",
                "greenhouse.io",
                "lever.co",
            ]
        )

        if not looks_like_job or len(title) < 4:
            continue

        if href in seen:
            continue

        seen.add(href)

        if not matches_role(title, ""):
            continue

        if not matches_location("", title, ""):
            continue

        external_id = re.sub(
            r"[^a-zA-Z0-9]+",
            "-",
            href,
        ).strip("-")[-180:]

        jobs.append(
            normalize_job(
                company,
                external_id,
                title,
                "",
                "",
                "",
                "",
                href,
                None,
            )
        )

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


# ============================================================
# SUPABASE
# ============================================================

def upsert_jobs(client, jobs):
    if not jobs:
        return 0

    for i in range(0, len(jobs), 100):
        batch = jobs[i:i + 100]

        client.table("jobs").upsert(
            batch,
            on_conflict="company_slug,external_id",
        ).execute()

    return len(jobs)


def mark_stale(client):
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=72)
    ).isoformat()

    client.table("jobs").update(
        {
            "is_active": False,
            "updated_at": now_iso(),
        }
    ).lt(
        "last_seen_at",
        cutoff,
    ).eq(
        "is_active",
        True,
    ).execute()


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
        on_conflict="slug",
    ).execute()


# ============================================================
# MAIN
# ============================================================

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY",
            file=sys.stderr,
        )
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

            upsert_company_status(
                client,
                company,
            )

            total += count

            print(
                f"[OK] {company['name']}: "
                f"{count} matching jobs"
            )

        except Exception as exc:
            failed += 1

            print(
                f"[ERROR] {company['name']}: {exc}",
                file=sys.stderr,
            )

            try:
                upsert_company_status(
                    client,
                    company,
                    exc,
                )
            except Exception:
                pass

    mark_stale(client)

    print(
        f"Finished. Matching jobs: {total}; "
        f"failed sources: {failed}"
    )

    # Do not fail the whole workflow because one source is unavailable.
    if failed == len(companies):
        sys.exit(1)


if __name__ == "__main__":
    main()
