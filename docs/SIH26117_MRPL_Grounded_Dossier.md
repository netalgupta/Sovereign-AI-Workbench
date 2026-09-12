# SIH26117 — MRPL-Grounded Dossier
## Every tool mapped to MRPL's actual refinery, not a generic "industrial plant"

Researched from MRPL's own site and public filings. No Wolfram Alpha anywhere — all computation is open-source and runs on your box (SymPy/Maxima/NumPy/CoolProp, per the previous spec). This document exists so every tool in the catalog can be pitched as "built for *this* refinery," not "built for refineries in general."

---

## 1. MRPL Operational Profile (the facts to design around)

- **15 MMTPA** design capacity, Category 1 Schedule 'A' Miniratna CPSE, subsidiary of ONGC, under Ministry of Petroleum & Natural Gas
- **Only refinery in India with two hydrocrackers** — premium low-sulphur diesel, a genuine point of technical pride for them
- **Two Continuous Catalytic Reformer (CCR) units** (UOP technology) — unleaded high-octane petrol, hydrogen as by-product
- **LPG Merox + Kero Merox units** (UOP) — sulphur/mercaptan removal
- **Three Hydrogen units** — steam reforming of naphtha, UOP Pressure Swing Adsorption (PSA) to 99.9% purity
- **440 KTA Novolen gas-phase Polypropylene plant** (Ziegler-Natta catalyst)
- **Aromatic Complex** in Mangalore SEZ — 0.905 MMTPA Para-Xylene, 0.273 MMTPA Benzene
- **Single Point Mooring "Mangala-1"** — 17km offshore, handles VLCCs (300,000T), 32m draft
- **Petronet MHB cross-country pipeline** — 363km Mangalore–Bangalore (via Devangonthi), with intermediate stations at Hassan and Neriya
- **Two captive jetties at New Mangalore Port Trust (NMPT)**, plus rail wagon + truck loading silos for Petcoke
- **Marketing depots**: Kasargod (Kerala), Hindupur (AP), Hosur (TN)
- **SAP ERP live since 15 Oct 2010**, covering Finance, Materials, Maintenance, Projects, Marketing, Production, Quality Assurance — this is the single most important fact for your design: **MRPL already has a structured system of record**. Your workbench's job is not to replace it, it's to **read, ground, and act on top of it, entirely on-prem.**

Use this list as your literal script when a judge asks "why does this feature matter to *us* specifically."

---

## 2. Unit-by-Unit Tool Mapping

### Hydrocracker Units (MRPL's signature technical differentiator)
- **Approval-note drafting tool**, pre-tuned with hydrocracker-specific terminology (LHSV, WABT, catalyst cycle length, conversion %) so drafted notes use the right vocabulary out of the box
- **Calculation tool**: catalyst deactivation trend / WABT creep modeling via SymPy + SciPy curve-fitting on historical operating data — flags when a catalyst change-out is approaching, with the math shown
- **P&ID symbol extraction** tuned on hydrocracker-specific line/valve tagging conventions (reactor loops, recycle gas compressors)

### CCR Units (UOP tech, high-octane petrol + hydrogen by-product)
- **Coking/regeneration cycle log summarizer** — condenses shift logs into a trend summary, flags deviations from normal regeneration cycle timing
- **Hydrogen balance calculator** — since H2 from CCR feeds the hydrotreating units, a Pint-based unit-aware mass-balance tool prevents the classic unit-conversion error class entirely

### Merox Units (LPG + Kero sulphur removal)
- **Sulphur-spec compliance checker** — cross-references lab results (ingested as scanned/digital lab sheets) against product spec sheets in the knowledge base, flags any near-limit reading automatically — ties directly into the "confidential inspection reports" language in the PS

### Hydrogen / PSA Units
- **Purity trend dashboard tool** — ingests PSA purity logs, plots against the 99.9% target using Matplotlib, flags drift
- **CoolProp-backed thermophysical lookup tool** — for any hydrogen/steam property lookups engineers currently do by hand from steam tables

### Polypropylene (Novolen) Plant
- **Grade-changeover checklist agent** — since Novolen is a gas-phase Ziegler-Natta process producing a range of homopolymer grades, a changeover-procedure retrieval + checklist-generation tool (grounded in the actual SOP for that grade transition) saves real manual-checklist time
- **Batch quality report generator** — auto-drafts a QA summary DOCX from lab data + spec sheet comparison

### Aromatic Complex (Para-Xylene / Benzene, MSEZ)
- **Cross-document reconciliation tool** — since this unit sits in a separate SEZ with likely separate correspondence trails, a tool that reconciles refinery-side and aromatic-complex-side documentation on shared feedstock/utilities is a genuinely non-obvious, MRPL-specific win
- **Benzene exposure/safety-note drafting** — benzene is a known carcinogen with strict handling SOPs; a tool that auto-drafts safety circulars grounded strictly in the ingested HSE SOPs (with the NotebookLM-style refuse-to-hallucinate discipline) is a serious, defensible safety USP

### SPM "Mangala-1" + Petronet MHB Pipeline
- **Vessel/cargo document processing** — VLCC cargo manifests, customs/port paperwork (scanned) → OCR + structured extraction → auto-populated tracking sheet
- **Pipeline SOP + incident-report graph** — given the pipeline spans Mangalore–Hassan–Neriya–Devangonthi, a graph layer linking SOPs, maintenance records, and past incident reports *by pipeline segment* is a concrete, non-generic GraphRAG demo query: *"show every maintenance record and incident report for the Hassan pumping station segment"*

### Marketing Depots (Kasargod, Hindupur, Hosur)
- **Multi-location correspondence summarizer** — condenses depot-to-HQ correspondence threads, flags anything requiring HQ approval action

### SAP ERP (Finance, Materials, Maintenance, Projects, Marketing, Production, QA)
This is the highest-leverage, most MRPL-specific tool in the whole catalog:
- **Local, read-only SAP connector tool** — since SAP has been live at MRPL since 2010 covering exactly the domains this PS cares about (Maintenance, Materials, QA, Projects), an agent tool that can query **on-prem SAP tables/reports directly** (via existing on-prem RFC/BAPI or a scheduled local export, never over the internet) grounds every drafted approval note or maintenance summary in **live operational data**, not just static documents
- Framed correctly this becomes your single strongest USP line: *"We don't just read your SOPs — we read your actual SAP maintenance and materials records, on-prem, and ground every draft in what the ERP already knows."*
- Keep the connector strictly read-only for the demo — write-back is a v2 conversation, not something to promise on stage

---

## 3. Design Principle Restated (per your instruction)

No Wolfram Alpha, no cloud math API, no cloud anything. Every computational claim in this system is backed by an open-source library executing locally (SymPy, Maxima, NumPy/SciPy, Pint, CoolProp, NetworkX — full spec in the previous document). This is not a limitation, it's the entire point: MRPL cannot use a tool that phones out to evaluate a hydrocracker mass balance, and neither can you.

---

## 4. Master USP List (MRPL-specific, for the pitch deck)

1. **"Only refinery in India with two hydrocrackers" gets a hydrocracker-literate assistant** — not a generic industrial chatbot, one that already speaks WABT, LHSV, and catalyst cycle language
2. **Grounded directly in MRPL's own SAP ERP** (live since 2010) — on-prem, read-only, zero internet, turning 15 years of structured operational data into agent-usable context
3. **Segment-aware pipeline intelligence** across the actual 363km Mangalore–Hassan–Neriya–Devangonthi corridor, not a generic "pipeline module"
4. **Benzene/Aromatic Complex safety-note drafting** with hard refuse-to-hallucinate grounding — a real safety-critical use case, not a demo toy
5. **Every number verified by code**, never guessed by an LLM — critical in a domain where a wrong mass balance or wrong sulphur-spec reading has real consequences
6. **Zero-egress, physically portable, deployable at any MRPL site** (refinery, SEZ aromatic complex, or a depot) off a single encrypted drive
7. **Built and proven on consumer-grade hardware (RTX 4060, 8GB)** — realistic for a PSU IT budget, not a hypothetical requiring a GPU cluster
