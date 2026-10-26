/* Isha's Curl Lab: a small single-page app. All model text is inserted as text (never as HTML). */
"use strict";

const SAVE_KEY = "curllab.v1";
const OLD_SAVE_KEY = "coilcurl.v1";  // earlier name of the app: saved routines are moved over once
const AGENT_LABELS = {
  photo_analyst: ["Photo reader", "Looks at your wash-day photo"],
  hair_science: ["Hair scientist", "Protein and moisture balance, porosity needs"],
  weather: ["Weather watcher", "Reads your 7-day forecast for frizz and dryness"],
  schedule: ["Schedule planner", "Fits wash days to your week and your time"],
  products: ["Product finder", "Searches the verified US product catalog"],
  budget: ["Budget keeper", "Fits the routine to your monthly budget"],
  planner: ["Routine planner", "Writes your step-by-step routine"],
  daily_coach: ["Daily coach", "Decides what to do today"],
};
const BUILD_AGENTS = ["hair_science", "weather", "schedule", "products", "budget", "planner"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_NAMES = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };
const KIND_LABEL = { wash_day: "Wash day", deep_condition_day: "Deep condition", protein_day: "Protein", refresh_day: "Refresh", rest_day: "Rest" };
const CATEGORY_LABEL = {
  cleanser: "Cleanser", clarifier: "Clarifier", cowash: "Co-wash", conditioner: "Conditioner", deep_conditioner: "Deep conditioner",
  protein_treatment: "Protein treatment", leave_in: "Leave-in", curl_cream: "Curl cream", gel: "Gel", mousse: "Mousse", oil: "Oil / sealant", scalp_care: "Scalp care",
};
const CONCERNS = [
  ["dryness", "Dryness"], ["frizz", "Frizz"], ["breakage", "Breakage"], ["shrinkage", "Shrinkage"], ["tangles", "Tangles"],
  ["buildup", "Product buildup"], ["flaky_scalp", "Flaky or itchy scalp"], ["thinning", "Thinning or bald patches"], ["definition", "Wanting more definition"],
];
const STYLE_GOALS = [
  ["wash_and_go", "Wash-and-go", "Defined curls, air-dried or diffused"],
  ["twist_or_braid_out", "Twist-out or braid-out", "Stretched, defined curls from a set style"],
  ["protective_style", "Protective styles", "Braids, twists or wigs that stay in for weeks"],
  ["locs", "Locs", "Maintaining starter or mature locs"],
  ["short_and_simple", "Short and simple", "Short cuts, waves, fades, quick routines"],
  ["low_manipulation", "Low manipulation", "As little daily work as possible"],
];

const defaultProfile = () => ({
  zip_code: "", curl_pattern: null, porosity: null, strand_width: null, density: null, hair_length: "medium",
  elasticity: "not_sure", concerns: [], color_treated: false, heat_styled: false, chemically_relaxed_or_bleached: false,
  style_goal: "wash_and_go", wash_every_days: 7, minutes_per_day: 15, wash_day_minutes: 90, monthly_budget_usd: 40,
  fragrance_free: false, sulfate_free: false, silicone_free: false, notes: "", photo_analysis: null,
});

const state = { user: null, authTab: "login", authMsg: "", step: "welcome", profile: defaultProfile(), photo: null, result: null, tab: "overview", error: "", saved: loadSaved(), today: null, lastWash: null };
if (state.saved) { state.profile = { ...defaultProfile(), ...state.saved.profile }; state.result = state.saved.result; state.lastWash = state.saved.lastWash || state.saved.result?.last_wash || null; }

function loadSaved() {
  try {
    const old = localStorage.getItem(OLD_SAVE_KEY);
    if (old && !localStorage.getItem(SAVE_KEY)) localStorage.setItem(SAVE_KEY, old);
    localStorage.removeItem(OLD_SAVE_KEY);
    return JSON.parse(localStorage.getItem(SAVE_KEY));
  } catch { return null; }
}
function save() { if (state.result) state.result.last_wash = state.lastWash; try { localStorage.setItem(SAVE_KEY, JSON.stringify({ profile: state.profile, result: state.result, lastWash: state.lastWash })); } catch {} }

/* ---------- tiny DOM helper ---------- */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") throw new Error("html attr not allowed");
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const money = (n) => "$" + Number(n).toFixed(2);
const cap = (s) => s ? s[0].toUpperCase() + s.slice(1) : s;
function svg(markup) { const t = document.createElement("template"); t.innerHTML = markup.trim(); return t.content.firstChild; }

/* ---------- curl pattern drawings ---------- */
function patternSVG(p) {
  const type = p[0], t = { A: 0, B: 1, C: 2 }[p[1]];
  const pts = [];
  if (type === "2") {
    const amp = [5, 8, 11][t], cycles = [2.2, 2.8, 3.4][t];
    for (let i = 0; i <= 80; i++) { const u = i / 80; pts.push([4 + u * 72, 23 + amp * Math.sin(u * cycles * 2 * Math.PI)]); }
  } else if (type === "3") {
    const r = [10, 8, 6.5][t], cycles = [2.6, 3.4, 4.4][t];
    for (let i = 0; i <= 160; i++) { const th = (i / 160) * cycles * 2 * Math.PI; pts.push([th * r * 0.55 - r * Math.sin(th), 23 - r * Math.cos(th) * 1.05]); }
  } else {
    const amp = [12, 10, 8][t], n = [6, 9, 13][t];
    for (let i = 0; i <= n * 2; i++) pts.push([i, 23 + (i % 2 ? amp : -amp)]);
  }
  const xs = pts.map((q) => q[0]), min = Math.min(...xs), span = Math.max(...xs) - min || 1;
  const d = pts.map((q, i) => (i ? "L" : "M") + (4 + ((q[0] - min) / span) * 72).toFixed(1) + " " + q[1].toFixed(1)).join(" ");
  const join = type === "4" ? "round" : "round";
  return svg(`<svg viewBox="0 0 80 46" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="${join}"/></svg>`);
}
function heroArt() {
  return svg(`<svg viewBox="0 0 360 300" role="img" aria-label="Illustration of wave, curl and coil patterns">
    <rect width="360" height="300" rx="28" fill="#f0e3f1"/>
    <circle cx="300" cy="52" r="34" fill="#e9a63a"/>
    <path d="M30 86 q20 -22 40 0 t40 0 t40 0 t40 0 t40 0 t40 0" fill="none" stroke="#4b2150" stroke-width="9" stroke-linecap="round"/>
    <path d="M30 150 c0-24 30-24 30 0 s30 24 30 0 s30-24 30 0 s30 24 30 0 s30-24 30 0 s30 24 30 0 s30-24 30 0" fill="none" stroke="#cf6544" stroke-width="9" stroke-linecap="round"/>
    <path d="M30 214 l16 -22 l16 44 l16 -44 l16 44 l16 -44 l16 44 l16 -44 l16 44 l16 -44 l16 44 l16 -22" fill="none" stroke="#3f7a62" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="30" y="276" font-family="Georgia, serif" font-size="16" fill="#4b2150" font-weight="700">2A to 4C, and everything in between</text>
  </svg>`);
}

/* ---------- networking ---------- */
async function streamPost(url, body, onEvent) {
  const isForm = body instanceof FormData;
  const res = await fetch(url, { method: "POST", headers: isForm ? {} : { "Content-Type": "application/json" }, body: isForm ? body : JSON.stringify(body) });
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (line) onEvent(JSON.parse(line)); }
  }
}

/* ---------- accounts (optional) ---------- */
async function api(url, method, body) {
  const res = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = null;
  if (res.status !== 204) { try { data = await res.json(); } catch {} }
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.");
  return data;
}
async function saveToAccount() {
  if (!state.user || !state.result) return;
  try { await api("/api/account/saved", "PUT", { profile: state.profile, result: state.result }); } catch {}
}
/* After signing in: use the routine saved on the account, or save the one already on this device. */
async function syncAfterAuth() {
  try {
    const { saved } = await api("/api/account/saved", "GET");
    if (saved) {
      state.profile = { ...defaultProfile(), ...saved.profile }; state.result = saved.result; state.lastWash = saved.result?.last_wash || null; state.today = null; save();
    } else if (state.result) await saveToAccount();
  } catch {}
}
function setUser(user) { state.user = user; renderNav(); }
function renderNav() {
  const u = state.user;
  document.getElementById("nav-signin").hidden = !!u;
  const acct = document.getElementById("nav-account");
  acct.hidden = !u; acct.textContent = u ? `Hi, ${u.first_name}` : "";
  document.getElementById("nav-logout").hidden = !u;
}
const PASSWORD_RULES = [
  [(v) => v.length >= 10, "At least 10 characters"], [(v) => /[A-Za-z]/.test(v), "A letter"],
  [(v) => /\d/.test(v), "A number"], [(v) => /[^A-Za-z0-9\s]/.test(v), "A special character (like ! ? # $ %)"],
];
function passwordChecklist(getValue) {
  const list = h("ul", { class: "rules", "aria-live": "polite" });
  const update = () => list.replaceChildren(...PASSWORD_RULES.map(([ok, label]) => h("li", { class: ok(getValue()) ? "ok" : "" }, (ok(getValue()) ? "✓ " : "○ ") + label)));
  update();
  return { el: list, update };
}

/* ---------- shell ---------- */
const app = document.getElementById("app");
function go(step) { state.step = step; state.error = ""; render(); window.scrollTo({ top: 0, behavior: "smooth" }); document.getElementById("main").focus({ preventScroll: true }); }

function render() {
  app.replaceChildren(views[state.step]());
  document.getElementById("nav-today").hidden = !state.result;
  document.getElementById("nav-restart").hidden = state.step === "welcome";
  renderNav();
}
document.getElementById("nav-signin").onclick = () => { state.authTab = "login"; go("auth"); };
document.getElementById("nav-account").onclick = () => go("account");
document.getElementById("nav-logout").onclick = async () => { await doLogout(); };
async function doLogout() {
  try { await api("/api/auth/logout", "POST"); } catch {}
  try { localStorage.removeItem(SAVE_KEY); } catch {}  // don't leave someone's hair profile on a shared device
  state.user = null; state.profile = defaultProfile(); state.result = null; state.today = null; state.photo = null; state.lastWash = null;
  renderNav(); go("welcome");
}
document.getElementById("nav-today").onclick = () => { state.tab = "today"; go("results"); };
document.getElementById("nav-restart").onclick = () => { if (confirm("Start over? Your saved routine stays until you build a new one.")) { state.profile = { ...defaultProfile(), zip_code: state.profile.zip_code }; state.photo = null; go("welcome"); } };

function stepper(active) {
  const names = [["photo", "1 · Photo"], ["hair", "2 · Your hair"], ["life", "3 · Your life"], ["building", "4 · Your routine"]];
  const idx = names.findIndex((n) => n[0] === active);
  return h("ol", { class: "stepper", "aria-label": "Progress" }, names.map(([k, label], i) => h("li", { class: i === idx ? "on" : i < idx ? "done" : "", "aria-current": i === idx ? "step" : false }, label)));
}
function errorBox() { return state.error ? h("div", { class: "error", role: "alert" }, state.error) : null; }

/* ---------- widgets ---------- */
function chipGroup(options, value, onPick, { multi = false } = {}) {
  return h("div", { class: "chips", role: multi ? "group" : "radiogroup" }, options.map(([val, label]) => {
    const on = multi ? value.includes(val) : value === val;
    return h("button", { type: "button", class: "chip", [multi ? "aria-pressed" : "aria-checked"]: String(on), role: multi ? false : "radio", onclick: () => onPick(val) }, label);
  }));
}
function optGroup(options, value, onPick) {
  return h("div", { class: "grid two", role: "radiogroup" }, options.map(([val, title, sub]) =>
    h("button", { type: "button", class: "opt", role: "radio", "aria-checked": String(value === val), onclick: () => onPick(val) }, h("b", {}, title), sub ? h("span", {}, sub) : null)));
}
function toggle(label, key) {
  return h("label", { class: "toggle" }, h("input", { type: "checkbox", checked: state.profile[key] || false, onchange: (e) => { state.profile[key] = e.target.checked; } }), label);
}
function rangeField(label, key, min, max, step, fmt) {
  const out = h("span", { class: "range-val" }, fmt(state.profile[key]));
  const input = h("input", { type: "range", min, max, step, value: state.profile[key], "aria-label": label, oninput: (e) => { state.profile[key] = Number(e.target.value); out.textContent = fmt(state.profile[key]); } });
  return h("div", { style: "margin-bottom:18px" }, h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "label" }, label), out), input);
}
function rerenderKeep(fn) { const y = window.scrollY; fn(); render(); window.scrollTo(0, y); }

/* ---------- views ---------- */
const views = {};

views.welcome = () => {
  const back = state.result && h("section", { class: "card honey", "aria-labelledby": "wb" },
    h("h2", { id: "wb" }, "Welcome back"),
    h("p", {}, "Your routine is saved on this device. Check what to do today, or look at your week."),
    h("div", { class: "row" },
      h("button", { class: "btn", onclick: () => { state.tab = "today"; go("results"); } }, "What should I do today?"),
      h("button", { class: "btn ghost", onclick: () => { state.tab = "overview"; go("results"); } }, "See my routine")));
  return h("div", {},
    h("section", { class: "hero" },
      h("div", {},
        h("h1", {}, "Your hair. Your weather. Your routine."),
        h("p", { class: "lead" }, "A personal routine for waves, curls, coils and locs, built around your hair type, your forecast, your time and your budget. Real products you can buy in the US, with the real cost per month."),
        h("div", { class: "pills" }, ["Every texture, 2A to 4C", "Every gender", "Short hair, braids and locs welcome", "Budget friendly"].map((t) => h("span", { class: "pill" }, t))),
        h("button", { class: "btn", onclick: () => go("photo") }, "Build my routine →")),
      h("div", { class: "hero-art" }, heroArt())),
    back,
    !state.user && h("section", { class: "card soft", "aria-labelledby": "acct" },
      h("h2", { id: "acct" }, "Want to keep your routine?"),
      h("p", {}, "You don't need an account to build a routine. If you make one (it's free), your profile and latest routine are saved so you can open them on any device."),
      h("div", { class: "row" },
        h("button", { class: "btn ghost", onclick: () => { state.authTab = "register"; go("auth"); } }, "Create an account"),
        h("button", { class: "btn ghost", onclick: () => { state.authTab = "login"; go("auth"); } }, "Sign in"))),
    h("section", { class: "features", "aria-label": "How it works" },
      [["Photo, if you like", "Not sure of your curl pattern or porosity? Upload a wash-day photo and we'll make our best estimate. You can correct it."],
       ["Weather aware", "We read your 7-day dew point, rain and wind, so humidity and dry air don't wreck your wash day."],
       ["Protein and moisture balanced", "Too much of either causes breakage. We check your hair's signs and pick products to match."],
       ["Honest about cost", "Picks come only from a verified US catalog, and every price and monthly cost is computed, not guessed."]]
        .map(([t, d]) => h("div", { class: "feature" }, h("b", {}, t), h("span", { class: "muted" }, d)))));
};

views.photo = () => {
  const box = h("div", { id: "photo-box" });
  const input = h("input", { type: "file", accept: "image/*", id: "photo-file", hidden: true, onchange: (e) => pick(e.target.files[0]) });
  const drop = h("div", { class: "drop", role: "button", tabindex: "0", "aria-label": "Choose a hair photo", onclick: () => input.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } },
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); }, ondragleave: () => drop.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); } },
    h("b", {}, "Tap to upload or drop a photo here"), h("div", { class: "muted small" }, "JPG or PNG, up to 8 MB"));

  async function pick(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) { state.error = "Please choose an image file."; render(); return; }
    state.error = "";
    const url = URL.createObjectURL(file);
    drop.replaceChildren(h("img", { src: url, alt: "Your uploaded hair photo preview" }), h("div", { class: "muted" }, "Analyzing your photo…"));
    const form = new FormData(); form.append("file", file);
    try {
      let out = null, err = null;
      await streamPost("/api/photo", form, (ev) => { if (ev.event === "result") out = ev.data; if (ev.event === "error") err = ev.message; });
      if (err) throw new Error(err);
      state.photo = out; state.photoUrl = url; renderPhotoResult();
    } catch (e) { state.error = e.message; render(); }
  }
  function renderPhotoResult() {
    const a = state.photo.analysis;
    const conf = (c) => h("span", { class: "conf " + c }, c + " confidence");
    box.replaceChildren();
    if (!a.is_hair_photo || a.photo_quality === "poor" && !a.curl_pattern) {
      box.append(h("div", { class: "card alert" }, h("h3", {}, "Let's try another photo"), h("p", {}, a.problem || "We couldn't read the hair in that photo."), h("p", { class: "muted small" }, "Your photo was not stored.")));
      return;
    }
    box.append(h("div", { class: "card soft" },
      h("h3", {}, "Here's what we see"),
      h("p", {}, a.summary),
      h("div", { class: "result-grid" },
        h("div", { class: "stat" }, h("small", {}, "Curl pattern"), h("b", {}, a.curl_pattern || "Not sure"), h("div", {}, conf(a.pattern_confidence)), a.alternate_pattern ? h("small", {}, "Could also be " + a.alternate_pattern) : null),
        h("div", { class: "stat" }, h("small", {}, "Porosity (estimate)"), h("b", {}, a.porosity_estimate ? cap(a.porosity_estimate) : "Not sure"), h("div", {}, conf(a.porosity_confidence))),
        a.strand_width ? h("div", { class: "stat" }, h("small", {}, "Strand width"), h("b", {}, cap(a.strand_width))) : null,
        a.density ? h("div", { class: "stat" }, h("small", {}, "Density"), h("b", {}, cap(a.density))) : null),
      a.mixed_patterns ? h("p", { class: "small" }, "Different sections of your hair may have different patterns. That's very common.") : null,
      h("p", { class: "small muted" }, "A photo can't measure porosity. You can confirm it with a quick strand test: a clean strand that floats a long time suggests low porosity, one that sinks fast suggests high. You'll be able to change anything on the next screen. Photo estimates are not stored."),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: () => { applyPhoto(a); go("hair"); } }, "Use these and continue →"))));
  }
  if (state.photo) setTimeout(renderPhotoResult);

  return h("div", {}, stepper("photo"),
    h("section", { class: "card" },
      h("h2", {}, "Start with a photo (optional)"),
      h("p", { class: "muted" }, "Not sure if you're a 3B or a 4A? A photo of freshly washed hair, with no products or styling, helps us estimate your pattern and what your hair may need. You can skip this and answer the questions yourself."),
      input, drop, errorBox(), box,
      h("ul", { class: "tips" }, ["Take it right after washing, with no product or styling", "Use natural light, such as near a window", "Show your hair loose, not stretched or pulled back", "Make sure the photo is in focus and shows your hair, not just your face"].map((t) => h("li", {}, t))),
      h("p", { class: "small muted", style: "margin-top:14px" }, "Your photo is analyzed in memory and is never saved. We don't guess anything about you except your hair."),
      h("div", { class: "row end" }, h("button", { class: "btn ghost", onclick: () => go("welcome") }, "← Back"), h("button", { class: "btn ghost", onclick: () => go("hair") }, state.photo ? "Skip the estimate" : "Skip the photo"))));
};

function applyPhoto(a) {
  const p = state.profile;
  p.photo_analysis = a;
  if (a.curl_pattern && a.pattern_confidence !== "low") p.curl_pattern = a.curl_pattern;
  else if (a.curl_pattern && !p.curl_pattern) p.curl_pattern = a.curl_pattern;
  if (a.porosity_estimate && !p.porosity) p.porosity = a.porosity_estimate;
  if (a.strand_width && !p.strand_width) p.strand_width = a.strand_width;
  if (a.density && !p.density) p.density = a.density;
}

views.hair = () => {
  const p = state.profile;
  const patterns = ["2A", "2B", "2C", "3A", "3B", "3C", "4A", "4B", "4C"];
  const set = (k, v) => rerenderKeep(() => { p[k] = v; });
  return h("div", {}, stepper("hair"),
    h("section", { class: "card" },
      h("h2", {}, "About your hair"),
      p.photo_analysis ? h("p", { class: "muted" }, "We filled in what we could from your photo. Change anything that doesn't match your experience.") : h("p", { class: "muted" }, "Answer what you know. \"Not sure\" is always fine."),
      h("fieldset", {}, h("legend", {}, "Curl pattern"), h("p", { class: "hint" }, "2 = waves, 3 = curls, 4 = coils. A is looser, C is tighter. Many people have more than one."),
        h("div", { class: "grid pat", role: "radiogroup", "aria-label": "Curl pattern" },
          patterns.map((pt) => h("button", { type: "button", class: "opt pat-btn", role: "radio", "aria-checked": String(p.curl_pattern === pt), onclick: () => set("curl_pattern", pt) }, patternSVG(pt), h("b", {}, pt))),
          h("button", { type: "button", class: "opt pat-btn", role: "radio", "aria-checked": String(p.curl_pattern === null), onclick: () => set("curl_pattern", null) }, h("div", { style: "height:46px;display:grid;place-items:center;font-size:1.6rem" }, "?"), h("b", {}, "Not sure")))),
      h("fieldset", {}, h("legend", {}, "Porosity"), h("p", { class: "hint" }, "How quickly your hair soaks up and loses water."),
        chipGroup([["low", "Low (slow to get wet)"], ["medium", "Medium"], ["high", "High (soaks up and dries fast)"], [null, "Not sure"]], p.porosity, (v) => set("porosity", v))),
      h("fieldset", {}, h("legend", {}, "Strand width"),
        chipGroup([["fine", "Fine"], ["medium", "Medium"], ["coarse", "Coarse"], [null, "Not sure"]], p.strand_width, (v) => set("strand_width", v))),
      h("fieldset", {}, h("legend", {}, "Hair length"),
        chipGroup([["buzzed_or_very_short", "Buzzed or very short"], ["short", "Short"], ["medium", "Medium"], ["long", "Long"]], p.hair_length, (v) => set("hair_length", v))),
      h("fieldset", {}, h("legend", {}, "The stretch test"), h("p", { class: "hint" }, "Gently stretch one clean, wet strand. What does it do? This tells us whether your hair needs more protein or more moisture."),
        optGroup([["stretches_and_bounces_back", "Stretches, then bounces back", "Usually balanced"], ["stretches_and_stays_stretched", "Stretches and stays stretched", "Often needs protein (mushy, gummy)"], ["snaps_quickly", "Snaps with little stretch", "Often needs moisture (brittle, straw-like)"], ["not_sure", "I haven't tried it", "We'll start with a gentle default"]], p.elasticity, (v) => set("elasticity", v))),
      h("fieldset", {}, h("legend", {}, "What would you like help with?"),
        chipGroup(CONCERNS, p.concerns, (v) => rerenderKeep(() => { p.concerns = p.concerns.includes(v) ? p.concerns.filter((c) => c !== v) : [...p.concerns, v]; }), { multi: true })),
      h("fieldset", {}, h("legend", {}, "Treatments"), toggle("My hair is color-treated", "color_treated"), toggle("I use heat tools regularly", "heat_styled"), toggle("My hair is relaxed, straightened chemically, or bleached", "chemically_relaxed_or_bleached")),
      h("div", { class: "row end" }, h("button", { class: "btn ghost", onclick: () => go("photo") }, "← Back"), h("button", { class: "btn", onclick: () => go("life") }, "Next →"))));
};

views.life = () => {
  const p = state.profile;
  const zip = h("input", { type: "text", inputmode: "numeric", maxlength: "5", autocomplete: "postal-code", id: "zip", value: p.zip_code, placeholder: "e.g. 60614", "aria-describedby": "zip-hint", oninput: (e) => { p.zip_code = e.target.value.replace(/\D/g, "").slice(0, 5); e.target.value = p.zip_code; } });
  const notes = h("textarea", { rows: "3", maxlength: "300", id: "notes", placeholder: "Anything else we should know? (optional)", oninput: (e) => { p.notes = e.target.value; } }, p.notes);
  const set = (k, v) => rerenderKeep(() => { p[k] = v; });
  return h("div", {}, stepper("life"),
    h("section", { class: "card" },
      h("h2", {}, "About your life"),
      h("div", { style: "margin-bottom:22px" }, h("label", { class: "label", for: "zip" }, "Your US ZIP code"), h("p", { class: "hint", id: "zip-hint" }, "Used to read your local forecast. It's kept in our private run log for 90 days, and with your saved profile if you sign in."), zip),
      optGroup(STYLE_GOALS, p.style_goal, (v) => set("style_goal", v)),
      h("div", { style: "height:22px" }),
      rangeField("How often do you wash?", "wash_every_days", 1, 30, 1, (v) => (v === 1 ? "Every day" : `Every ${v} days`)),
      rangeField("Time you have on a normal day", "minutes_per_day", 5, 60, 5, (v) => `${v} minutes`),
      rangeField("Time you have on wash day", "wash_day_minutes", 20, 240, 10, (v) => `${v} minutes`),
      rangeField("Monthly budget for hair products", "monthly_budget_usd", 5, 150, 5, (v) => `$${v} a month`),
      h("p", { class: "hint" }, "We count what you actually use each month, not the full price of every bottle."),
      h("fieldset", {}, h("legend", {}, "Product preferences"), toggle("Sulfate-free only", "sulfate_free"), toggle("Silicone-free only", "silicone_free"), toggle("Fragrance-free only", "fragrance_free")),
      h("div", {}, h("label", { class: "label", for: "notes" }, "Notes"), notes, h("p", { class: "hint" }, "Treated as information about you, never as instructions.")),
      errorBox(),
      h("div", { class: "row end" }, h("button", { class: "btn ghost", onclick: () => go("hair") }, "← Back"),
        h("button", { class: "btn honey", onclick: () => { if (!/^\d{5}$/.test(p.zip_code)) { state.error = "Please enter a 5-digit US ZIP code."; render(); return; } startBuild(); } }, "Build my routine ✨"))));
};

views.auth = () => {
  const reg = state.authTab === "register";
  const f = { first: "", last: "", email: "", pw: "", pw2: "" };
  const field = (label, key, type, ac) => h("div", { style: "margin-bottom:14px" }, h("label", { class: "label", for: "f-" + key }, label),
    h("input", { type, id: "f-" + key, autocomplete: ac, maxlength: key === "pw" || key === "pw2" ? "128" : "254", required: true,
      oninput: (e) => { f[key] = e.target.value; if (key === "pw" && check) check.update(); } }));
  const check = reg ? passwordChecklist(() => f.pw) : null;
  const msg = h("div", { id: "auth-msg", "aria-live": "assertive" }, state.error ? h("div", { class: "error", role: "alert" }, state.error) : null);
  const submit = h("button", { class: "btn", type: "submit" }, reg ? "Create account" : "Sign in");
  const form = h("form", { novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); submit.disabled = true; state.error = "";
    try {
      const out = reg
        ? await api("/api/auth/register", "POST", { first_name: f.first, last_name: f.last, email: f.email, password: f.pw, confirm_password: f.pw2 })
        : await api("/api/auth/login", "POST", { email: f.email, password: f.pw });
      setUser(out.user); await syncAfterAuth();
      if (out.password_update_required) { state.authMsg = "Your password no longer meets our rules. Please choose a new one."; go("account"); }
      else go(state.result ? "results" : "welcome");
    } catch (err) { state.error = err.message; msg.replaceChildren(h("div", { class: "error", role: "alert" }, err.message)); submit.disabled = false; }
  } },
    reg ? h("div", { class: "grid two" }, field("First name", "first", "text", "given-name"), field("Last name", "last", "text", "family-name")) : null,
    field("Email", "email", "email", "email"),
    field("Password", "pw", "password", reg ? "new-password" : "current-password"),
    reg ? [check.el, field("Confirm password", "pw2", "password", "new-password")] : null,
    msg, h("div", { class: "row end" }, h("button", { class: "btn ghost", type: "button", onclick: () => go(state.result ? "results" : "welcome") }, "← Back"), submit));
  return h("div", {}, h("section", { class: "card", style: "max-width:560px;margin:18px auto" },
    h("div", { class: "tabs", role: "tablist" },
      h("button", { class: "tab", role: "tab", "aria-selected": String(!reg), type: "button", onclick: () => { state.authTab = "login"; state.error = ""; render(); } }, "Sign in"),
      h("button", { class: "tab", role: "tab", "aria-selected": String(reg), type: "button", onclick: () => { state.authTab = "register"; state.error = ""; render(); } }, "Create account")),
    h("h2", {}, reg ? "Create your account" : "Welcome back"),
    h("p", { class: "muted" }, reg ? "Free, and optional. We save your hair profile and latest routine so you can open them anywhere. Your photo is never saved." : "Sign in to open your saved routine."),
    form));
};

views.account = () => {
  const u = state.user;
  if (!u) return views.auth();
  const f = { cur: "", pw: "", pw2: "" };
  const field = (label, key, ac) => h("div", { style: "margin-bottom:14px" }, h("label", { class: "label", for: "a-" + key }, label),
    h("input", { type: "password", id: "a-" + key, autocomplete: ac, maxlength: "128", oninput: (e) => { f[key] = e.target.value; if (key === "pw") check.update(); } }));
  const check = passwordChecklist(() => f.pw);
  const msg = h("div", { "aria-live": "assertive" }, state.authMsg ? h("div", { class: "error", role: "alert" }, state.authMsg) : null);
  state.authMsg = "";
  const btn = h("button", { class: "btn", type: "submit" }, "Update password");
  return h("div", {},
    h("section", { class: "card", style: "max-width:640px;margin:18px auto" },
      h("h2", {}, `${u.first_name} ${u.last_name}`), h("p", { class: "muted" }, u.email),
      h("p", {}, state.result ? "Your latest routine is saved to this account." : "You haven't built a routine yet. Once you do, it's saved here automatically."),
      h("div", { class: "row" }, state.result ? h("button", { class: "btn", onclick: () => { state.tab = "overview"; go("results"); } }, "Open my routine") : h("button", { class: "btn", onclick: () => go("photo") }, "Build my routine"),
        h("button", { class: "btn ghost", onclick: doLogout }, "Log out"))),
    h("section", { class: "card", style: "max-width:640px;margin:0 auto 18px" }, h("h3", {}, "Change your password"),
      h("form", { novalidate: true, onsubmit: async (e) => {
        e.preventDefault(); btn.disabled = true;
        try {
          const out = await api("/api/auth/change-password", "POST", { current_password: f.cur, new_password: f.pw, confirm_password: f.pw2 });
          setUser(out.user); msg.replaceChildren(h("div", { class: "ok-box", role: "status" }, "Password updated."));
          e.target.reset(); f.cur = f.pw = f.pw2 = ""; check.update();
        } catch (err) { msg.replaceChildren(h("div", { class: "error", role: "alert" }, err.message)); }
        btn.disabled = false;
      } }, field("Current password", "cur", "current-password"), field("New password", "pw", "new-password"), check.el, field("Confirm new password", "pw2", "new-password"), msg, btn)));
};

/* ---------- build ---------- */
async function startBuild() {
  state.error = ""; state.step = "building"; state.buildStatus = {}; state.buildNote = "Getting started…"; render();
  const payload = { ...state.profile };
  if (!payload.photo_analysis) delete payload.photo_analysis;
  let result = null, err = null;
  try {
    await streamPost("/api/build", payload, (ev) => {
      if (ev.event === "agent_start") state.buildStatus[ev.agent] = { s: "working" };
      if (ev.event === "agent_done") state.buildStatus[ev.agent] = { s: "done", u: ev.usage };
      if (ev.event === "tool" && ev.tool !== "final_result") state.buildNote = `${AGENT_LABELS[ev.agent]?.[0] || ev.agent} is using its ${ev.tool.replace(/_/g, " ")} tool…`;
      if (ev.event === "paused") state.buildNote = "Paused. Your run will continue when the app resumes.";
      if (ev.event === "result") result = ev.data;
      if (ev.event === "error") err = ev.message;
      if (state.step === "building") render();
    });
  } catch (e) { err = e.message; }
  if (err || !result) { state.error = err || "Something went wrong."; state.step = "life"; render(); return; }
  state.result = result; state.today = null; state.tab = "overview"; state.lastWash = null; save(); saveToAccount();
  go("results");
}

views.building = () => h("div", {}, stepper("building"),
  h("section", { class: "card" },
    h("h2", {}, "Your team is building your routine"),
    h("p", { class: "muted", "aria-live": "polite" }, state.buildNote),
    h("div", { class: "agents" }, BUILD_AGENTS.map((a) => {
      const st = state.buildStatus[a] || { s: "waiting" };
      return h("div", { class: "agent " + st.s }, h("div", { class: "dot", "aria-hidden": "true" }, st.s === "done" ? "✓" : st.s === "working" ? "…" : ""),
        h("div", {}, h("b", {}, AGENT_LABELS[a][0]), h("small", {}, AGENT_LABELS[a][1])),
        h("div", { class: "small muted" }, st.s === "done" ? "done" : st.s === "working" ? "working" : "waiting"));
    }))));

/* ---------- haircut (one-time, optional) ---------- */
const hc = { prefs: { change: "trim_and_shape", maintenance: "medium", goals: [], notes: "" }, avail: { days: [], times: [], from: "", to: "" }, selected: 0, edited: false, draft: "", busy: false, error: "", copied: false };
const LENGTH_WORDS = { buzzed_or_very_short: "buzzed or very short", short: "short", medium: "medium-length", long: "long" };
const CHANGE_WORDS = { keep_length: "keep my length and dust the ends", trim_and_shape: "a trim and shape", noticeably_shorter: "a noticeably shorter cut", much_shorter: "a much shorter cut" };

function dateWord(iso) { return iso ? new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : ""; }

function appointmentDraft(r) {
  const p = state.profile, a = hc.avail, opt = r.haircut.suggestion.options[hc.selected] || r.haircut.suggestion.options[0];
  const hair = `${LENGTH_WORDS[p.hair_length]}${p.strand_width ? `, with ${p.strand_width} strands` : ""}`;
  const day = a.days.length ? a.days.join(", ") : "";
  const time = a.times.length ? (day ? ` (${a.times.join(" or ")})` : a.times.join(" or ")) : "";
  const range = a.from && a.to ? `between ${dateWord(a.from)} and ${dateWord(a.to)}` : a.from ? `from ${dateWord(a.from)}` : a.to ? `until ${dateWord(a.to)}` : "";
  const avail = day || time || range ? `I'm available ${[day + time, range].filter(Boolean).join(", ")}.` : "I'm flexible on timing.";
  const name = state.user?.first_name || "";
  return [
    "Hi,",
    "",
    `I'd like to book a haircut with a stylist who regularly cuts ${p.curl_pattern ? p.curl_pattern + " " : ""}textured hair. My hair is ${hair}. I'm looking for ${CHANGE_WORDS[hc.prefs.change]}, something like: ${opt.name}.`,
    "",
    avail,
    "",
    "Could you tell me: which stylist cuts my texture, whether they cut curls dry, the price range, and the earliest opening in that window?",
    "",
    name ? `Thank you,\n${name}` : "Thank you!",
  ].join("\n");
}

async function runHaircut(r) {
  const profile = { ...state.profile }; if (!profile.photo_analysis) delete profile.photo_analysis;
  hc.busy = true; hc.error = ""; render();
  let res = null, err = null;
  try { await streamPost("/api/haircut", { profile, prefs: hc.prefs }, (ev) => { if (ev.event === "result") res = ev.data; if (ev.event === "error") err = ev.message; }); } catch (e) { err = e.message; }
  hc.busy = false;
  if (err || !res) { hc.error = err || "Something went wrong."; render(); return; }
  r.haircut = res; hc.selected = 0; hc.edited = false; save(); saveToAccount(); render();
}

function tabHaircut(r) {
  const set = (k, v) => { hc.prefs[k] = v; render(); };
  if (!r.haircut) {
    return h("section", { class: "card" },
      h("h2", {}, "A haircut idea (optional)"),
      h("p", { class: "muted" }, "Want a fresh cut as well as a routine? Using your answers, we'll suggest a few options to bring to a stylist, then help you find stylists near you and write an appointment request. It's a one-time suggestion for any gender. Face shape isn't considered; ideas come from your texture, length, density and upkeep."),
      h("fieldset", {}, h("legend", {}, "How much change do you want?"), chipGroup([["keep_length", "Keep my length"], ["trim_and_shape", "Trim and shape"], ["noticeably_shorter", "Noticeably shorter"], ["much_shorter", "Much shorter"]], hc.prefs.change, (v) => set("change", v))),
      h("fieldset", {}, h("legend", {}, "How much upkeep will you do?"), chipGroup([["low", "As little as possible"], ["medium", "Some"], ["high", "I like a sharp shape"]], hc.prefs.maintenance, (v) => set("maintenance", v))),
      h("fieldset", {}, h("legend", {}, "What matters most?"), chipGroup([["shape", "Better shape"], ["volume_balance", "Balance volume"], ["remove_damage", "Remove damaged ends"], ["easier_styling", "Easier styling"], ["definition", "More definition"], ["grow_out", "Growing it out"]],
        hc.prefs.goals, (v) => { hc.prefs.goals = hc.prefs.goals.includes(v) ? hc.prefs.goals.filter((g) => g !== v) : [...hc.prefs.goals, v]; render(); }, { multi: true })),
      h("div", {}, h("label", { class: "label", for: "hc-notes" }, "Anything else? (optional)"), h("textarea", { id: "hc-notes", rows: "2", maxlength: "300", oninput: (e) => { hc.prefs.notes = e.target.value; } }, hc.prefs.notes), h("p", { class: "hint" }, "Treated as information about you, never as instructions.")),
      hc.error ? h("div", { class: "error", role: "alert" }, hc.error) : null,
      h("div", { class: "row end" }, h("span", { class: "small muted" }, "Takes about 10 seconds."), h("button", { class: "btn honey", disabled: hc.busy, onclick: () => runHaircut(r) }, hc.busy ? "Thinking…" : "Suggest a haircut")));
  }
  const sg = r.haircut.suggestion, a = hc.avail;
  const chip = (arr, label, val) => h("button", { type: "button", class: "chip", "aria-pressed": String(arr.includes(val)), onclick: () => { const i = arr.indexOf(val); if (i >= 0) arr.splice(i, 1); else arr.push(val); if (!hc.edited) hc.draft = ""; render(); } }, label);
  if (!hc.draft || !hc.edited) hc.draft = appointmentDraft(r);
  const draftEl = h("textarea", { id: "hc-draft", rows: "11", "aria-label": "Appointment request", oninput: (e) => { hc.draft = e.target.value; hc.edited = true; } }, hc.draft);
  const dateIn = (id, label, key) => h("div", {}, h("label", { class: "label", for: id }, label), h("input", { type: "date", id, value: a[key],
    onchange: (e) => { a[key] = /^\d{4}-\d{2}-\d{2}$/.test(e.target.value) ? e.target.value : ""; if (!hc.edited) hc.draft = ""; render(); } }));
  return h("div", {},
    h("section", { class: "card" }, h("h2", {}, "Haircut ideas to bring to a stylist"),
      h("div", { class: "products" }, sg.options.map((o, i) => h("article", { class: "product", style: hc.selected === i ? "outline:3px solid var(--plum); outline-offset:-3px" : "" },
        h("div", { class: "cat" }, `Option ${i + 1}`), h("h3", {}, o.name), h("p", { class: "small" }, o.description), h("p", { class: "small" }, h("b", {}, "Why for you: "), o.why_for_you),
        h("p", { class: "small" }, h("b", {}, "How much comes off: "), o.length_change), h("p", { class: "small" }, h("b", {}, "Upkeep: "), o.upkeep),
        h("div", { class: "small" }, h("b", {}, "Say to your stylist:"), h("ul", {}, o.ask_your_stylist.map((q) => h("li", {}, `"${q}"`)))),
        h("button", { class: "btn ghost", type: "button", onclick: () => { hc.selected = i; hc.edited = false; render(); } }, hc.selected === i ? "Selected for my request" : "Use this in my request")))),
      h("div", { class: "grid two", style: "margin-top:14px" },
        h("div", {}, h("h3", {}, "Avoid"), h("ul", {}, sg.avoid.map((x) => h("li", {}, x))), h("h3", {}, "Bring or do beforehand"), h("ul", {}, sg.bring.map((x) => h("li", {}, x)))),
        h("div", {}, h("h3", {}, "Questions to ask a salon"), h("ul", {}, sg.stylist_questions.map((x) => h("li", {}, x))))),
      h("p", { class: "small muted" }, sg.note),
      h("div", { class: "row" }, h("button", { class: "btn ghost", onclick: () => { delete r.haircut; save(); saveToAccount(); render(); } }, "Change my answers"))),
    h("section", { class: "card soft" }, h("h2", {}, "Find stylists near you"),
      h("p", {}, "Search links for your ZIP code and your texture. We don't recommend specific salons, because we can't verify them. Check each stylist's reviews and photos of work on textures like yours."),
      h("div", { class: "grid two" }, r.haircut.links.map((l) => h("div", { class: "card" }, h("a", { class: "btn", href: l.url, target: "_blank", rel: "noopener noreferrer" }, l.label + " ↗"), h("p", { class: "small muted", style: "margin-top:8px" }, l.why))))),
    h("section", { class: "card" }, h("h2", {}, "Appointment request"),
      h("p", { class: "muted" }, "Tell us when you're free and we'll write the message. We can't call or book for you, so copy it into the salon's website form, email or text, or call and read it out."),
      h("div", { class: "label" }, "Days you're free"), h("div", { class: "chips" }, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => chip(a.days, d, d))),
      h("div", { class: "label", style: "margin-top:12px" }, "Times of day"), h("div", { class: "chips" }, [["morning", "Morning"], ["afternoon", "Afternoon"], ["evening", "Evening"]].map(([v, l]) => chip(a.times, l, v))),
      h("div", { class: "grid two", style: "margin-top:12px" }, dateIn("hc-from", "Earliest date (optional)", "from"), dateIn("hc-to", "Latest date (optional)", "to")),
      h("div", { style: "margin-top:14px" }, h("label", { class: "label", for: "hc-draft" }, "Your message (edit anything)"), draftEl),
      h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "btn", type: "button", onclick: async (e) => { try { await navigator.clipboard.writeText(draftEl.value); e.target.textContent = "Copied ✓"; setTimeout(() => (e.target.textContent = "Copy message"), 1800); } catch { draftEl.select(); } } }, "Copy message"),
        h("a", { class: "btn ghost", href: `mailto:?subject=${encodeURIComponent("Haircut appointment request")}&body=${encodeURIComponent(hc.draft)}` }, "Open in my email"),
        hc.edited ? h("button", { class: "btn ghost", type: "button", onclick: () => { hc.edited = false; render(); } }, "Reset message") : null)));
}

/* ---------- results ---------- */
const TABS = [["overview", "Overview"], ["today", "Today"], ["week", "This week"], ["products", "Products & cost"], ["weather", "Weather"], ["haircut", "Haircut"], ["details", "Behind the scenes"]];

views.results = () => {
  const r = state.result;
  if (!r) return views.welcome();
  const tabs = h("div", { class: "tabs", role: "tablist" }, TABS.filter(([k]) => k !== "weather" || r.weather).map(([k, label]) =>
    h("button", { class: "tab", role: "tab", "aria-selected": String(state.tab === k), onclick: () => { state.tab = k; render(); } }, label)));
  const panel = { overview: tabOverview, today: tabToday, week: tabWeek, products: tabProducts, weather: tabWeather, haircut: tabHaircut, details: tabDetails }[state.tab](r);
  return h("div", {}, h("h1", { style: "font-size:clamp(1.8rem,4vw,2.6rem);margin-top:14px" }, r.headline), tabs, h("div", { role: "tabpanel" }, panel));
};

function prodName(r, id) { const p = r.products.find((x) => x.id === id); return p ? `${p.brand} ${p.name}` : null; }

function stepList(steps, lookup) {
  if (!steps.length) return h("p", { class: "muted" }, "Nothing to do today. Let your hair rest.");
  return h("ol", { class: "steps" }, steps.map((s) => h("li", {},
    h("b", {}, s.action), s.minutes ? h("span", { class: "mins" }, `  · ${s.minutes} min`) : null,
    s.product_id && lookup(s.product_id) ? h("div", { class: "prod" }, lookup(s.product_id)) : null, h("div", {}, s.how))));
}

function tabOverview(r) {
  const hair = r.hair, c = r.costs;
  return h("div", {},
    hair.see_a_professional ? h("div", { class: "card alert", role: "alert" }, h("h3", {}, "Please see a doctor or dermatologist"), h("p", {}, "Some of what you described, such as hair loss, sores or severe itching, needs a professional. These products won't treat it.")) : null,
    h("section", { class: "card" }, h("h2", {}, "Your hair"), h("p", {}, hair.summary),
      h("p", {}, h("b", {}, "Balance: "), hair.balance.replace(/_/g, " "), ". ", hair.balance_reason),
      h("div", { class: "result-grid" },
        h("div", { class: "stat" }, h("small", {}, "Deep condition"), h("b", {}, `every ${hair.deep_condition_every_days} days`)),
        h("div", { class: "stat" }, h("small", {}, "Protein treatment"), h("b", {}, hair.protein_treatment_every_weeks ? `every ${hair.protein_treatment_every_weeks} weeks` : "not needed")),
        h("div", { class: "stat" }, h("small", {}, "Clarify"), h("b", {}, `every ${hair.clarify_every_weeks} weeks`)),
        h("div", { class: "stat" }, h("small", {}, "Monthly cost"), h("b", {}, money(c.monthly_total)), h("small", {}, `budget ${money(c.budget)}`)))),
    r.weather ? h("section", { class: "card honey" }, h("h3", {}, "This week's weather, for your hair"), h("p", {}, r.weather.summary)) : h("section", { class: "card honey" }, h("p", {}, "We couldn't reach the weather service, so this routine doesn't use your forecast.")),
    h("section", { class: "card" }, h("h2", {}, "Why this routine"), h("ul", {}, r.routine.why.map((w) => h("li", {}, w))),
      r.routine.cautions.length ? h("div", {}, h("h3", {}, "Good to know"), h("ul", {}, r.routine.cautions.map((w) => h("li", {}, w)))) : null),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: () => { state.tab = "today"; render(); } }, "What should I do today?"), h("button", { class: "btn ghost", onclick: () => { state.tab = "week"; render(); } }, "See my week")));
}

function tabWeek(r) {
  const rolled = rollingWeek(r);
  const todayName = DAYS[(new Date().getDay() + 6) % 7];
  const clar = r.routine.clarify_steps || [];
  const days = rolled || r.week;
  const banner = state.lastWash
    ? h("section", { class: "card soft" }, h("p", { style: "margin:0" }, h("b", {}, "Lined up with your last wash: "), friendlyDate(state.lastWash), ". This list starts today and moves with it. Next wash due ", h("b", {}, nextWashDue()), "."),
      h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn ghost", onclick: () => { state.tab = "today"; render(); } }, "Update my last wash")))
    : h("section", { class: "card soft" }, h("p", { style: "margin:0" }, h("b", {}, "Tell us when you last washed "), "and this week will line up with it, starting today."),
      h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn ghost", onclick: () => { state.tab = "today"; render(); } }, "Go to Today")));
  return h("div", {}, banner, h("div", { class: "week" }, [...days.map((d, i) => {
    const isToday = rolled ? i === 0 : d.day === todayName;
    const body = d.steps.length ? h("div", { class: "body" }, stepList(d.steps, (id) => prodName(r, id))) : null;
    if (body) body.hidden = !isToday;
    const label = rolled ? friendlyDate(d.date) : d.day;
    const done = rolled && d.off === 0 && WASH_KINDS.includes(d.kind);
    const btn = h("button", { type: "button", "aria-expanded": body ? String(!body.hidden) : false, onclick: () => { if (!body) return; body.hidden = !body.hidden; btn.setAttribute("aria-expanded", String(!body.hidden)); } },
      h("span", { class: "dn" + (rolled ? " wide" : "") }, label),
      h("span", {}, h("span", { class: "kind " + d.kind }, KIND_LABEL[d.kind]), done ? [" ", h("span", { class: "badge good" }, "Done ✓")] : null, "  ", h("span", { class: "muted" }, d.what)),
      h("span", { class: "mins" }, d.minutes ? `${d.minutes} min` : "—"));
    return h("div", { class: "day" + (isToday ? " today" : "") }, btn, body);
  }), clar.length ? h("div", { class: "card soft" }, h("h3", {}, `Every ${r.hair.clarify_every_weeks} weeks: a clarifying wash`), h("p", { class: "small muted" }, "Swap this in for your regular cleanser on one wash day."), stepList(clar, (id) => prodName(r, id))) : null]));
}

/* "2026-10-25" -> "today", "yesterday", "3 days ago", "2 weeks ago", "4 months ago" */
function relativeDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const then = new Date(y, m - 1, d), now = new Date();
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - then) / 86400000);
  if (!(days > 0)) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  return `${Math.round(days / 30)} months ago`;
}

function productCard(p) {
  const badges = [];
  badges.push(h("span", { class: "badge" + (p.protein === "none" ? " good" : p.protein === "heavy" ? " warn" : "") }, p.protein === "none" ? "No protein" : cap(p.protein) + " protein"));
  if (!p.sulfates) badges.push(h("span", { class: "badge good" }, "Sulfate-free"));
  if (!p.silicones) badges.push(h("span", { class: "badge good" }, "Silicone-free"));
  if (p.fragrance_free) badges.push(h("span", { class: "badge good" }, "Fragrance-free"));
  if (p.humectant_heavy) badges.push(h("span", { class: "badge" }, "Humectant-rich"));
  return h("article", { class: "product" },
    h("div", { class: "cat" }, CATEGORY_LABEL[p.category]), h("h3", {}, p.name), h("div", { class: "brand-name" }, p.brand), h("div", { class: "badges" }, badges),
    p.why ? h("p", { class: "small" }, p.why) : null,
    h("div", { class: "money" }, h("div", {}, h("small", {}, "Price"), h("b", {}, money(p.price_usd)), h("small", {}, `${p.size_oz} oz`)), h("div", {}, h("small", {}, "Per use"), h("b", {}, money(p.cost_per_use))), h("div", {}, h("small", {}, "Per month"), h("b", {}, money(p.monthly_cost)))),
    h("div", { class: "small muted" }, "Seen at: ",
      p.stores.length ? p.stores.map((st, i) => [i ? ", " : "", h("span", { class: "store " + st.toLowerCase().replace(/[^a-z]+/g, "-") }, st)]) : "see link",
      p.price_checked ? [" · price checked ", h("b", { title: `Checked on ${p.price_checked}` }, relativeDate(p.price_checked))] : null),
    p.url ? h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer" }, "View product page ↗") : null);
}

const ADJ = { swap: ["⇄", "Cheaper swap"], dropped: ["−", "Left out to save money"], unused: ["○", "Not needed for your schedule"], upgrade: ["↑", "Pricier option that fits"] };
function adjustmentsList(items) {
  if (!items || !items.length) return null;
  return h("div", { class: "adjust" }, h("h3", {}, "How we kept it in budget"),
    items.map((a) => h("div", { class: "adj " + a.kind },
      h("span", { class: "adj-icon", "aria-hidden": "true" }, ADJ[a.kind][0]),
      h("div", {}, h("div", { class: "adj-title" }, `${ADJ[a.kind][1]} · ${CATEGORY_LABEL[a.category]}`), h("div", { class: "small" }, a.text),
        a.saves > 0 ? h("span", { class: "badge good" }, `Saves ${money(a.saves)} a month`) : a.saves < 0 ? h("span", { class: "badge warn" }, `Costs ${money(-a.saves)} more a month`) : null))));
}

/* ---------- products & cost: fine-tune panel ---------- */
const SORTS = [
  ["routine", "Routine order"], ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"],
  ["month_asc", "Monthly cost: low to high"], ["month_desc", "Monthly cost: high to low"], ["use_asc", "Cost per use: low to high"],
];
const SORT_FN = {
  routine: null, price_asc: (a, b) => a.price_usd - b.price_usd, price_desc: (a, b) => b.price_usd - a.price_usd,
  month_asc: (a, b) => a.monthly_cost - b.monthly_cost, month_desc: (a, b) => b.monthly_cost - a.monthly_cost, use_asc: (a, b) => a.cost_per_use - b.cost_per_use,
};
const shop = { ready: false, budget: 40, store: "", sulfate_free: false, silicone_free: false, fragrance_free: false, essentials: false, sort: "routine", preview: null, stores: null, busy: false, error: "", timer: null };

function shopInit(r) {
  if (shop.ready && shop.runId === r.run_id) return;
  Object.assign(shop, { ready: true, runId: r.run_id, budget: r.costs.budget, store: "", essentials: false, sort: "routine", preview: null, error: "", busy: false,
    sulfate_free: !!state.profile.sulfate_free, silicone_free: !!state.profile.silicone_free, fragrance_free: !!state.profile.fragrance_free });
  if (!shop.stores) fetch("/api/catalog/stores").then((x) => x.json()).then((d) => { shop.stores = d.stores; if (state.tab === "products") render(); }).catch(() => {});
}
function shopIsDefault(r) {
  const p = state.profile;
  return shop.budget === r.costs.budget && !shop.store && !shop.essentials && shop.sulfate_free === !!p.sulfate_free && shop.silicone_free === !!p.silicone_free && shop.fragrance_free === !!p.fragrance_free;
}
async function shopRefresh(r) {
  if (shopIsDefault(r)) { shop.preview = null; shop.error = ""; renderShopResults(r); return; }
  shop.busy = true; shop.error = ""; renderShopResults(r);
  try {
    shop.preview = await api("/api/reprice", "POST", {
      needs: r.needs, hair_length: state.profile.hair_length, monthly_budget_usd: shop.budget, curl_pattern: state.profile.curl_pattern, porosity: state.profile.porosity,
      store: shop.store || null, sulfate_free: shop.sulfate_free, silicone_free: shop.silicone_free, fragrance_free: shop.fragrance_free, essentials_only: shop.essentials,
    });
  } catch (e) { shop.error = e.message; }
  shop.busy = false; renderShopResults(r);
}
function shopReset(r) { shop.ready = false; shopInit(r); render(); }

async function shopCommit(r) {
  const pv = shop.preview; if (!pv || !r.context) return;
  const profile = { ...state.profile, monthly_budget_usd: shop.budget, sulfate_free: shop.sulfate_free, silicone_free: shop.silicone_free, fragrance_free: shop.fragrance_free };
  if (!profile.photo_analysis) delete profile.photo_analysis;
  shop.busy = true; shop.error = ""; renderShopResults(r);
  let res = null, err = null;
  try {
    await streamPost("/api/replan", { profile, product_ids: pv.products.map((p) => p.id), science: r.context.science, schedule: r.context.schedule, weather_summary: r.context.weather_summary || "" },
      (ev) => { if (ev.event === "result") res = ev.data; if (ev.event === "error") err = ev.message; });
  } catch (e) { err = e.message; }
  if (err || !res) { shop.busy = false; shop.error = err || "Something went wrong."; renderShopResults(r); return; }
  res.costs.adjustments = pv.costs.adjustments;
  const u = r.usage;
  const merged = { agents: [...u.agents, ...res.usage.agents], total: Object.fromEntries(Object.keys(u.total).map((k) => [k, +(u.total[k] + (res.usage.total[k] || 0)).toFixed(6)])) };
  Object.assign(r, { headline: res.headline, routine: res.routine, week: res.week, products: res.products, costs: res.costs, step_categories: res.step_categories, usage: merged });
  r.hair.summary = res.routine.hair_profile_summary;
  Object.assign(state.profile, { monthly_budget_usd: shop.budget, sulfate_free: shop.sulfate_free, silicone_free: shop.silicone_free, fragrance_free: shop.fragrance_free });
  state.today = null; save(); saveToAccount();
  shop.preview = null; shop.busy = false; shop.runId = null; shopInit(r); state.notice = "Your routine was updated with these products."; render();
}

function shopControls(r) {
  const out = h("span", { class: "range-val" }, `$${shop.budget} a month`);
  const slider = h("input", { type: "range", min: 5, max: 150, step: 5, value: shop.budget, "aria-label": "Monthly budget",
    oninput: (e) => { shop.budget = Number(e.target.value); out.textContent = `$${shop.budget} a month`; clearTimeout(shop.timer); shop.timer = setTimeout(() => shopRefresh(r), 250); } });
  const tog = (label, key) => h("button", { type: "button", class: "chip", "aria-pressed": String(shop[key]), onclick: () => { shop[key] = !shop[key]; render(); shopRefresh(r); } }, label);
  const storeSel = h("select", { id: "shop-store", "aria-label": "Shop at one store", onchange: (e) => { shop.store = e.target.value; shopRefresh(r); } },
    h("option", { value: "" }, "Any store"), (shop.stores || []).map((s) => h("option", { value: s.store, selected: shop.store === s.store }, `${s.store} (${s.count} products)`)));
  const sortSel = h("select", { id: "shop-sort", "aria-label": "Sort products", onchange: (e) => { shop.sort = e.target.value; renderShopResults(r); } },
    SORTS.map(([v, l]) => h("option", { value: v, selected: shop.sort === v }, l)));
  return h("section", { class: "card", "aria-labelledby": "ft" },
    h("h2", { id: "ft" }, "Fine-tune your products"),
    h("p", { class: "muted" }, "Slide your budget, pick a single store, or filter ingredients. Products re-pick instantly from the same verified catalog."),
    h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "label" }, "Monthly budget"), out), slider,
    h("div", { class: "grid two", style: "margin-top:16px" },
      h("div", {}, h("label", { class: "label", for: "shop-store" }, "Buy from one store"), storeSel),
      h("div", {}, h("label", { class: "label", for: "shop-sort" }, "Sort products"), sortSel)),
    h("div", { style: "margin-top:14px" }, h("span", { class: "label" }, "Filters"),
      h("div", { class: "chips" }, tog("Sulfate-free", "sulfate_free"), tog("Silicone-free", "silicone_free"), tog("Fragrance-free", "fragrance_free"), tog("Essentials only", "essentials"))),
    h("p", { class: "small muted", style: "margin-top:10px" }, "Low budget: we swap to cheaper options and drop optional steps. Room to spare: we offer pricier options that fit just as well. Pricier isn't always better."));
}

function renderShopResults(r) {
  const el = document.getElementById("shop-results"); if (!el) return;
  const pv = shop.preview, shown = pv || r;
  const c = shown.costs;
  const rows = [...shown.products]; const fn = SORT_FN[shop.sort]; if (fn) rows.sort(fn);
  const hint = shown.stores_all && shown.stores_all.length && !shop.store
    ? h("p", { class: "small" }, "One-stop shop: ", shown.stores_all.map((s) => h("button", { type: "button", class: "chip", onclick: () => { shop.store = s; render(); shopRefresh(r); } }, `All at ${s}`)))
    : null;
  el.replaceChildren(...[
    shop.error ? h("div", { class: "error", role: "alert" }, shop.error) : null,
    pv ? h("div", { class: "card honey", role: "status" },
      h("b", {}, "You're previewing a different set of products."), h("p", { class: "small" }, "Your saved routine still uses your original products until you update it. Updating rewrites your steps around these products and takes about 10 seconds."),
      h("div", { class: "row" },
        h("button", { class: "btn", disabled: shop.busy || !r.context, onclick: () => shopCommit(r) }, shop.busy ? "Updating…" : "Use these in my routine"),
        h("button", { class: "btn ghost", disabled: shop.busy, onclick: () => shopReset(r) }, "Back to my original picks")),
      !r.context ? h("p", { class: "small" }, "This routine was saved before updates were possible. Build a new one to use this.") : null) : null,
    pv && pv.unavailable.length ? h("div", { class: "error" }, `Nothing in our catalog matches these filters for: ${pv.unavailable.map((k) => CATEGORY_LABEL[k].toLowerCase()).join(", ")}. Try another store or fewer filters.`) : null,
    h("section", { class: "card" }, h("div", { class: "total" },
      h("div", {}, h("div", { class: "small muted" }, "Estimated monthly cost"), h("div", { class: "big" }, money(c.monthly_total))),
      h("div", {}, h("div", { class: c.within_budget ? "ok" : "over" }, c.within_budget ? "Within your budget" : "Over your budget"),
        h("div", { class: "muted small" }, `Budget ${money(pv ? shop.budget : c.budget)} · starter kit ${money(c.upfront_total)} to buy everything once`))),
      !pv && c.budget_agent_summary ? h("p", { style: "margin-top:12px" }, c.budget_agent_summary) : null,
      adjustmentsList(c.adjustments),
      !c.within_budget ? h("p", { class: "error" }, "We couldn't get under your budget without removing essential steps. Try raising the budget a little or washing a bit less often.") : null,
      hint),
    h("div", { class: "products", "aria-busy": String(shop.busy) }, rows.map(productCard))].filter(Boolean));
}

function tabProducts(r) {
  shopInit(r);
  const holder = h("div", { id: "shop-results" });
  setTimeout(() => renderShopResults(r));
  return h("div", {},
    r.needs ? shopControls(r) : h("section", { class: "card soft" }, h("p", {}, "This routine was saved before the fine-tune tools existed. Build a new routine to unlock the budget slider, store and ingredient filters.")),
    state.notice ? h("div", { class: "ok-box", role: "status" }, (() => { const t = state.notice; state.notice = ""; return t; })()) : null,
    holder,
    h("p", { class: "small muted", style: "margin-top:14px" }, "Monthly cost = cost per use × how many times you use it each month. Prices are snapshots from US retailers and may change; check the store before buying. We earn nothing from any link."));
}

/* "2026-10-27" -> "Tues. Oct 27 (tomorrow)"; "(today)" and "(tomorrow)" only when they apply */
const WEEKDAYS = ["Sun.", "Mon.", "Tues.", "Wed.", "Thurs.", "Fri.", "Sat."];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function friendlyDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d), now = new Date();
  const diff = Math.round((date - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  const base = `${WEEKDAYS[date.getDay()]} ${MONTHS[m - 1]} ${d}`;
  return diff === 0 ? `${base} (today)` : diff === 1 ? `${base} (tomorrow)` : base;
}

/* Last wash: stored as a local date (YYYY-MM-DD). It lines up the week and counts days since the wash. */
const pad2 = (n) => String(n).padStart(2, "0");
const isoOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const startOfToday = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), n.getDate()); };
const parseDay = (iso) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
function daysSinceWash() { return state.lastWash ? Math.max(0, Math.round((startOfToday() - parseDay(state.lastWash)) / 86400000)) : null; }
function setLastWash(daysAgo) {
  const d = startOfToday(); d.setDate(d.getDate() - daysAgo);
  state.lastWash = isoOf(d); state.today = null; save(); saveToAccount();
}
/* Calendar-day arithmetic (adding milliseconds would be an hour off across a daylight-saving change). */
function nextWashDue() { const d = parseDay(state.lastWash); d.setDate(d.getDate() + state.profile.wash_every_days); return friendlyDate(isoOf(d)); }
const WASH_KINDS = ["wash_day", "deep_condition_day", "protein_day"];
/* The next 7 days, lined up so the template's first wash day falls on the person's last wash. Null if no wash is logged. */
function rollingWeek(r) {
  if (!state.lastWash) return null;
  const anchor = r.week.findIndex((d) => WASH_KINDS.includes(d.kind));
  if (anchor < 0) return null;
  const last = parseDay(state.lastWash), t0 = startOfToday(), out = [];
  for (let i = 0; i < 7; i++) {
    const date = new Date(t0); date.setDate(t0.getDate() + i);
    const off = Math.round((date - last) / 86400000);
    out.push({ ...r.week[(((anchor + off) % 7) + 7) % 7], date: isoOf(date), off });
  }
  return out;
}

function tabWeather(r) {
  const w = r.weather;
  return h("div", {}, h("section", { class: "card honey" }, h("h3", {}, w.place), h("p", {}, w.summary), w.best_wash_dates.length ? h("p", {}, h("b", {}, "Good wash days: "), w.best_wash_dates.map(friendlyDate).join(", ")) : null),
    h("div", { class: "weather-days" }, w.days.map((d, i) => {
      const a = w.advice.find((x) => x.date === d.date);
      const label = friendlyDate(d.date);
      return h("div", { class: "wday" }, h("b", {}, label), h("span", { class: "climate " + d.climate }, d.climate.replace("_", " ")),
        h("div", {}, `${d.temp_hi_f}°/${d.temp_lo_f}° · dew ${d.dew_point_f}°`), h("div", { class: "muted" }, `rain ${d.rain_chance_pct}% · wind ${d.wind_mph} mph · UV ${d.uv_index}`),
        a ? h("div", { style: "margin-top:6px" }, a.hair_tip) : null);
    })));
}

function usageTable(u) {
  const t = u.total;
  return h("table", {}, h("thead", {}, h("tr", {}, ["Agent", "Input", "Cached", "Output", "Calls", "Tools", "Time", "Est. cost"].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
    h("tbody", {}, u.agents.map((a) => h("tr", {}, h("td", {}, AGENT_LABELS[a.agent]?.[0] || a.agent), ...[a.input_tokens, a.cached_tokens, a.output_tokens, a.requests, a.tool_calls].map((n) => h("td", { class: "num" }, n.toLocaleString())), h("td", { class: "num" }, a.seconds + "s"), h("td", { class: "num" }, "$" + a.cost_usd.toFixed(4)))),
      h("tr", {}, h("td", {}, h("b", {}, "Total")), ...[t.input_tokens, t.cached_tokens, t.output_tokens, t.requests, t.tool_calls].map((n) => h("td", { class: "num" }, h("b", {}, n.toLocaleString()))), h("td", {}), h("td", { class: "num" }, h("b", {}, "$" + t.cost_usd.toFixed(4))))));
}

function costText(usd) { return usd < 0.01 ? `${(usd * 100).toFixed(1)}¢` : `$${usd.toFixed(2)}`; }
function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

function tabDetails(r) {
  const u = r.usage, t = u.total;
  const words = Math.round(((t.input_tokens + t.output_tokens) * 0.75) / 100) * 100;
  const secs = Math.round(t.wall_seconds || u.agents.reduce((n, a) => n + a.seconds, 0));
  return h("div", {},
    h("section", { class: "card" }, h("h2", {}, "How your routine was made"),
      h("p", { class: "muted" }, "Instead of one big program, a team of AI helpers each handled one job, and plain code double-checked their work. Here's what it took."),
      h("div", { class: "result-grid" },
        h("div", { class: "stat" }, h("small", {}, "AI helpers"), h("b", {}, String(u.agents.length))),
        h("div", { class: "stat" }, h("small", {}, "Time"), h("b", {}, `${secs} seconds`)),
        h("div", { class: "stat" }, h("small", {}, "Cost to make this"), h("b", {}, costText(t.cost_usd)), t.cost_usd < 0.01 ? h("small", {}, "less than a penny") : null),
        h("div", { class: "stat" }, h("small", {}, "Looked things up"), h("b", {}, plural(t.tool_calls, "time", "times")), h("small", {}, "catalog and forecast"))),
      h("p", { class: "small muted" }, `Together they read and wrote roughly ${words.toLocaleString()} words. At this price, 1,000 routines would cost about ${money(t.cost_usd * 1000)}.`)),
    h("section", { class: "card" }, h("h3", {}, "Who did what"),
      h("div", { class: "agents" }, u.agents.map((a) => h("div", { class: "agent done" },
        h("div", { class: "dot", "aria-hidden": "true" }, "✓"),
        h("div", {}, h("b", {}, AGENT_LABELS[a.agent]?.[0] || a.agent), h("small", {}, AGENT_LABELS[a.agent]?.[1] || "")),
        h("div", { class: "small muted" }, "done"))))),
    h("section", { class: "card" }, h("h3", {}, "How we keep it trustworthy"), h("ul", {}, [
      "Every product comes from a verified US catalog. Anything the AI makes up is thrown out.",
      "Prices, cost per use and your monthly total are calculated from real catalog prices, not written by the AI.",
      "If the plan runs over your budget, we swap to cheaper options or drop optional steps.",
      "Your notes are treated as information about you, never as instructions.",
      "Your photo is looked at once and never saved."].map((x) => h("li", {}, x)))),
    h("details", { class: "card tech" }, h("summary", {}, "Technical details"),
      usageTable(u),
      h("p", { class: "small muted", style: "margin-top:10px" }, `Run ${r.run_id}. Model: gpt-6-luna. Input counts include cached tokens. Cost is an estimate at list prices ($0.10 input, $0.01 cached input, $0.50 output per million tokens).`)));
}

function tabToday(r) {
  const since = daysSinceWash();
  let touched = false;
  const daysInput = h("input", { type: "number", min: "0", max: "60", id: "dsw", value: since === null ? state.profile.wash_every_days : since, "aria-label": "Days since your last wash", oninput: () => { touched = true; } });
  const minInput = h("input", { type: "number", min: "0", max: "240", id: "mt", value: state.profile.minutes_per_day, "aria-label": "Minutes available today" });
  const out = h("div", { id: "today-out" });
  if (state.today) renderToday(out, state.today, r);
  const go_ = h("button", { class: "btn honey", onclick: async () => {
    setLastWash(Math.max(0, Math.min(60, Number(daysInput.value || 0)))); touched = false;  // whatever is in the box (typed or the starting guess) lines up This week, so both tabs agree
    go_.disabled = true; out.replaceChildren(h("p", { class: "muted", role: "status" }, "Checking your forecast and your routine…"));
    let res = null, err = null;
    try {
      await streamPost("/api/today", { zip_code: state.profile.zip_code, days_since_wash: Number(daysInput.value || 0), wash_every_days: state.profile.wash_every_days, minutes_today: Number(minInput.value || 0), routine: r.routine },
        (ev) => { if (ev.event === "result") res = ev.data; if (ev.event === "error") err = ev.message; });
    } catch (e) { err = e.message; }
    go_.disabled = false;
    if (err || !res) { out.replaceChildren(h("div", { class: "error", role: "alert" }, err || "Something went wrong.")); return; }
    state.today = res; renderToday(out, res, r);
  } }, "What should I do today?");
  const washed = h("button", { class: "btn ghost", onclick: () => { setLastWash(0); render(); } }, "I washed my hair today");
  const next = state.lastWash ? nextWashDue() : null;
  return h("div", {},
    h("section", { class: "card" }, h("h2", {}, "Today"), h("p", { class: "muted" }, "Your routine is saved. Each day we re-check the weather and tell you what your hair needs today."),
      h("div", { class: "grid two" },
        h("div", {}, h("label", { class: "label", for: "dsw" }, "Days since your last wash"), daysInput),
        h("div", {}, h("label", { class: "label", for: "mt" }, "Minutes you have today"), minInput)),
      h("div", { class: "row", style: "margin-top:16px" }, go_, washed),
      since === null ? h("p", { class: "small muted", style: "margin-top:10px" }, `We started with your usual wash schedule (${state.profile.wash_every_days} days). Change the number if it's been a different amount of time.`) : null,
      h("p", { class: "small muted", style: "margin-top:10px" }, "Just washed? Tap \u201cI washed my hair today\u201d. We'll count days from today and line up the This week tab with it. If it was earlier, type how many days ago above."),
      state.lastWash ? h("div", { class: "ok-box", role: "status" }, `Last wash: ${friendlyDate(state.lastWash)}. Next wash due: ${next}. `, h("button", { class: "link", type: "button", onclick: () => { state.tab = "week"; render(); } }, "See This week →")) : null),
    out);
}

function renderToday(out, data, r) {
  const p = data.plan, w = data.weather_today;
  const lookup = (id) => data.products[id] ? `${data.products[id].brand} ${data.products[id].name}` : null;
  out.replaceChildren(h("section", { class: "card soft" },
    h("span", { class: "kind " + ({ wash_day: "wash_day", refresh: "refresh_day", rest: "rest_day", protective_care: "deep_condition_day" }[p.action]) }, { wash_day: "Wash day", refresh: "Refresh", rest: "Rest", protective_care: "Protect" }[p.action]),
    h("h2", { style: "margin-top:10px" }, p.headline),
    w ? h("p", {}, h("b", {}, data.place + ": "), `${w.temp_hi_f}° high, dew point ${w.dew_point_f}°, ${w.climate.replace("_", " ")}. `, p.weather_note) : h("p", {}, p.weather_note),
    stepList(p.steps, lookup), h("p", { class: "muted", style: "margin-top:10px" }, "Tip: " + p.tip)));
}

/* ---------- start ---------- */
api("/api/auth/me", "GET").then(async (me) => {
  if (!me.user) return;
  setUser(me.user); await syncAfterAuth();
  if (me.password_update_required) { state.authMsg = "Your password no longer meets our rules. Please choose a new one."; state.step = "account"; }
  render();
}).catch(() => {});
fetch("/api/status").then((r) => r.json()).then((s) => { document.getElementById("pause-banner").hidden = !s.paused; }).catch(() => {});
render();
