"use strict";
/* Bedrock audit UI. All data is rendered with textContent / DOM calls (never innerHTML). */

const $ = (sel) => document.querySelector(sel);
const LABEL = {
  RETRACTED: "Retracted",
  CITES_RETRACTED: "Cites a retracted work",
  TWO_HOP: "Two hops from a retracted work",
  NO_EXPOSURE_FOUND: "No exposure found",
  NOT_IN_CORPUS: "Not in corpus",
};
const KIND = { REMOVE_OR_REPLACE: "Remove or replace", SUGGEST_ALTERNATIVE: "Suggested alternative", REVIEW: "Manual review" };
const SVGNS = "http://www.w3.org/2000/svg";

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
function sv(tag, attrs = {}, text) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/* One horizontal chain of boxes joined by arrows: [{doi, caption, ret}] */
function pathSvg(nodes, description) {
  const W = 200, H = 50, GAP = 44, PAD = 6;
  const width = PAD * 2 + nodes.length * W + (nodes.length - 1) * GAP;
  const svg = sv("svg", { class: "path", viewBox: `0 0 ${width} ${H + PAD * 2}`, width, height: H + PAD * 2,
    role: "img", "aria-label": description });
  nodes.forEach((n, i) => {
    const x = PAD + i * (W + GAP), y = PAD;
    const g = sv("g");
    g.append(sv("title", {}, n.doi));
    g.append(sv("rect", { x, y, width: W, height: H, rx: 6, class: n.ret ? "ret" : "" }));
    g.append(sv("text", { x: x + 8, y: y + 18, class: "cap" }, n.caption));
    g.append(sv("text", { x: x + 8, y: y + 36 }, short(n.doi, 29)));
    svg.append(g);
    if (i < nodes.length - 1) {
      const x1 = x + W + 4, x2 = x + W + GAP - 6, ym = y + H / 2;
      svg.append(sv("line", { x1, y1: ym, x2, y2: ym, "stroke-width": 1.5 }));
      svg.append(sv("polygon", { points: `${x2},${ym - 4} ${x2 + 7},${ym} ${x2},${ym + 4}` }));
    }
  });
  return svg;
}

function facts(...parts) {
  const f = el("p", { class: "facts" });
  parts.filter(Boolean).forEach((p) => f.append(el("span", { text: p })));
  return f;
}

function renderItem(it) {
  const a = el("article", { class: "item", "data-status": it.status });
  a.append(el("div", { class: "head" }, el("span", { class: "badge", text: LABEL[it.status] }), el("span", { class: "doi", text: it.doi })));
  const cov = it.coverage ? `Checked ${it.coverage.refs_indexed} of ${it.coverage.refs_total ?? "?"} references` : null;
  const venue = it.venue && it.venue.name ? `${it.venue.name} (${it.venue.retractions_recorded} retractions recorded in this venue)` : null;
  if (it.status === "NOT_IN_CORPUS") {
    a.append(facts("This DOI is not in the indexed corpus, so nothing can be said about it."));
  } else if (it.status === "NO_EXPOSURE_FOUND") {
    a.append(facts("No retracted work found within 2 hops in the corpus. This is not a certification.", cov, venue));
  } else if (it.status === "RETRACTED") {
    const r = it.retraction;
    a.append(facts(`Retracted ${r.date}`, `cited by ${r.indexed_papers_citing_it} indexed papers`, venue));
    if (r.reasons.length) {
      const ul = el("ul", { class: "reasons", "aria-label": "Recorded reasons" });
      r.reasons.forEach((x) => ul.append(el("li", { text: x })));
      a.append(ul);
    }
    a.append(pathSvg([{ doi: it.doi, caption: `Retracted ${r.date}`, ret: true }], `${it.doi} was retracted on ${r.date}`));
  } else if (it.status === "CITES_RETRACTED") {
    a.append(facts(cov, venue));
    it.direct.slice(0, 5).forEach((d) => a.append(pathSvg(
      [{ doi: it.doi, caption: "Your cited work" }, { doi: d.doi || d.id, caption: `Retracted ${d.retracted_at}`, ret: true }],
      `${it.doi} cites ${d.doi || d.id}, retracted on ${d.retracted_at}`)));
    if (it.direct.length > 5) a.append(facts(`${it.direct.length - 5} more retracted works cited directly`));
  } else if (it.status === "TWO_HOP") {
    a.append(facts(cov, venue, `${it.two_hop_total} path${it.two_hop_total === 1 ? "" : "s"} found`));
    it.two_hop.forEach((t) => a.append(pathSvg(
      [{ doi: it.doi, caption: "Your cited work" }, { doi: t.via.doi || t.via.id, caption: "Cites" },
       { doi: t.retracted.doi || t.retracted.id, caption: `Retracted ${t.retracted.retracted_at}`, ret: true }],
      `${it.doi} cites ${t.via.doi || t.via.id}, which cites ${t.retracted.doi || t.retracted.id}, retracted on ${t.retracted.retracted_at}`)));
    if (it.two_hop_total > it.two_hop.length) a.append(facts(`${it.two_hop_total - it.two_hop.length} more paths not shown`));
  }
  return a;
}

let lastText = "";
let proposals = [];

function setBusy(btn, busy, statusEl, msg) {
  btn.disabled = busy;
  statusEl.className = "";
  statusEl.textContent = msg || "";
}
function showError(statusEl, msg) { statusEl.className = "error"; statusEl.textContent = msg; }

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}

function render(data) {
  const { audit } = data;
  proposals = data.proposals;
  const s = audit.summary;
  const chips = $("#summary");
  chips.replaceChildren();
  [["Checked", s.input], ["Retracted", s.RETRACTED], ["Cite retracted", s.CITES_RETRACTED], ["Two hops", s.TWO_HOP],
   ["No exposure found", s.NO_EXPOSURE_FOUND], ["Not in corpus", s.NOT_IN_CORPUS]]
    .forEach(([k, v]) => chips.append(el("li", { text: `${k}: ${v}` })));
  $("#notice").textContent = audit.caveats[0] + " " + audit.caveats[1];
  $("#items").replaceChildren(...audit.items.map(renderItem));

  const list = $("#proposals");
  list.replaceChildren();
  proposals.forEach((p, i) => {
    const id = `prop-${i}`;
    list.append(el("li", {}, el("input", { type: "checkbox", id, "data-id": p.id }),
      el("label", { for: id }, el("span", { class: "kind", text: KIND[p.kind] }), p.text)));
  });
  $("#approve-card").hidden = proposals.length === 0;
  $("#applied").hidden = true;
  $("#apply-status").textContent = "";
  $("#empty").hidden = true;
  $("#results").hidden = false;
  const h = $("#res-h");
  h.setAttribute("tabindex", "-1");
  h.focus({ preventScroll: true });
  h.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

$("#audit-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#refs").value.trim();
  const btn = $("#run"), st = $("#status");
  if (!text) { showError(st, "Paste some DOIs first, or try the example."); $("#refs").focus(); return; }
  setBusy(btn, true, st, "Checking…");
  try {
    const data = await post("/api/audit", { text });
    lastText = text;
    render(data);
    setBusy(btn, false, st, `Checked ${data.audit.summary.input} DOIs`);
  } catch (e) {
    setBusy(btn, false, st, "");
    showError(st, e.message);
  }
});

$("#refs").addEventListener("keydown", (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") $("#audit-form").requestSubmit();
});

async function loadExample() {
  const st = $("#status");
  try {
    const ex = (await (await fetch("/examples.json")).json()).examples[0];
    $("#refs").value = ex.text;
    $("#audit-form").requestSubmit();
  } catch { showError(st, "Could not load the example."); }
}
$("#example").addEventListener("click", loadExample);
$("#example2").addEventListener("click", loadExample);

$("#all").addEventListener("click", () => {
  document.querySelectorAll("#proposals input").forEach((c) => { c.checked = true; });
});

$("#apply").addEventListener("click", async () => {
  const st = $("#apply-status"), btn = $("#apply");
  const approved = [...document.querySelectorAll("#proposals input:checked")].map((c) => c.dataset.id);
  if (!approved.length) { showError(st, "Nothing approved yet. Tick at least one action."); return; }
  setBusy(btn, true, st, "Applying…");
  try {
    const out = await post("/api/apply", { text: lastText, approved });
    $("#revised").value = out.revised_dois.join("\n");
    const blob = new Blob([out.report_markdown], { type: "text/markdown" });
    const a = $("#download");
    if (a.dataset.url) URL.revokeObjectURL(a.dataset.url);
    a.href = URL.createObjectURL(blob);
    a.dataset.url = a.href;
    $("#applied").hidden = false;
    setBusy(btn, false, st, `Applied ${out.applied.length} action${out.applied.length === 1 ? "" : "s"}`);
  } catch (e) {
    setBusy(btn, false, st, "");
    showError(st, e.message);
  }
});

$("#copy").addEventListener("click", async () => {
  const b = $("#copy");
  try {
    await navigator.clipboard.writeText($("#revised").value);
    b.textContent = "Copied ✓";
  } catch {
    $("#revised").select();
    b.textContent = "Press Ctrl/⌘+C";
  }
  setTimeout(() => { b.textContent = "Copy list"; }, 1600);
});

(async function health() {
  const c = $("#corpus");
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    const when = d.retraction_snapshot_downloaded_utc ? `; Retraction Watch snapshot downloaded ${d.retraction_snapshot_downloaded_utc.slice(0, 10)}` : "";
    c.textContent = `${d.papers_indexed.toLocaleString()} papers and ${d.retracted_works.toLocaleString()} retracted works${when}.`;
  } catch (e) {
    c.textContent = e.message || "the graph database is not reachable.";
  }
})();
