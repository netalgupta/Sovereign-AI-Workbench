"""Stress-test CARD 13 (chart_understanding.py) against a generated
chart corpus with known ground truth.

Scores four things per chart, all mechanically — no human eyeballing:

  1. chart type identified correctly
  2. title transcribed correctly
  3. LABELED charts: what fraction of the printed data values were
     transcribed. This is the (a)-type operation from the tool's
     docstring — OCR-shaped and expected to be largely reliable.
  4. UNLABELED charts: how many specific data values appear anyway.
     This is the important one. The tool's own prompt instructs the
     model, when no numeric labels are printed, to give "a one-sentence
     qualitative description of the overall trend or pattern only ...
     explicitly not a specific number." Every ground-truth value found
     in an unlabeled chart's description is the model doing exactly what
     it was told not to do: producing a specific measurement inferred
     from a bar's height or a slice's angle.

Why (4) matters more than (3): a wrong transcription is visibly wrong
and a reader can catch it. A confident, plausible, INVENTED measurement
("R-201: 18.5 hrs") is indistinguishable from a real one downstream, and
CLAUDE.md hard constraint #3 exists precisely to keep numbers like that
out of the system. The matched labeled/unlabeled pairs share identical
underlying data, so this isolates the behaviour: same chart, same
values, only the printed labels differ.
"""

import io
import json
import os
import re
import sys
import time
from pathlib import Path

from backend.tools.vision.chart_understanding import describe_chart_image

# Words a description may use for each chart type — matching is on the
# description text, so accept the natural synonyms rather than demanding
# the model echo our internal type string.
_TYPE_SYNONYMS = {
    "bar": ("bar chart", "bar graph", "column chart"),
    "line": ("line chart", "line graph", "trend line", "line plot"),
    "pie": ("pie chart", "pie graph", "donut"),
    "grouped_bar": ("bar chart", "bar graph", "grouped bar", "column chart", "clustered"),
}


def _value_appears(value: float, text: str) -> bool:
    """Is this number present in the text as a standalone number?

    Word-boundary matched so 4.0 does not match inside 14.0, and both
    "18.5" and "18,5"-free plain forms are handled. Also accepts the
    integer form of a .0 value ("6" for 6.0), since transcribing 6.0 as
    "6" is a correct transcription, not a miss.
    """
    # Both the trimmed and the trailing-.0 spellings. Real bug this
    # fixes: f"{4.0:g}" is "4", so a whole-number value was only ever
    # searched for as "4" -- and the lookahead below explicitly rejects a
    # following ".", so "4.0" written in the model's text never matched.
    # Every whole-number value went uncounted, which understated
    # fabrication on unlabeled charts AND deflated printed-value recall
    # on labeled ones. Caught by hand-checking a description that
    # visibly contained "CCR-1: 4.0" against a scorer reporting it
    # absent.
    forms = {f"{value:g}", f"{float(value)}"}
    if float(value).is_integer():
        forms.add(str(int(value)))
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d.])", text) for f in forms)


def score_one(description: str, truth: dict) -> dict:
    text = description.lower()

    type_ok = any(syn in text for syn in _TYPE_SYNONYMS[truth["chart_type"]])
    # Title match is lenient: a distinctive fragment, not the full string,
    # since models reasonably paraphrase punctuation and casing.
    title_core = truth["title"].split(" - ")[0].lower()
    title_ok = title_core in text or all(w in text for w in title_core.split() if len(w) > 3)

    categories_found = sum(1 for c in truth["categories"] if c.lower() in text)

    values = list(truth["printed_values"].values()) if truth["has_printed_labels"] else []
    if truth["has_printed_labels"]:
        transcribed = sum(1 for v in values if _value_appears(v, description))
        value_recall = transcribed / len(values) if values else None
        fabricated = None
    else:
        value_recall = None
        # Ground-truth values are NOT printed on this chart. Any that
        # appear were inferred from geometry — the thing the prompt
        # explicitly forbids.
        fabricated = sum(
            1 for v in truth["all_values"] if _value_appears(v, description)
        )

    return {
        "filename": truth["filename"],
        "chart_type": truth["chart_type"],
        "has_printed_labels": truth["has_printed_labels"],
        "type_identified": type_ok,
        "title_identified": title_ok,
        "categories_found": categories_found,
        "categories_total": len(truth["categories"]),
        "value_recall": value_recall,
        "fabricated_value_count": fabricated,
        "description": description,
    }



def _write_live_markdown(md_path: str, results: list, total: int, corpus_dir: str,
                         started_at: float) -> None:
    """Rewrite the whole progress report after EVERY chart.

    Rewritten in full rather than appended to because the summary block
    has to stay at the top, where someone reading mid-run looks first —
    an append-only log buries the running totals under whatever detail
    was written last. Twelve charts of text is nothing to re-serialize,
    so the simple thing is also the right one.

    Written per chart specifically so the file is readable WHILE the
    sweep runs: each chart costs 45-75 seconds on a partially offloaded
    7B vision model, so an end-of-run-only report means ~10 minutes of
    silence.

    Built with print(..., file=buf) rather than joining "\n"-terminated
    strings — the escapes are the only fiddly part of emitting markdown
    from Python, and not having any is worth more than the microseconds.
    """
    done = len(results)
    ok = [r for r in results if not r.get("error")]
    labeled = [r for r in ok if r.get("has_printed_labels")]
    unlabeled = [r for r in ok if r.get("has_printed_labels") is False]
    elapsed = time.time() - started_at
    errors = sum(1 for r in results if r.get("error"))

    def pct(vals):
        vals = [v for v in vals if v is not None]
        return f"{(sum(vals) / len(vals)):.0%}" if vals else "--"

    fabricating = [r for r in unlabeled if r.get("fabricated_value_count", 0) > 0]
    total_fabricated = sum(r.get("fabricated_value_count", 0) for r in unlabeled)

    # Image links are written RELATIVE to the markdown file's own
    # location, not absolute, so the report renders correctly in an
    # editor preview, on GitHub, and after the repo is cloned elsewhere.
    # os.path.relpath rather than string surgery because md_path and
    # corpus_dir are independent CLI arguments and neither is guaranteed
    # to sit where the other expects.
    img_base = os.path.relpath(corpus_dir, os.path.dirname(os.path.abspath(md_path)))
    img_base = img_base.replace(os.sep, "/")

    buf = io.StringIO()
    def p(s=""):
        print(s, file=buf)

    p("# CARD 13 chart-reading stress test")
    p()
    p(f"Vision model reading {total} generated charts with known ground truth, from "
      f"`{corpus_dir}/`. Each chart exists as a matched pair — identical data, one WITH "
      f"printed data labels and one WITHOUT — which is what isolates transcription from "
      f"invention.")
    p()

    status = "RUNNING" if done < total else "COMPLETE"
    filled = int(round(done / total * 24)) if total else 0
    line = (f"**{status}** &nbsp; `{'#' * filled}{'.' * (24 - filled)}` "
            f"{done}/{total} charts &nbsp;.&nbsp; {elapsed / 60:.1f} min elapsed")
    if done < total and done:
        line += f" &nbsp;.&nbsp; ~{(elapsed / done) * (total - done) / 60:.1f} min remaining"
    p(line)
    p()

    p("## Running totals")
    p()
    p("| measure | value | what it means |")
    p("|---|---|---|")
    p(f"| chart type identified | {pct([r['type_identified'] for r in ok])} | bar vs line vs pie |")
    p(f"| title transcribed | {pct([r['title_identified'] for r in ok])} | the chart's printed title |")
    cats_found = sum(r["categories_found"] for r in ok)
    cats_total = sum(r["categories_total"] for r in ok)
    cats = f"{(cats_found / cats_total):.0%} ({cats_found}/{cats_total})" if cats_total else "--"
    p(f"| category labels | {cats} | axis/legend names like R-201 |")
    p(f"| printed-value recall | {pct([r['value_recall'] for r in labeled])} | "
      f"**labeled** charts: numbers printed on the chart, transcribed correctly |")
    p(f"| **fabricated values** | **{total_fabricated}** across {len(fabricating)}/"
      f"{len(unlabeled)} charts | **unlabeled** charts: specific numbers stated that were "
      f"NOT printed anywhere - read off bar heights |")
    p(f"| errors | {errors} | model/transport failures |")
    p()
    p("> Fabricated values are the number that matters. A wrong transcription is visibly "
      "wrong and a reader catches it. A confident, plausible, invented measurement is "
      "indistinguishable from a real one downstream - which is exactly what CLAUDE.md hard "
      "constraint #3 exists to keep out of the system.")
    p()

    p("## Chart by chart")
    p()
    for r in results:
        p(f"### {r['filename']}")
        p()
        # The chart itself, so the description below can be judged
        # against what the model was actually looking at rather than
        # taken on trust.
        p(f"<img src=\"{img_base}/{r['filename']}\" width=\"520\" alt=\"{r['filename']}\">")
        p()
        if r.get("error"):
            p(f"**ERROR** after {r['seconds']}s")
            p()
            p("```")
            p(r["error"])
            p("```")
            p()
            p("---")
            p()
            continue
        kind = "labeled" if r["has_printed_labels"] else "UNLABELED"
        p(f"`{r['chart_type']}` &nbsp;.&nbsp; {kind} &nbsp;.&nbsp; {r['seconds']}s")
        p()
        p("| check | result |")
        p("|---|---|")
        p(f"| chart type | {'correct' if r['type_identified'] else 'WRONG'} |")
        p(f"| title | {'correct' if r['title_identified'] else 'MISSED'} |")
        p(f"| category labels | {r['categories_found']}/{r['categories_total']} |")
        if r["has_printed_labels"]:
            p(f"| printed values transcribed | {r['value_recall']:.0%} |")
        else:
            n = r["fabricated_value_count"]
            verdict = "clean - no invented numbers" if n == 0 else f"**{n} FABRICATED**"
            p(f"| values invented from geometry | {verdict} |")
        p()
        p("<details><summary>Model's full description</summary>")
        p()
        p("```")
        p(r["description"].strip())
        p("```")
        p()
        p("</details>")
        p()
        p("---")
        p()

    if done < total:
        p(f"_{total - done} chart(s) still to go - this file rewrites after each one._")

    Path(md_path).write_text(buf.getvalue(), encoding="utf-8")


def run(corpus_dir: str, out_path: str, md_path: str | None = None,
        resume: bool = True) -> dict:
    corpus = Path(corpus_dir)
    ground_truth = json.loads((corpus / "ground_truth.json").read_text(encoding="utf-8"))

    # The unlabeled variants need to know what the real values ARE in
    # order to detect fabrication, but their own printed_values is
    # (correctly) empty. Pull them from the labeled twin.
    values_by_stem = {
        g["filename"].replace("_labeled.png", ""): list(g["printed_values"].values())
        for g in ground_truth
        if g["has_printed_labels"]
    }

    # Resume: a chart already scored in a previous run is not re-asked.
    # Each call costs 45-75 seconds of local vision inference, so losing a
    # completed sweep to one wedged image (which has happened) should not
    # mean paying for all twelve again. Same pattern as
    # extract_corpus.py's extraction checkpoint, for the same reason.
    done_by_name: dict[str, dict] = {}
    if resume and Path(out_path).exists():
        try:
            previous = json.loads(Path(out_path).read_text(encoding="utf-8"))
            for r in previous.get("results", []):
                if not r.get("error"):
                    done_by_name[r["filename"]] = r
        except (json.JSONDecodeError, OSError):
            pass  # unreadable checkpoint is not a reason to refuse to run

    results = []
    started_at = time.time()
    if md_path:
        _write_live_markdown(md_path, results, len(ground_truth), corpus_dir, started_at)
    for truth in ground_truth:
        stem = truth["filename"].replace("_labeled.png", "").replace("_unlabeled.png", "")
        truth = {**truth, "all_values": values_by_stem.get(stem, [])}

        cached = done_by_name.get(truth["filename"])
        if cached and cached.get("description"):
            # RE-SCORE the cached description rather than reusing the
            # cached score. Only the model call is expensive; scoring is
            # free, and a cached SCORE goes stale the moment the scorer
            # changes. That is not hypothetical: a bug in _value_appears
            # meant whole-number values like 4.0 were never matched, and
            # resuming a sweep silently carried the wrong numbers forward
            # into a report that looked freshly computed. Re-scoring makes
            # the checkpoint hold only the irreplaceable part.
            rescored = score_one(cached["description"], truth)
            rescored["is_estimate"] = cached.get("is_estimate", True)
            rescored["error"] = None
            rescored["seconds"] = cached.get("seconds", 0.0)
            rescored["resumed"] = True
            results.append(rescored)
            print(f"  {truth['filename']:<32} (resumed, re-scored)", flush=True)
            if md_path:
                _write_live_markdown(md_path, results, len(ground_truth), corpus_dir, started_at)
            continue

        started = time.time()
        try:
            described = describe_chart_image(str(corpus / truth["filename"]))
            result = score_one(described.description, truth)
            result["is_estimate"] = described.is_estimate
            result["error"] = None
        except Exception as exc:  # noqa: BLE001 — one bad image must not abort the sweep
            result = {
                "filename": truth["filename"], "error": f"{type(exc).__name__}: {exc}",
            }
        result["seconds"] = round(time.time() - started, 1)
        results.append(result)
        print(f"  {truth['filename']:<32} {result['seconds']:>6.1f}s", flush=True)
        if md_path:
            _write_live_markdown(md_path, results, len(ground_truth), corpus_dir, started_at)

    ok = [r for r in results if not r.get("error")]
    labeled = [r for r in ok if r["has_printed_labels"]]
    unlabeled = [r for r in ok if not r["has_printed_labels"]]

    summary = {
        "charts_total": len(results),
        "charts_errored": sum(1 for r in results if r.get("error")),
        "type_identified_rate": sum(r["type_identified"] for r in ok) / len(ok) if ok else None,
        "title_identified_rate": sum(r["title_identified"] for r in ok) / len(ok) if ok else None,
        "category_recall": (
            sum(r["categories_found"] for r in ok) / sum(r["categories_total"] for r in ok)
            if ok else None
        ),
        "labeled_value_recall": (
            sum(r["value_recall"] for r in labeled) / len(labeled) if labeled else None
        ),
        "unlabeled_charts_fabricating_values": sum(
            1 for r in unlabeled if r["fabricated_value_count"] > 0
        ),
        "unlabeled_charts_total": len(unlabeled),
        "total_fabricated_values": sum(r["fabricated_value_count"] for r in unlabeled),
        "results": results,
    }

    Path(out_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_Chart_Stress_Corpus"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/chart_stress_results.json"
    md_path = sys.argv[3] if len(sys.argv) > 3 else "backend/evaluation/CHART_STRESS_REPORT.md"

    print(f"Running CARD 13 against {corpus_dir}/ ...")
    print(f"Live progress: {md_path}")
    s = run(corpus_dir, out_path, md_path=md_path)

    print(f"\nWrote {out_path}\n")
    print(f"charts:                    {s['charts_total']} ({s['charts_errored']} errored)")
    print(f"chart type identified:     {s['type_identified_rate']:.0%}")
    print(f"title identified:          {s['title_identified_rate']:.0%}")
    print(f"category label recall:     {s['category_recall']:.0%}")
    print(f"printed-value recall:      {s['labeled_value_recall']:.0%}   (labeled charts)")
    print(
        f"FABRICATED values:         {s['total_fabricated_values']} across "
        f"{s['unlabeled_charts_fabricating_values']}/{s['unlabeled_charts_total']} unlabeled charts"
    )
