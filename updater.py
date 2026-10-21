"""Searches the web with Claude and writes exams.json for the tracker page."""
import datetime
import json
import os
import re
import sys

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
TODAY = datetime.date.today().isoformat()

PROFILE = (
    "BBA/BCom/BA graduate, currently in MBA 3rd semester, under 22 years old, "
    "OBC category, from Tamil Nadu."
)

TOPICS = [
    "UPSC exams (Civil Services, ESE, CAPF, CMS, IES/ISS, Geo-Scientist)",
    "SSC exams (CGL, CHSL, MTS, GD Constable, CPO, JE, Stenographer)",
    "Banking exams (IBPS PO, Clerk, SO, RRB; SBI PO, Clerk; RBI)",
    "Railway RRB exams (NTPC, Group D, JE, ALP, Technician)",
    "Defence exams (NDA, CDS, AFCAT, Agniveer, CAPF recruitment)",
    "Tamil Nadu exams (TNPSC Group 1, 2, 2A, 4; TNUSRB SI and constable; TRB; TN MRB)",
]

FIELDS = """Each item must be a JSON object with exactly these keys (all strings except source_urls):
name, body, category ("Central" or "Tamil Nadu"), apply_start, apply_end,
apply_start_iso (YYYY-MM-DD or ""), apply_end_iso (YYYY-MM-DD or ""), other_dates, exam_date,
about, eligibility, fee, syllabus, selection_rounds, salary, official_link,
fit ("good", "possible" or "not_suitable"), fit_reason, source_urls (array of URLs)."""


def build_prompt(topic):
    return f"""Today is {TODAY}. Search the web for current official information about: {topic}.

Include an exam only if its application is open now, opens within the next 6 months, or closed within the last 45 days.
Prefer official sites (upsc.gov.in, ssc.gov.in, ibps.in, rrbapply.gov.in, tnpsc.gov.in, tnusrb.tn.gov.in) and confirm dates against them.
Never invent a date or fee. If something is unknown, write "Not announced".
Salary: give starting basic pay and pay level.
For the fit fields, judge against this candidate: {PROFILE}
Rate "good" if they clearly qualify and the job suits a graduate, "possible" if they qualify but the job is below their qualification or physically demanding, "not_suitable" if they do not qualify. Explain in one or two sentences in fit_reason.

{FIELDS}

Reply with only a JSON array. No markdown fences, no commentary."""


def ask(client, topic):
    messages = [{"role": "user", "content": build_prompt(topic)}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]
    for _ in range(6):  # continue if the server pauses a long turn
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, messages=messages, tools=tools
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        text = "".join(b.text for b in resp.content if b.type == "text")
        return parse_json(text)
    return []


def parse_json(text):
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("name")]


def clean(item):
    keys = [
        "name", "body", "category", "apply_start", "apply_end", "apply_start_iso",
        "apply_end_iso", "other_dates", "exam_date", "about", "eligibility", "fee",
        "syllabus", "selection_rounds", "salary", "official_link", "fit", "fit_reason",
    ]
    out = {k: str(item.get(k, "") or "") for k in keys}
    out["source_urls"] = [u for u in item.get("source_urls", []) if isinstance(u, str)][:4]
    if out["fit"] not in ("good", "possible", "not_suitable"):
        out["fit"] = "possible"
    if not out["official_link"].startswith(("http://", "https://")):
        out["official_link"] = ""
    return out


def main():
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    found = {}
    for topic in TOPICS:
        try:
            for item in ask(client, topic):
                found[item["name"].strip().lower()] = clean(item)
            print(f"ok: {topic}")
        except Exception as e:  # keep going; one failing topic should not lose the rest
            print(f"failed: {topic}: {e}", file=sys.stderr)
    if not found:
        print("No exams found; keeping the old exams.json", file=sys.stderr)
        sys.exit(1)
    with open("exams.json", "w", encoding="utf-8") as f:
        json.dump(
            {"updated": TODAY, "profile": PROFILE, "exams": list(found.values())},
            f, ensure_ascii=False, indent=1,
        )
    print(f"Wrote {len(found)} exams")


if __name__ == "__main__":
    main()
