# Sahil — what is done, what is not, and exactly what to do next

Written 2026-09-19 after reviewing `origin/sahil` line by line and merging it
into `main` (merge commit `08deb6f`). Pull `main` before starting anything
below — several things you wrote were changed during the merge, and the
reasons are recorded here so you are not surprised.

---

## 1. What is DONE and good (keep it)

| Deliverable | Status | Evidence |
|---|---|---|
| `/monitor` full view | **Done** | `App.jsx` routes `/monitor` to `NetworkMonitor mode="full"`. Polls `GET /api/network/status`, which is real: on the dev box it returns live connections and `externalCount: 0`. |
| Network monitor honesty | **Done** | An errored poll never shows green; the alarm keys only on `externalCount`. Exactly right. |
| Read-only image route `/api/inspection/image` | **Done** | Path is resolved and re-checked against the corpus root, so `..` cannot escape. Tested. |
| Upload → OCR/transcription pipeline | **Done** | Files upload into the corpus, then images/audio go through the registered tools; failures show as failed events, not fake successes. |
| No mock data anywhere | **Done** | No `Math.random` data, no sample payloads, no external URLs. Thank you — this is the standard. |

---

## 2. What was CHANGED during the merge (read this before coding)

1. **Your `MultimodalUpload` component is currently not mounted.** Advay had
   rebuilt the chat composer (voice, code mode, paperclip) on his branch while
   you wired your upload into the old composer. Both touched the same lines.
   The merge kept Advay's composer and routed its paperclip into **your**
   pipeline: images and audio now go through your upload + OCR/transcription
   code; small text files are still pasted inline. So your pipeline is live —
   your *component* (tray, drag-and-drop, thumbnails) is not. See task 2.
2. **`detect_defects` was made honest.** It told the model it "detects
   defect/anomaly regions", and mapped *low* OCR confidence to *high*
   severity — a blurry nameplate rendered as a high-severity defect. Now:
   the description says plainly it is **not** a defect detector, every
   region is severity `"low"`, and results carry `kind: "text_region"`.
   Test: `test_ocr_regions_are_not_presented_as_defects`.
3. **Removed a hardcoded toast**, "Grounded in 8 local sources — Zero
   outbound network egress". The 8 was invented. (Review Rule 4 in
   `CLAUDE.md`: fields the system cannot know are absent, never plausible.)
4. **Untracked `MRPL_RAG_Test_Corpus/07_User_Uploads/test_pump_log.txt`** —
   a test upload committed into the corpus, in a gitignored directory.
5. **Your network bar is still there**, restored at the foot of the chat pane.

---

## 3. What is NOT done — your task list, in priority order

### Task 1 (🔴, demo-critical): row 7 is marked "built" and is not

`docs/TOOLS.md` row 7 says **"Defect/anomaly detection (YOLOv8) — built"**
and describes it as detecting defect regions. It does not detect a single
defect: it returns where the printed text is. A judge who uploads a photo of
a corroded flange and asks "what's wrong here" gets nameplate text boxes.

You must pick ONE of these, knowingly, and update TOOLS.md row 7 + OWNERSHIP
+ this doc in the same commit (Review Rule 10):

- **Option A — descope honestly (recommended given the time left).** Change
  row 7's status to `not started (OCR text-region overlay only)`, keep 🟡,
  and make the chat say so when asked for defects. Your handoff doc
  (`Sahil_Defect_Detection_Handoff.md`, last section) already argues this.
- **Option B — build a real detector.** Only if you can finish ALL of:
  1. Weights fetched ONCE while online into `models/vision/` using the
     repo's fetch-once/offline-forever pattern (`backend/ingestion/model_cache.py`).
  2. ultralytics' four phone-homes disabled **before import** (analytics on
     import, analytics on predict, weight auto-download, Arial.ttf fetch) and a
     test that hard-blocks sockets and still runs `detect_defects`
     (`test_offline_with_sockets_hard_blocked` is the pattern).
  3. **No torch/cuDNN change in the shared environment** — the constraint in
     row 7's notes is real; use a venv.
  4. Any accuracy number names the dataset it was measured on. A public
     dataset fine-tune says nothing about MRPL photos.
  5. Same output contract (`id, label, confidence, box, severity, kind`) with
     `kind: "defect"` — the overlay must not change.

Acceptance: row 7's text matches what the code does, and asking the chat to
"find defects in this photo" either finds real ones or says detection is not
available. Never text boxes presented as defects.

### Task 2 (🔴): bring drag-and-drop and thumbnails into Advay's composer

Your assignment (FRONTEND.md §3.13) is "drag-and-drop/paperclip upload,
**immediate thumbnail preview** before processing". Today, in the composer
that shipped, a picked image shows only as a filename chip, and there is no
drag-and-drop.

- Work **with Advay** — it is his component. Do not replace his composer.
- Add a drop zone over the composer (drag-over highlight, drop → same path as
  his paperclip: images/audio into `attachments`, which already feeds your
  pipeline).
- Replace the filename chip for images with a thumbnail (the `previewUrl` is
  already created in `handleBrowserFilesUpload`), plus the status your pipeline
  sets (`queued → uploading → processing → ready / error`).
- Revoke object URLs when an attachment is removed or sent (your original
  component did this; the merged chips do not yet).
- Either delete `integrations/multimodal-upload/MultimodalUpload.jsx` if its
  pieces move into the composer, or mount it — do not leave dead code.

Acceptance: drop a PNG on the composer → thumbnail appears immediately → send
→ status moves through the states → the trace shows the OCR result.

### Task 3 (🔴, FR-14): uploaded images get OCR only, never understanding

FR-14 is *"Live demo of VLM correctly interpreting an image/diagram input."*
Right now an uploaded image goes to `detect_defects` (OCR) and nothing else, so
a P&ID or a photo is never *interpreted* — only its text is read.

- For images, also call the vision model. `describe_chart_image` exists for
  charts; for photos/diagrams coordinate with Aryan on a general
  image-description tool (row 6, P&ID extraction, is Aryan's and not started —
  that is the demo's Flow 3). **RESOLVED 2026-09-19:** a general image-description
  tool (`describe_image`, TOOLS.md row 72) is now Sahil's and built —
  `backend/tools/vision/image_description.py`, `is_estimate=True`. It is a PROSE
  description (subject, equipment, connections, printed text) and deliberately
  does NOT step on row 6's structured P&ID symbol/connection *extraction* into
  the graph layer — that stays Aryan's. Coordination point preserved in the
  row-72 module docstring and TOOLS.md row 72.
- Anything a vision model says about quantities is an **estimate** — render it
  with the ESTIMATE badge your MessageBubble already supports (`is_estimate`
  from `/api/tools`), exactly as for chart reading. **Done:** the image pipeline
  now calls `describe_image` alongside `detect_defects`, and `/api/tools`
  metadata (`is_estimate=True`) makes the trace badge it ESTIMATE automatically.

Acceptance: upload the corpus P&ID (`Hydrocracker_PID_Schematic.png`) → the
reply describes the equipment and connections, and any number is badged
ESTIMATE. **Status:** pipeline + tool + badge are in; full end-to-end needs the
vision model running at the venue (the dev box cannot test live vision — models
absent), pending Ollama vision availability.

### Task 4 (✅ DONE): prove the monitor goes red, on camera

The judges will scrutinise this panel more than anything else (your
assignment says so). Today we have only ever seen it green.

**Status: COMPLETE.** 10 backend tests + 6 frontend tests prove the red path:

- `test_own_external_socket_flips_the_status_to_external_detected` — mocked
  psutil socket with `pid=os.getpid()` on 8.8.8.8:443 → `status:
  "external_detected"`, `externalCount >= 1`, `is_air_gapped: False`.
- `test_api_network_status_goes_red_end_to_end` — the red state survives
  the full HTTP path via `TestClient(app).get("/api/network/status")`.
- `test_host_wide_figure_survives_the_mock_without_driving_the_alarm` —
  `hostExternalCount >= 1` alongside the alarm, but the alarm key is app-only.
- Frontend `security-state.test.js` (6 tests): `externalCount >= 1` →
  `security: "external_detected"`, `dotColor: DANGER`; host-wide alone never
  drives the alarm; errored poll never shows green.
- Remaining action: demo rehearsal (manual, not code).

### Task 5 (⚪, registry-listed is acceptable): rows 46 and 47

- Row 46 RBAC on the knowledge base — `not started`.
- Row 47 Model provenance tracking — `not started`.

Both are ⚪/🟡 and may stay registry-listed for the demo. If you start them,
say so in TOOLS.md first so nobody duplicates work.

---

## 4. Rules that apply to everything above (from `CLAUDE.md`)

- **No fabricated data**, even labelled. Unknown fields are absent.
- **A tool is not built until it has been called** through the registry in a
  test.
- **Run your new test against the previous commit** — if it passes there too,
  it is not testing your change.
- **Never `except: pass`** in anything that measures or reports.
- Commit messages say what broke and how you know it is fixed.

Ping Aryan with the commit hash when each task lands.
