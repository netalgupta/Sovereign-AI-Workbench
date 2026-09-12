# Functional test report

End-to-end exercise of every delivered feature across normal, edge and adversarial inputs. This is not the unit suite — it asks whether each feature actually works when used, not whether its functions behave as designed.

**95 passed · 1 failed · 2 skipped** of 98 checks

## Failures

| feature | scenario | expected | observed |
|---|---|---|---|
| Live model | router classifies a real request | returns a classification from the live model | raised HTTPError: 404 Client Error: Not Found for url: http://localhost:11434/api/generate — model 'phi-3.5-mini' not found |

## All checks

### Tool registry — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | every registered tool exposes a usable schema | `normal` | all tools have a real description and typed parameters | 16 tools; all schemas well-formed |
| PASS | agent invents a plausible tool name | `adversarial` | KeyError that lists the real tools so the agent can correct itself | KeyError listing real tools: True |
| PASS | agent sends a wrong argument name | `adversarial` | TypeError naming the offending argument, not a silent drop | TypeError naming the bad argument: analyse_trend does not take ['data']. It takes: ['values'] |
| PASS | narrow schemas to one sub-agent's category | `normal` | a vision/audio/document tool never appears in the computation set | 10 computation tools; leaked: none |

### Math (SymPy) — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | arithmetic with precedence | `normal` | 8, computed by SymPy not by a model | 2 + 2*3 -> 8 |
| PASS | divide by zero | `edge` | an explicit infinity or a clean error — never a plain number | 1/0 -> zoo |
| PASS | syntactically invalid expression | `adversarial` | rejected rather than returning something | rejected: ValueError |

### Math (Pint) — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | convert bar to kPa | `normal` | 100 kPa | 1 bar -> expression='1 bar' result_magnitude=100.0 result_unit='kilopascal' steps=['1 bar', '100.0 kilopascal']  |
| PASS | add pressure to temperature | `adversarial` | rejected — this is the unit-error class the tool exists to prevent | rejected incompatible units: ValueError |

### Statistics — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | steady WABT creep | `normal` | increasing with a strong fit | increasing, slope 1.55, R2 0.9982 |
| PASS | a single reading | `edge` | refuses — a slope from one point is fabricated | refused: A trend needs at least 2 readings; got 1. Reporting a slope for a single point would be inventing one. |
| PASS | oscillating noise with no trend | `edge` | flat — must not report a direction its own fit quality calls unreliable | direction=flat, quality=poor — there is no reliable linear trend, self-consistent=True |
| PASS | every reading identical | `edge` | flat, and no divide-by-zero on R-squared | direction=flat, R2=1.0 |
| PASS | large negative through large positive | `edge` | increasing, no overflow | handles large negatives: increasing |
| PASS | threshold already passed | `edge` | no countdown to something that already happened | will_cross=False, steps=None, assumption='Already past the threshold at the most recent reading.' |
| PASS | a series with one wild reading | `edge` | the outlier is flagged, not silently averaged in | outliers flagged: [95.0] |
| PASS | empty series | `edge` | refuses | refused an empty series |

### Plotting — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | line chart with a threshold line | `normal` | real PNG bytes carrying their data provenance | PNG 33825 bytes, provenance recorded: True |
| PASS | fewer labels than values | `adversarial` | refuses — silently mislabelling every point is worse than not drawing | refused mismatched labels |
| PASS | a single data point | `edge` | renders without error | rendered 8352 bytes |
| PASS | 20 long category labels | `edge` | renders with rotation rather than overlapping text | 20 long labels rendered, 20159 bytes |

### MRPL process — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | clean WABT creep to end-of-run | `normal` | plannable, and refuses to invent a time base | plannable=True; WABT is creeping at 1.55 degC per reading (strong — the trend explains most of the variati |
| PASS | noisy WABT with no reliable trend | `edge` | NOT plannable — scheduling a shutdown on this would be wrong | plannable=False; WABT is flat over these 5 readings, so it is not approaching end-of-run on the current tre |
| PASS | consumption exceeds production | `normal` | named as a deficit with what to do about it | balance -4000 Nm**3/h; Consumption exceeds production by 4000 Nm**3/h. The shortfall must be  |
| PASS | no consumption side | `edge` | refuses — one side alone is a total, not a balance | refused a one-sided balance |
| PASS | purity partially below target | `normal` | counts breaches and names the worst reading | 2 below target, worst 99.1 |
| PASS | all readings pass but purity is falling | `edge` | reports BOTH — the trend is the actionable half | breaches=0, trend=decreasing |

### Contradiction detection — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | two documents disagree on a limit | `normal` | one HIGH severity finding naming both documents | 1 finding(s): 2 documents state different limits for "benzene 8-hour twa exposure": 1 ppm (HSE_Rev4.docx |
| PASS | same limit written in different units | `adversarial` | NO finding — 1 bar and 100 kPa are the same limit | 0 findings (expected 0 — same pressure) |
| PASS | a reading against a limit | `adversarial` | NO finding — one is evidence about the other | 0 findings (expected 0) |
| PASS | two dated readings | `adversarial` | NO finding — treating a time series as conflict flags every log | 0 findings (expected 0 — a trend) |
| PASS | same limit type, different equipment | `adversarial` | NO finding — HCU-2 and HCU-3 are different units | 0 findings (expected 0 — different units) |
| PASS | no documents at all | `edge` | no findings, no crash | empty corpus handled |
| PASS | sweep the whole real corpus | `normal` | runs over 21 real chunks and reports honestly | 0 finding(s) on the clean corpus (0 high) |

### Approval gate — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | gated tool called directly, no approval | `adversarial` | refused AND no file written | blocked; file written anyway: False |
| PASS | request, approve, execute | `normal` | the document is written exactly once | document written: C:\Users\Aryan\AppData\Local\Temp\tmp4ew5lxy8\ok.docx |
| PASS | reuse the same approval token | `adversarial` | denied — one approval authorises exactly one execution | second run denied: This approval has already been used. Each approval authorises exactly one execution; a second run needs a new approval. |
| PASS | swap the payload after approval | `adversarial` | denied AND nothing written — approval is bound to what was shown | denied: The arguments differ from what was approved. Approval is bound to the ; file written: False |
| PASS | approve a request that already expired | `edge` | denied — a decision made in a context that is gone | expired request cannot be approved |
| PASS | a read-only tool is not gated | `normal` | not gated — queueing harmless tools trains people to click yes | analyse_trend gated: False |

### Audit log — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | full lifecycle is reconstructable | `normal` | requested -> granted -> executed, with the approver named | ['approval_requested', 'approval_granted', 'tool_executed'], actors={'agent', 'aryan'} |
| PASS | a tool that failed after approval | `edge` | recorded — a gap would imply it never ran | ['approval_requested', 'approval_granted', 'tool_failed'] |

### Document output — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | a section with no sources | `edge` | marked UNSOURCED inside the document itself | UNSOURCED marker present in the file |
| PASS | content resting on a vision estimate | `edge` | the caveat is printed IN the document, not just in metadata | estimate caveat printed in the document body |
| PASS | output path with the wrong extension | `adversarial` | refuses — the user's tools would not open it | refused a non-.docx path |
| PASS | no sections at all | `edge` | refuses | refused a document with no sections |

### Document typing — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | PDF bytes saved with a .txt extension | `adversarial` | detected as pdf from content, not from the name | '.txt' holding PDF bytes detected as: pdf |
| PASS | a zero-byte file | `edge` | classified without crashing | detected: txt |

### Chunking — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | whitespace-only document | `edge` | no chunks — an empty chunk would be embedded and pollute the corpus | whitespace-only text produced no chunks |
| PASS | mixed unicode (accents, CJK, Cyrillic) | `edge` | characters survive chunking intact | 2 chunks, non-ASCII preserved |
| PASS | a single 50,000-character token | `adversarial` | split rather than returned as one oversized chunk | a 50k-character token split into 112 chunks |

### Ingestion — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | a corrupt PDF | `adversarial` | fails loudly or yields nothing — never silent garbage chunks | failed loudly: PdfminerException |
| PASS | a real corpus DOCX | `normal` | chunks with complete metadata on every one | 2 chunks, every one carrying source + date metadata |

### Retrieval — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | an in-corpus question | `normal` | found, with the answering document in the results | found=True, top sources=['SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx', 'Novolen_Batch_QA_Report_Aug2026.pdf', 'SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx'] |

### Refusal gate (NFR-4) — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | 6 questions from in-corpus to Pride and Prejudice | `normal` | in-corpus answered, off-domain and unrelated refused | all 6 behaved correctly |
| PASS | an empty query string | `edge` | refused rather than returning arbitrary chunks | empty query -> found=False |
| PASS | keyboard mash | `adversarial` | refused | gibberish -> found=False |
| PASS | a single bare domain word | `edge` | a decision is made without crashing | 'sulphur' -> found=False (either is defensible) |
| PASS | querying an empty corpus | `edge` | refused with a reason that says the corpus is empty | reason: No documents in the corpus matched this query. |
| PASS | prompt-injection styled query | `adversarial` | treated as ordinary text and refused — it matches nothing | found=False (no corpus content matches this) |

### Image retrieval — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | 'show me the hydrocracker P&ID' | `normal` | returns the P&ID, not a chart | selected: Hydrocracker_PID_Schematic.png (score 0.7547) |
| PASS | a request no image satisfies | `adversarial` | returns nothing — a wrong diagram is worse than none | 0 matches (expected 0) |
| PASS | resolve an image to actual pixels | `normal` | real bytes come back, not a description | resolved 23215 bytes of real pixels |
| PASS | an image id that does not exist | `edge` | None rather than an exception | unknown id returned None |

### Source tracking — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | a registered file is edited after indexing | `normal` | reported MODIFIED with a message the UI can show | status=modified; detail=sop.txt has changed since it was indexed. Anything quoted from it may  |
| PASS | a registered file is deleted | `edge` | reported MISSING, not an exception | status=missing |
| PASS | registering a document | `normal` | records the path only — the user's bytes are never duplicated | registry metadata is 416 bytes for a 10,000-byte document |
| PASS | a Downloads folder full of non-documents | `adversarial` | only the real document is queued — partial downloads produce garbage chunks | offered: ['keep.pdf'] |
| PASS | a new file lands beside an old one | `normal` | the newest is first — new work preempts the backlog | order: ['new.pdf', 'old.pdf'] |

### Ingestion queue — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | a file that fails every time | `adversarial` | parked after 3 attempts, error retained, queue not blocked | failed=1, still pending=0, error retained: True |

### Page preview — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | render page 1 of a real corpus PDF | `normal` | a real PNG with highlight rectangles | 1275x1650 PNG, 2 highlight rect(s) |
| PASS | a page number past the end | `edge` | None rather than a crash or a blank image | page 9999 -> None |
| PASS | a document that was never registered | `edge` | None | unregistered document -> None |

### Planner — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | model returns prose instead of JSON | `adversarial` | PlanningError — an empty plan would be executed as 'nothing to do' | rejected: Planner did not return JSON: "Sure! I'd be happy to help you |
| PASS | every step depends on another (cycle) | `adversarial` | repaired into a runnable plan without discarding steps — a hang is indistinguishable from slow inference | 3 steps kept, 1 able to start |
| PASS | a dependency on a step the model never emitted | `adversarial` | dropped — otherwise the step waits forever on an id nobody completes | deps after repair: ['a'] |
| PASS | a 60-step plan | `edge` | capped — each step is tens of seconds of local inference | 60 proposed -> 12 kept |
| PASS | the model returns zero steps | `edge` | rejected — an empty plan reports success having done nothing | rejected |

### Self-verification — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | verifier returns prose, not JSON | `adversarial` | treated as UNVERIFIED — defaulting to satisfied makes a malformed response a silent pass | passed=False; reason='The verifier did not return a readable verdict, so this outp' |
| PASS | nothing was produced to verify | `edge` | UNCONFIRMED — a step that produced nothing must not reach the gate as verified | outcome=unconfirmed even though the verifier said satisfied |
| PASS | verification fails four times running | `adversarial` | exactly 2 re-plans then UNCONFIRMED — never loops, never silently ships | outcomes: ['replan', 'replan', 'unconfirmed', 'unconfirmed'] |
| PASS | the message shown to a human | `normal` | says what was checked, what was missing, and that it is not vouched for | 'Verification could not confirm this output is complete after 2 attempts. The checker said: No source given. Re' |

### Sub-agent contracts — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | vision_agent attempts a file write | `adversarial` | refused by the closed tool set, not by convention | refused: vision_agent may not call 'draft_docx'. AGENTS_SPEC §6 allows it: ['de |
| PASS | math_tool attempts a chart reading | `adversarial` | refused | refused — an estimate must not enter where a computed number is expected |
| PASS | dispatch called twice before any step finishes | `edge` | the same step is never handed out twice | first=1, second=0 |

### API — OK

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| PASS | GET /api/health | `normal` | reports each dependency, so a UI can explain an empty screen | health keys: ['corpus_loaded', 'documents_registered', 'graph_available', 'images_stored'] |
| PASS | GET /docs | `normal` | 404 — the default page fetches JS from a CDN, violating hard constraint #1 | FastAPI's CDN-backed Swagger page is disabled |
| PASS | call a tool that does not exist | `adversarial` | 404, correctable by the caller | status 404 |
| PASS | call a gated tool over HTTP with no approval | `adversarial` | 403 AND no file written | status 403, file written: False |
| PASS | a tool called with invalid arguments | `adversarial` | 400 with the tool's own message | status 400 |
| PASS | full approval flow over HTTP | `normal` | no token leak, 403 before approval, 200 once, 403 on replay | token leaked=False, pre-approval=403, execute=200, replay=403, written=True |
| PASS | GET /api/metrics | `normal` | every result carries when it was measured | 5 metric sets, all timestamped: True |
| PASS | POST /api/search with an off-topic question | `adversarial` | found=false with an explicit reason | found=False, reason='not found in the provided corpus' |
| PASS | GET /api/contradictions | `normal` | sweeps the corpus and reports | checked 21 chunks, 0 findings |
| PASS | GET /api/graph with Neo4j down | `edge` | falls back to the snapshot and SAYS so, rather than serving an empty graph | source=snapshot, nodes=101, warning=Neo4j unavailable (ServiceUnavailable: Couldn't connect to l |

### Knowledge graph — SKIPPED

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| — | signature query for Mangalore-Hassan | `normal` | Neo4j unreachable — Docker Desktop is not running on this machine | Neo4j unreachable — Docker Desktop is not running on this machine |
| — | relationship domain/range validity | `normal` | Neo4j unreachable — Docker Desktop is not running on this machine | Neo4j unreachable — Docker Desktop is not running on this machine |

### Live model — 1 FAILED

| # | scenario | input | expected | observed |
|---|---|---|---|---|
| **FAIL** | router classifies a real request | `normal` | returns a classification from the live model | raised HTTPError: 404 Client Error: Not Found for url: http://localhost:11434/api/generate — model 'phi-3.5-mini' not found |

