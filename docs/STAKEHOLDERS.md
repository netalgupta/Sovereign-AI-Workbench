# STAKEHOLDERS.md — SIH26117

## 1. MRPL-Side Stakeholders (who this system is actually for)

| Stakeholder | Role in the workflow | What they need from this system |
|---|---|---|
| Control room / process engineers | Draft approval notes, review inspection findings, run engineering calcs | Fast, accurate drafting grounded in real unit terminology (hydrocracker, CCR, Merox, etc.), verified math |
| HSE (Health, Safety, Environment) officers | Review inspection reports, issue safety circulars, track incidents | Trustworthy, non-hallucinating summarization; especially critical for Aromatic Complex (benzene) safety notes |
| Maintenance planners | Schedule turnarounds, track catalyst/equipment life, log inspection findings | Trend analysis on inspection/maintenance data, grounded in SAP Maintenance module data |
| Materials / procurement staff | Vendor negotiations, materials tracking | Confidentiality-first document handling; SAP Materials module grounding |
| QA lab personnel | Log test results, check spec compliance | Automated spec-compliance checking against ingested product spec sheets |
| Plant management / approvers | Sign off on approval notes and reports | Clear, real DOCX/PPTX deliverables with audit trail and citation backing, not raw chat output |
| IT / Information Security team | Own the deployment, must approve any new system touching confidential data | Zero-egress proof, encryption at rest, audit logging, RBAC — this stakeholder is effectively a co-judge of the "sovereign" claim |
| Depot staff (Kasargod, Hindupur, Hosur) | Correspondence with HQ | Multi-location correspondence summarization |
| ONGC (parent company) oversight | Governance/compliance oversight over MRPL as a CPSE | Indirect stakeholder — reinforces why governance/audit features matter, not just functionality |

## 2. SIH-Side Stakeholders

| Stakeholder | What they're evaluating |
|---|---|
| SIH Judges / Evaluation Panel | PS coverage, technical depth, live demo credibility, feasibility of real deployment |
| MRPL PS mentors / SPOC | Domain relevance — do the demoed tools actually speak to real refinery workflows |
| SIH nodal center (KJSSE) | Team readiness, presentation quality, adherence to submission format |

## 3. Team-Side Stakeholders (build-side responsibility map)

| Person | Primary responsibility |
|---|---|
| Aryan | RAG/AI/ML/LLM engineering, team lead — model registry, routing, RAG/GraphRAG, vision integration, technical direction |
| Aditya | Backend lead — orchestrator, sandbox execution, SAP connector, infra/deployment, network monitor backend |
| Advay | Fullstack lead — overall frontend architecture, integration layer, coordinates other frontend contributors |
| Kanishka | Fullstack (foundational tools) — output viewers, file upload UI, settings, audit log UI |
| Sahil | Fullstack (mid-complexity tools) — OCR/vision UI, calculation trace viewer |
| Netal | Fullstack (mid-complexity tools) — knowledge base/source manager UI, graph visualization, citations |

Full task breakdowns per person live in their individual `<name>.md` assignment files.

## 4. Stakeholder-to-Requirement Cross-Reference

- HSE officers → NFR-4 (traceable claims), Aromatic Complex safety-note tool
- Maintenance planners → SAP connector (§5 of REQUIREMENTS.md), trend analysis tools
- IT/InfoSec → FR-1, FR-15, NFR-3, NFR-7 (the entire "governance" category is written for this stakeholder)
- Plant approvers → FR-9, FR-12, NFR-6 (human confirmation gate)
- Judges → REQUIREMENTS.md traceability table itself, live demo script in TOOLS.md category I
