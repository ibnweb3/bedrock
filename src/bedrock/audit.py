"""Citation-provenance audit: which retracted works does a bibliography stand on, and by what path?

Every graph question is a Cypher query in queries/audit/ executed by FalkorDB. This module only
parses input, calls those queries, and assembles the answer. It makes exact statements about the
indexed corpus; it does NOT predict retraction (the backtest in docs/RESULTS.md found no reliable
predictive lift) and "clean" never means "safe" - it means nothing was found within 2 hops in the corpus.

Statuses (strongest first):
  RETRACTED         the cited work itself is retracted (Retraction Watch)
  CITES_RETRACTED   the cited work cites a retracted work (1 hop)
  TWO_HOP           the cited work cites a work that cites a retracted work (2 hops)
  NO_EXPOSURE_FOUND in the corpus; no retracted work found within 2 hops
  NOT_IN_CORPUS     the DOI is unknown to this graph, so nothing can be said
"""
from __future__ import annotations

import re
from collections import defaultdict

from .graph import read_query
from .openalex import norm_doi

MAX_INPUT_DOIS = 300
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>*]+", re.IGNORECASE)  # * ends a DOI (Markdown bold)
_TRAIL = ".,;:)]}>'\"*_"

RETRACTED, DIRECT, TWO_HOP, CLEAN, UNKNOWN = (
    "RETRACTED", "CITES_RETRACTED", "TWO_HOP", "NO_EXPOSURE_FOUND", "NOT_IN_CORPUS",
)


def extract_dois(text: str) -> list[str]:
    """DOIs from free text or a list, normalised, de-duplicated, order preserved."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _DOI_RE.findall(text or ""):
        d = norm_doi(m.rstrip(_TRAIL))
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def fmt_date(v: int | None) -> str | None:
    return None if not v else f"{v // 10000:04d}-{v // 100 % 100:02d}-{v % 100:02d}"


def _cypher(name: str) -> str:
    return "\n".join(l for l in read_query(f"audit/{name}.cypher").splitlines() if not l.strip().startswith("//"))


class Auditor:
    def __init__(self, graph, *, timeout: int = 60_000):
        self.g, self.timeout = graph, timeout

    def _run(self, name: str, params: dict):
        return self.g.ro_query(_cypher(name), params, timeout=self.timeout).result_set

    def audit(self, dois: list[str], *, max_two_hop: int = 5, max_alternatives: int = 3) -> dict:
        dois = [d for d in dict.fromkeys(norm_doi(x) for x in dois) if d][:MAX_INPUT_DOIS]
        rows = self._run("10_resolve", {"dois": dois})
        info: dict[str, dict] = {}
        for d, pid, pub, ret_at, reasons, ref_total, vid, vname, vstrat in rows:
            info[d] = None if pid is None else {
                "id": pid, "pub_date": fmt_date(pub), "retracted_at": ret_at,
                "reasons": list(reasons or []), "ref_total": ref_total,
                "venue": {"id": vid, "name": vname, "stratum": vstrat},
            }
        ids = [v["id"] for v in info.values() if v]
        indexed = {i: n for i, n in self._run("20_indexed_refs", {"ids": ids})} if ids else {}
        direct, two = defaultdict(list), defaultdict(list)
        if ids:
            for i, rid, rdoi, rat, reasons in self._run("21_direct", {"ids": ids}):
                direct[i].append({"id": rid, "doi": rdoi, "retracted_at": fmt_date(rat), "reasons": list(reasons or [])})
            for i, xid, xdoi, rid, rdoi, rat, reasons in self._run("22_two_hop", {"ids": ids, "limit": 5000}):
                two[i].append({"via": {"id": xid, "doi": xdoi},
                               "retracted": {"id": rid, "doi": rdoi, "retracted_at": fmt_date(rat), "reasons": list(reasons or [])}})
        # Deterministic order (the database returns ties in arbitrary order): the same input must give the same output.
        for lst in direct.values():
            lst.sort(key=lambda d: (d["retracted_at"] or "", d["doi"] or d["id"]))
        for lst in two.values():
            lst.sort(key=lambda t: (t["via"]["doi"] or t["via"]["id"], t["retracted"]["doi"] or t["retracted"]["id"]))
        retracted_ids = [v["id"] for v in info.values() if v and v["retracted_at"]]
        citers = {i: n for i, n in self._run("30_citers", {"ids": retracted_ids})} if retracted_ids else {}
        vids = sorted({v["venue"]["id"] for v in info.values() if v and v["venue"]["id"]})
        vret = {v: n for v, n in self._run("40_venue_retractions", {"vids": vids})} if vids else {}

        items = []
        for d in dois:
            p = info.get(d)
            if p is None:
                items.append({"doi": d, "status": UNKNOWN})
                continue
            status = RETRACTED if p["retracted_at"] else DIRECT if direct[p["id"]] else TWO_HOP if two[p["id"]] else CLEAN
            item = {
                "doi": d, "status": status, "id": p["id"], "published": p["pub_date"],
                "venue": {"id": p["venue"]["id"], "name": p["venue"]["name"],
                          "retractions_recorded": vret.get(p["venue"]["id"], 0) if p["venue"]["id"] else None},
                "coverage": {"refs_indexed": indexed.get(p["id"], 0), "refs_total": p["ref_total"]},
            }
            if status == RETRACTED:
                item["retraction"] = {"date": fmt_date(p["retracted_at"]), "reasons": p["reasons"],
                                      "indexed_papers_citing_it": citers.get(p["id"], 0)}
                item["alternatives"] = [
                    {"id": a, "doi": ad, "published": fmt_date(ap), "co_cited_by": co}
                    for a, ad, ap, co in self._run("31_alternatives", {"rid": p["id"], "limit": max_alternatives})
                ]
            if direct[p["id"]]:
                item["direct"] = direct[p["id"]]
            if two[p["id"]]:
                item["two_hop_total"] = len(two[p["id"]])
                item["two_hop"] = two[p["id"]][:max_two_hop]
            items.append(item)

        order = {RETRACTED: 0, DIRECT: 1, TWO_HOP: 2, CLEAN: 3, UNKNOWN: 4}
        items.sort(key=lambda it: order[it["status"]])
        counts = {s: sum(1 for it in items if it["status"] == s) for s in order}
        return {"summary": {"input": len(dois), **counts}, "items": items,
                "caveats": [
                    "Findings are exact for the indexed corpus only; they do not predict retraction.",
                    "A work with NO_EXPOSURE_FOUND is not certified clean: only references indexed in the graph "
                    "(see coverage) and only up to 2 hops were checked.",
                    "Retraction data: Retraction Watch via Crossref (snapshot in data/raw/retraction_watch.meta.json); "
                    "citations: OpenAlex.",
                ]}


def build_proposals(result: dict) -> list[dict]:
    """Actions the agent proposes. Nothing is applied until a person approves each one."""
    props: list[dict] = []
    for it in result["items"]:
        if it["status"] == RETRACTED:
            props.append({"id": f"remove:{it['doi']}", "kind": "REMOVE_OR_REPLACE", "doi": it["doi"],
                          "text": f"Remove {it['doi']} from the bibliography or replace it: it was retracted on "
                                  f"{it['retraction']['date']}."})
            for alt in it.get("alternatives", []):
                props.append({"id": f"alt:{it['doi']}:{alt['doi']}", "kind": "SUGGEST_ALTERNATIVE", "doi": alt["doi"],
                              "replaces": it["doi"],
                              "text": f"Consider {alt['doi']} instead (co-cited with it by {alt['co_cited_by']} indexed papers; "
                                      f"topical fit not verified)."})
        elif it["status"] in (DIRECT, TWO_HOP):
            props.append({"id": f"review:{it['doi']}", "kind": "REVIEW", "doi": it["doi"],
                          "text": f"Review {it['doi']}: it depends on retracted work "
                                  f"({'directly' if it['status'] == DIRECT else 'via one intermediate paper'}). "
                                  f"This is a prompt for manual review, not a finding that the paper is wrong."})
    return props


def apply_approved(result: dict, proposals: list[dict], approved: set[str]) -> dict:
    """Apply only approved proposals: returns the revised DOI list and a markdown audit report."""
    by_id = {p["id"]: p for p in proposals}
    chosen = [by_id[i] for i in approved if i in by_id]
    removed = {p["doi"] for p in chosen if p["kind"] == "REMOVE_OR_REPLACE"}
    added = [p["doi"] for p in chosen if p["kind"] == "SUGGEST_ALTERNATIVE"]
    revised = [it["doi"] for it in result["items"] if it["doi"] not in removed] + [d for d in added if d not in removed]
    revised = list(dict.fromkeys(revised))
    s = result["summary"]
    lines = ["# Bibliography provenance audit", "",
             f"Checked {s['input']} DOIs: {s[RETRACTED]} retracted, {s[DIRECT]} cite a retracted work, "
             f"{s[TWO_HOP]} two-hop exposure, {s[CLEAN]} no exposure found, {s[UNKNOWN]} not in corpus.", ""]
    for it in result["items"]:
        if it["status"] in (UNKNOWN, CLEAN):
            continue
        lines.append(f"## {it['doi']} - {it['status']}")
        if "retraction" in it:
            lines.append(f"- Retracted {it['retraction']['date']}; reasons: {', '.join(it['retraction']['reasons']) or 'not recorded'}.")
        for d in it.get("direct", []):
            lines.append(f"- cites retracted work {d['doi'] or d['id']} (retracted {d['retracted_at']}).")
        for t in it.get("two_hop", []):
            lines.append(f"- via {t['via']['doi'] or t['via']['id']} -> retracted {t['retracted']['doi'] or t['retracted']['id']} "
                         f"({t['retracted']['retracted_at']}).")
        lines.append("")
    lines += ["## Approved actions", ""] + ([f"- {p['text']}" for p in chosen] or ["- none approved"]) + [""]
    lines += ["## Caveats", ""] + [f"- {c}" for c in result["caveats"]]
    return {"revised_dois": revised, "report_markdown": "\n".join(lines), "applied": [p["id"] for p in chosen]}
