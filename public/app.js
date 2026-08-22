/*
  OPTION A (recommended):
  Set these two Vercel environment variables and replace the placeholders
  below with the values during deployment if you keep this as a static site.

  SUPABASE_URL and SUPABASE_ANON_KEY are safe for the browser when RLS is
  configured as in supabase/schema.sql. Never put the service-role key here.
*/

const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY";

const state = {
  jobs: [],
  filtered: []
};

const roleGroups = {
  "Software Engineer": [
    "software engineer", "software developer", "backend engineer",
    "frontend engineer", "full stack", "full-stack"
  ],
  "Software Test Engineer": [
    "software test engineer", "test engineer", "test automation",
    "automation engineer"
  ],
  "QA / SDET": [
    "qa engineer", "quality assurance", "sdet"
  ],
  "Network Engineer": [
    "network engineer", "network test engineer", "network automation"
  ]
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function relativeDate(value) {
  if (!value) return "Recently";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Recently";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

function locationMatch(job, wanted) {
  if (!wanted) return true;
  const x = `${job.location || ""} ${job.title || ""}`.toLowerCase();

  if (wanted === "Bangalore") return /bangalore|bengaluru/.test(x);
  if (wanted === "Hyderabad") return /hyderabad/.test(x);
  if (wanted === "India / Remote") return /india|remote/.test(x);
  return true;
}

function roleMatch(job, wanted) {
  if (!wanted) return true;
  const title = (job.title || "").toLowerCase();
  return (roleGroups[wanted] || []).some(k => title.includes(k));
}

function render() {
  const search = document.querySelector("#search").value.toLowerCase().trim();
  const role = document.querySelector("#role").value;
  const location = document.querySelector("#location").value;
  const company = document.querySelector("#company").value;
  const sort = document.querySelector("#sort").value;

  state.filtered = state.jobs.filter(job => {
    const hay = [
      job.title, job.company_name, job.location,
      job.department, job.description
    ].join(" ").toLowerCase();

    return (!search || hay.includes(search))
      && roleMatch(job, role)
      && locationMatch(job, location)
      && (!company || job.company_name === company);
  });

  state.filtered.sort((a, b) => {
    if (sort === "company") return a.company_name.localeCompare(b.company_name);
    if (sort === "title") return a.title.localeCompare(b.title);
    return new Date(b.last_seen_at || 0) - new Date(a.last_seen_at || 0);
  });

  document.querySelector("#resultCount").textContent =
    `${state.filtered.length} matching jobs`;

  const container = document.querySelector("#jobs");
  const empty = document.querySelector("#empty");

  if (!state.filtered.length) {
    container.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");

  container.innerHTML = state.filtered.map(job => `
    <article class="card">
      <div class="card-head">
        <div>
          <div class="company">${esc(job.company_name)}</div>
          <h3>${esc(job.title)}</h3>
        </div>
        <span class="badge">${esc(job.source_type)}</span>
      </div>

      <div class="meta">
        <span>📍 ${esc(job.location || "India / Remote")}</span>
        <span>🕒 ${esc(relativeDate(job.posted_at || job.last_seen_at))}</span>
        ${job.employment_type ? `<span>💼 ${esc(job.employment_type)}</span>` : ""}
      </div>

      ${job.department ? `<div class="department">${esc(job.department)}</div>` : ""}

      <p class="description">${esc((job.description || "").slice(0, 260))}</p>

      <div class="actions">
        <a class="apply" href="${esc(job.apply_url)}" target="_blank" rel="noopener noreferrer">
          Apply on company site →
        </a>
        ${job.career_url ? `<a class="career" href="${esc(job.career_url)}" target="_blank" rel="noopener noreferrer">Career page</a>` : ""}
      </div>
    </article>
  `).join("");
}

async function load() {
  const status = document.querySelector("#status");

  if (SUPABASE_URL.startsWith("YOUR_") || SUPABASE_ANON_KEY.startsWith("YOUR_")) {
    status.textContent = "Add Supabase config";
    document.querySelector("#jobs").innerHTML = `
      <div class="setup">
        <h3>Almost ready</h3>
        <p>Open <code>public/app.js</code> and set SUPABASE_URL and SUPABASE_ANON_KEY.</p>
        <p>Keep the service-role key out of this file.</p>
      </div>`;
    return;
  }

  const client = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  try {
    const { data, error } = await client
      .from("jobs")
      .select("*")
      .eq("is_active", true)
      .order("last_seen_at", { ascending: false })
      .limit(1000);

    if (error) throw error;

    state.jobs = data || [];
    status.textContent = "Live";
    document.querySelector("#jobCount").textContent = state.jobs.length;
    document.querySelector("#companyCount").textContent =
      new Set(state.jobs.map(x => x.company_name)).size;

    const companies = [...new Set(state.jobs.map(x => x.company_name))].sort();
    const companySelect = document.querySelector("#company");
    companySelect.innerHTML = `<option value="">All companies</option>` +
      companies.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");

    document.querySelector("#updated").textContent =
      `Loaded ${new Date().toLocaleString()}`;

    render();
  } catch (err) {
    console.error(err);
    status.textContent = "Database error";
    document.querySelector("#jobs").innerHTML = `
      <div class="setup">
        <h3>Could not load jobs</h3>
        <p>${esc(err.message || "Check Supabase URL, key and RLS policy.")}</p>
      </div>`;
  }
}

["search", "role", "location", "company", "sort"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("input", render);
  document.querySelector(`#${id}`).addEventListener("change", render);
});

load();
