# Presentation Generation Module Guide

> **This file was rewritten.** It described template cloning through
> `slide_kit.py` + `PPTX/MRPL_Template.pptx`, rendered inside the Docker
> sandbox. That engine is deleted. Why, and what replaced it, is below —
> the original approach and the reasons it failed are recorded because
> the failures are the argument for the current design.

## 1. Two halves, and the line between them

| Half | Owns | Lives in |
|---|---|---|
| **Content** | what the deck says, and that every figure is grounded | `backend/orchestrator/deck_agent.py` |
| **Design** | how it looks: grid, type, colour, charts, pagination | `backend/tools/generation/deck/` |

A model writes content as structured data and never touches layout. The
renderer lays out whatever survives validation and never invents content.

## 2. Why the template engine was replaced

Measured on five real prompts, with the decks rendered and inspected:

- **The planner never ran.** Ollama's `format=json` returns an *object*;
  the prompt asked for an *array*, so every reply was rejected and a
  hardcoded five-section outline was used. Every deck had the same
  structure — an SOP deck carried "SENSOR TELEMETRY & SPECIFICATIONS".
- **Topic drift by design.** Each section searched the corpus with its own
  generic title, so a deck on a pipeline incident gained a KPI slide about
  sandbox RAM limits. Asking for "a presentation on X" even retrieved this
  project's own PPTX guide, and the model then copied its mold names.
- **Invented figures, cited.** When a model call failed, fallbacks filled
  slides with fixed numbers (`1,450 m³/h`, a thermocouple table reading
  NORMAL, an FFC-201 interlock) and attached the section's citations.
  "The plot of Pride and Prejudice" produced a fully "sourced" deck.
- **The layouts could not hold real text.** Each of the 19 samples was
  positioned for its own example text: titles overflowed onto bullets,
  most molds had no title slot at all, picture placeholders rendered as
  broken-image icons, and tables kept the template's sample rows when the
  source had fewer.

## 3. The pipeline now

1. **Anchor documents.** Retrieve once, on the *topic* — the deliverable
   words ("make a presentation on") are stripped, because searching them
   finds documents about presentations. Keep only documents scoring near
   the best match, and read those in full. Nothing downstream sees
   anything else, so a slide cannot drift into an unrelated document.
2. **Storyline.** One call plans sections and, per slide, a type, a
   working title and the facts it must carry.
3. **Fill per section**, so a section's slides read as one argument.
4. **Validate every slide**: required fields present, table rows
   rectangular, one chart value per category, sources resolvable, and
   every figure ≥ 10 must appear in the source text (compared
   numerically, so `84.0` matches a source that says `84%` while an
   invented `91` is caught). One repair attempt, then the slide is
   dropped and reported — never shipped broken.
5. **Render** to `.pptx` with native PowerPoint charts and tables.

**Deck length follows the material.** `max_slides` is accepted and
ignored; lists paginate onto balanced continuation slides.

## 4. The approval gate (hard constraint #4)

A deck is a file leaving the building, so it is gated like `draft_docx`.
Because the gate's contract is that the operator approves *the concrete
call that will run*, the work is split:

- `prepare_deck(request)` plans and validates. **Writes nothing.**
- The approval card lists the filename, every slide title, the sources,
  and anything left out for lack of a source.
- `generate_deck(deck_spec, output_path)` — registered with
  `requires_approval=True` — renders exactly that spec, with no model
  call that could change what was approved, into `outputs/`.

An earlier "safe deliverable exemption" let decks be written unapproved.
It was removed.

## 5. Slide types the model may choose

`points`, `big_stat`, `kpis`, `chart`, `table`, `process`, `timeline`,
`alert` (incidents and limit breaches only), `comparison`, `actions`.

The cover, agenda, section dividers, the sources appendix and `exhibit`
(a real corpus image — a P&ID or a scan — with caption and source) are
placed by code, not chosen by a model. Nothing generates a picture of
plant equipment: an invented diagram on an approval-bound deck is a
fabricated record.

Type and field synonyms are accepted (`multi_stat_row` → `kpis`, `val` →
`value`), and consecutive single-item slides of one type are merged —
the model once returned eight `process` slides of one step each.

## 6. No sandbox for rendering

The sandbox exists for **model-written code**, which cannot be trusted
with the filesystem. The renderer is our own deterministic code driven by
validated data, so it runs in the backend. Rendering in a container made
deck generation fail whenever Docker was not running, for no safety
gained. `python-pptx` remains in the sandbox image for model-written code.

## 7. Running it

```bash
# Unit tests: design system + content validation, no model calls
py -3 -m pytest backend/tests/test_deck.py backend/tests/test_slide_agent.py -q -m "not live_model"

# The real thing, end to end (calls the model, minutes)
py -3 -m pytest backend/tests/test_slide_agent.py -q -m live_model
```

To look at a deck the way a user sees it, export slides through
PowerPoint itself rather than trusting the XML:

```powershell
$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open("<abs path>.pptx", -1, 0, 0)
foreach ($s in $pres.Slides) { $s.Export("C:\temp\slide_$($s.SlideIndex).png", "PNG", 1600, 900) }
$pres.Close(); $app.Quit()
```

## 8. Frontend hand-off

`generate_deck` returns `deck_path`, `filename`, `file_size`,
`slide_count` and `citations` (document names). Every field is measured;
a field the system cannot know is absent rather than filled with a
plausible default. The approval card carries `action_type: FILE_WRITE`,
the resolved `target` path, and `resolved_parameters: true`.
