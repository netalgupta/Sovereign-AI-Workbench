# MRPL RAG/GraphRAG Validation Report

Full, untruncated question/expected-answer/actual-answer/source-provenance record for every question in the test set, against the real ingestion -> retrieval -> generation pipeline (RAG_SPEC.md §2-§4). No summarization or truncation of any generated text or retrieved passage below.


---

## Q1. What is the WABT end-of-run trigger temperature for HCU-2?

**Expected answer:** > 410 °C

**Expected source:** SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx


**Actual answer (full, verbatim):**

The WABT (Weighted Average Bed Temperature) end-of-run trigger temperature for HCU-2 is > 410 °C. [N] 

[N] Source: SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx, Revision History section indicates this value was updated based on catalyst vendor guidance in Rev 2 (2023-11-18).


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0325)

> 4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.
4.5 Fresh catalyst loading (dense loading method) to the bed density specified in the catalyst vendor's Technical Data Sheet, batch-verified against the Certificate of Analysis.
4.6 Catalyst sulfiding (activation) per the sulfiding curve in Appendix A - typical duration 36-48 hours.
4.7 Gradual introduction of feed, WABT ramp not exceeding 15°C/hour until target conversion is reached.
4.8 Post-changeout performance verification against Section 3 parameters for 72 continuous hours before the unit is declared in normal service.
5. Safety Precautions
Pyrophoric catalyst hazard: spent NiMo catalyst can self-heat on air exposure. Unloading must proceed under continuous nitrogen blanket or water-wetting per vendor guidance. Full-face supplied-air respirators are mandatory for all vessel-entry personnel. H2S monitoring is continuous throughout Sections 4.3-4.4.
6. Revision History
Revision	Date	Description of Change	Approved By
Rev 1	2021-06-02	Initial issue	Process Safety Group
Rev 2	2023-11-18	Updated WABT end-of-run trigger from 405 to 410 °C based on catalyst vendor guidance	Process Safety Group
Rev 3	2026-03-14	Added Section 5 pyrophoric hazard precautions; added Form F-114-A reference	HSE + Process Safety Group
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[2] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 2** (fused score: 0.0313)

> approximately 40 minutes before DCS alarm response. Batch downgraded to off-spec inventory; grade
changeover checklist (see SOP reference) updated to add a hold point at the 20-minute mark for
feed-rate confirmation.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[3] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0311)

> SOP-114: Hydrocracker Catalyst Changeout Procedure
Document No: SOP-114-Rev3   |   Unit: Hydrocracker-2 (HCU-2)   |   Effective Date: 2026-03-14   |   Review Cycle: 24 months
1. Purpose
This procedure defines the safe sequence of operations for changing out spent hydrocracking catalyst in HCU-2 Reactor R-201, including bed unloading, sulfiding of fresh catalyst, and return-to-service checks. This SOP applies specifically to the NiMo-alumina extrudate catalyst system currently qualified for HCU-2 service.
2. Scope and Applicability
Applies to: HCU-2 Reactor R-201 (Beds 1-3), associated recycle gas compressor K-201, and feed/effluent heat exchanger train E-201A/B. Does not apply to HCU-1 (R-101), which uses a different catalyst loading pattern under SOP-098.
3. Key Process Parameters (Reference Values)
The table below lists the normal operating envelope used to judge catalyst end-of-run:
Parameter	Normal Range	End-of-Run Trigger	Unit
Weighted Average Bed Temperature (WABT)	365 - 385	> 410	°C
LHSV (Liquid Hourly Space Velocity)	1.1 - 1.4	N/A (design basis)	hr⁻¹
Reactor Delta-P (Bed 2)	0.8 - 1.5	> 3.5	kg/cm²
Conversion (360°C+ fraction)	68 - 72	< 60	%
Recycle Gas H2 Purity	92 - 95	< 88	%
Catalyst Cycle Length (design)	22 - 26	N/A	months
4. Changeout Sequence
4.1 Unit shutdown and depressurization of R-201 per SOP-050 (Reactor Depressurization).
4.2 Nitrogen purge to < 0.5% hydrocarbon (LEL meter confirmation) before vessel entry permit is issued.
4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.


**[4] Aromatic_Complex_Benzene_Safety_Circular.docx** (fused score: 0.0301)

> HSE Safety Circular No. SC-2026-011
Unit: Aromatic Complex (MSEZ)   |   Classification: Confidential - Internal Use   |   Issue Date: 2026-05-02
Subject: Benzene Exposure Control - Storage Tank Farm TK-701 to TK-704
1. Background
This circular reiterates mandatory exposure control measures for personnel working in or near the Benzene storage and loading area (TK-701 to TK-704) within the Aromatic Complex. Benzene is classified as a Category 1 carcinogen. All requirements below are mandatory and supersede general area PPE guidance for this specific zone.
2. Exposure Limits
Exposure Metric	Limit	Action if Exceeded
8-hour TWA (Time Weighted Average)	1 ppm	Immediate area evacuation, HSE incident report within 4 hours
Short-Term Exposure Limit (STEL, 15 min)	5 ppm	Area evacuation, personal monitor review
Fixed gas detector alarm threshold	0.5 ppm	Automatic area alarm + PA announcement
3. Mandatory Controls
Personal benzene dosimeter badges worn at all times within the tank farm boundary, logged out/in at the HSE gate register.
Supplied-air respiratory protection required for any tank-top gauging, sampling, or connection/disconnection of loading arms.
No hot work within 30 metres of TK-701 to TK-704 without an active Hot Work Permit co-signed by the Aromatic Complex Shift Supervisor and HSE.
Continuous fixed benzene detection required to be in-service before any loading operation commences; loading is prohibited if any detector in the zone is under maintenance without an approved compensatory monitoring plan.
4. Reference Documents
SOP-221 (Benzene Loading Arm Operation), SOP-225 (Confined Space Entry - Aromatic Complex), HSE Manual Section 7.4 (Carcinogen Management)
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[5] Inspection_Report_CCR1_Regeneration_Cycle.pdf, page/sheet 1** (fused score: 0.0294)

> Inspection Report: CCR-1 Regeneration Cycle 18
Report No: IR-CCR1-2026-018 | Unit: CCR-1 (Continuous Catalytic Reformer) | Inspection Date:
2026-08-11
1. Summary of Findings
Regeneration Cycle 18 completed in 34 hours, exceeding the normal target of 28 hours by 6 hours.
This is the second consecutive cycle showing extended duration (Cycle 17: 31 hours, Cycle 18: 34
hours), following three cycles within normal range. Preliminary root cause: reduced chlorination
efficiency attributed to moisture ingress in the regeneration gas circuit, under investigation by the
Process Engineering team.
2. Cycle Duration Trend
3. Key Parameters at Cycle Completion
Parameter Cycle 17 Cycle 18 Normal Range
Coke Burn Rate (kg/hr) 142 128 135 - 155
Regeneration Gas O2 (%) 0.6 0.5 0.5 - 1.0
Chlorination Efficiency (%) 91 84 90 - 96
Catalyst Chloride Retention (%) 0.92 0.85 0.9 - 1.1
Bed Outlet Temp (°C) 482 478 470 - 490


---

## Q2. What caused the off-spec batch H110F-0847?

**Expected answer:** Catalyst feed rate excursion during grade changeover, ~40 min before DCS alarm response

**Expected source:** Novolen_Batch_QA_Report_Aug2026.pdf


**Actual answer (full, verbatim):**

According to the Novolen Batch QA Report from August 2026 [5], the root cause of the off-spec batch H110F-0847 was a catalyst feed rate excursion during the grade changeover process from Homopolymer H030SG [2].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0320)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[2] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 2** (fused score: 0.0311)

> approximately 40 minutes before DCS alarm response. Batch downgraded to off-spec inventory; grade
changeover checklist (see SOP reference) updated to add a hold point at the 20-minute mark for
feed-rate confirmation.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[3] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0311)

> SOP-114: Hydrocracker Catalyst Changeout Procedure
Document No: SOP-114-Rev3   |   Unit: Hydrocracker-2 (HCU-2)   |   Effective Date: 2026-03-14   |   Review Cycle: 24 months
1. Purpose
This procedure defines the safe sequence of operations for changing out spent hydrocracking catalyst in HCU-2 Reactor R-201, including bed unloading, sulfiding of fresh catalyst, and return-to-service checks. This SOP applies specifically to the NiMo-alumina extrudate catalyst system currently qualified for HCU-2 service.
2. Scope and Applicability
Applies to: HCU-2 Reactor R-201 (Beds 1-3), associated recycle gas compressor K-201, and feed/effluent heat exchanger train E-201A/B. Does not apply to HCU-1 (R-101), which uses a different catalyst loading pattern under SOP-098.
3. Key Process Parameters (Reference Values)
The table below lists the normal operating envelope used to judge catalyst end-of-run:
Parameter	Normal Range	End-of-Run Trigger	Unit
Weighted Average Bed Temperature (WABT)	365 - 385	> 410	°C
LHSV (Liquid Hourly Space Velocity)	1.1 - 1.4	N/A (design basis)	hr⁻¹
Reactor Delta-P (Bed 2)	0.8 - 1.5	> 3.5	kg/cm²
Conversion (360°C+ fraction)	68 - 72	< 60	%
Recycle Gas H2 Purity	92 - 95	< 88	%
Catalyst Cycle Length (design)	22 - 26	N/A	months
4. Changeout Sequence
4.1 Unit shutdown and depressurization of R-201 per SOP-050 (Reactor Depressurization).
4.2 Nitrogen purge to < 0.5% hydrocarbon (LEL meter confirmation) before vessel entry permit is issued.
4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.


**[4] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0310)

> 4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.
4.5 Fresh catalyst loading (dense loading method) to the bed density specified in the catalyst vendor's Technical Data Sheet, batch-verified against the Certificate of Analysis.
4.6 Catalyst sulfiding (activation) per the sulfiding curve in Appendix A - typical duration 36-48 hours.
4.7 Gradual introduction of feed, WABT ramp not exceeding 15°C/hour until target conversion is reached.
4.8 Post-changeout performance verification against Section 3 parameters for 72 continuous hours before the unit is declared in normal service.
5. Safety Precautions
Pyrophoric catalyst hazard: spent NiMo catalyst can self-heat on air exposure. Unloading must proceed under continuous nitrogen blanket or water-wetting per vendor guidance. Full-face supplied-air respirators are mandatory for all vessel-entry personnel. H2S monitoring is continuous throughout Sections 4.3-4.4.
6. Revision History
Revision	Date	Description of Change	Approved By
Rev 1	2021-06-02	Initial issue	Process Safety Group
Rev 2	2023-11-18	Updated WABT end-of-run trigger from 405 to 410 °C based on catalyst vendor guidance	Process Safety Group
Rev 3	2026-03-14	Added Section 5 pyrophoric hazard precautions; added Form F-114-A reference	HSE + Process Safety Group
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[5] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 1** (fused score: 0.0307)

> Novolen Polypropylene Plant - Monthly Batch QA
Report
Report Period: August 2026 | Plant Capacity: 440 KTA (Novolen Gas-Phase, Ziegler-Natta)
1. Production Mix
2. Batch Quality Summary
Grade Batches ProduceAdvg MFI (g/10minS)pec MFI RangeDensity (g/cm3) Off-Spec Batches
Homopolymer H030SG 22 3.4 3.0 - 3.8 0.905 0
Homopolymer H110F 16 11.2 10.0 - 12.0 0.905 1
Random Copolymer RP340 12 3.9 3.5 - 4.5 0.900 0
Impact Copolymer HP500 9 0.8 0.6 - 1.0 0.900 0
3. Off-Spec Batch Detail
Batch H110F-0847 (produced 2026-08-17) recorded MFI of 12.9 g/10min, above the upper spec limit of
12.0. Root cause: catalyst feed rate excursion during grade changeover from H030SG, duration


---

## Q3. What is the 8-hour TWA benzene exposure limit at the Aromatic Complex?

**Expected answer:** 1 ppm

**Expected source:** Aromatic_Complex_Benzene_Safety_Circular.docx


**Actual answer (full, verbatim):**

The 8-hour Time Weighted Average (TWA) benzene exposure limit at the Aromatic Complex for personnel working in or near the Benzene storage and loading area (TK-701 to TK-704) is 1 ppm [1].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Aromatic_Complex_Benzene_Safety_Circular.docx** (fused score: 0.0328)

> HSE Safety Circular No. SC-2026-011
Unit: Aromatic Complex (MSEZ)   |   Classification: Confidential - Internal Use   |   Issue Date: 2026-05-02
Subject: Benzene Exposure Control - Storage Tank Farm TK-701 to TK-704
1. Background
This circular reiterates mandatory exposure control measures for personnel working in or near the Benzene storage and loading area (TK-701 to TK-704) within the Aromatic Complex. Benzene is classified as a Category 1 carcinogen. All requirements below are mandatory and supersede general area PPE guidance for this specific zone.
2. Exposure Limits
Exposure Metric	Limit	Action if Exceeded
8-hour TWA (Time Weighted Average)	1 ppm	Immediate area evacuation, HSE incident report within 4 hours
Short-Term Exposure Limit (STEL, 15 min)	5 ppm	Area evacuation, personal monitor review
Fixed gas detector alarm threshold	0.5 ppm	Automatic area alarm + PA announcement
3. Mandatory Controls
Personal benzene dosimeter badges worn at all times within the tank farm boundary, logged out/in at the HSE gate register.
Supplied-air respiratory protection required for any tank-top gauging, sampling, or connection/disconnection of loading arms.
No hot work within 30 metres of TK-701 to TK-704 without an active Hot Work Permit co-signed by the Aromatic Complex Shift Supervisor and HSE.
Continuous fixed benzene detection required to be in-service before any loading operation commences; loading is prohibited if any detector in the zone is under maintenance without an approved compensatory monitoring plan.
4. Reference Documents
SOP-221 (Benzene Loading Arm Operation), SOP-225 (Confined Space Entry - Aromatic Complex), HSE Manual Section 7.4 (Carcinogen Management)
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[2] Inspection_Report_CCR1_Regeneration_Cycle.pdf, page/sheet 1** (fused score: 0.0313)

> Inspection Report: CCR-1 Regeneration Cycle 18
Report No: IR-CCR1-2026-018 | Unit: CCR-1 (Continuous Catalytic Reformer) | Inspection Date:
2026-08-11
1. Summary of Findings
Regeneration Cycle 18 completed in 34 hours, exceeding the normal target of 28 hours by 6 hours.
This is the second consecutive cycle showing extended duration (Cycle 17: 31 hours, Cycle 18: 34
hours), following three cycles within normal range. Preliminary root cause: reduced chlorination
efficiency attributed to moisture ingress in the regeneration gas circuit, under investigation by the
Process Engineering team.
2. Cycle Duration Trend
3. Key Parameters at Cycle Completion
Parameter Cycle 17 Cycle 18 Normal Range
Coke Burn Rate (kg/hr) 142 128 135 - 155
Regeneration Gas O2 (%) 0.6 0.5 0.5 - 1.0
Chlorination Efficiency (%) 91 84 90 - 96
Catalyst Chloride Retention (%) 0.92 0.85 0.9 - 1.1
Bed Outlet Temp (°C) 482 478 470 - 490


**[3] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0311)

> 4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.
4.5 Fresh catalyst loading (dense loading method) to the bed density specified in the catalyst vendor's Technical Data Sheet, batch-verified against the Certificate of Analysis.
4.6 Catalyst sulfiding (activation) per the sulfiding curve in Appendix A - typical duration 36-48 hours.
4.7 Gradual introduction of feed, WABT ramp not exceeding 15°C/hour until target conversion is reached.
4.8 Post-changeout performance verification against Section 3 parameters for 72 continuous hours before the unit is declared in normal service.
5. Safety Precautions
Pyrophoric catalyst hazard: spent NiMo catalyst can self-heat on air exposure. Unloading must proceed under continuous nitrogen blanket or water-wetting per vendor guidance. Full-face supplied-air respirators are mandatory for all vessel-entry personnel. H2S monitoring is continuous throughout Sections 4.3-4.4.
6. Revision History
Revision	Date	Description of Change	Approved By
Rev 1	2021-06-02	Initial issue	Process Safety Group
Rev 2	2023-11-18	Updated WABT end-of-run trigger from 405 to 410 °C based on catalyst vendor guidance	Process Safety Group
Rev 3	2026-03-14	Added Section 5 pyrophoric hazard precautions; added Form F-114-A reference	HSE + Process Safety Group
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[4] SAP_Mock_Materials_Master_Export.xlsx, page/sheet 1** (fused score: 0.0299)

> Sheet: Materials Master (Mock)
SAP Materials Master - Mock Export (Structured to Match Real SAP MARA/MARC Shape, Synthetic Data)							
							
Material No.	Material Description	Category	Unit (Plant)	Vendor Code	Stock Qty (UoM)	Unit Value (Rs.)	Line Value (Rs.)
MAT-100234	NiMo Hydrocracking Catalyst (Extrudate)	Catalysts	Hydrocracker-2	VEND-1042	12	480000	5760000
MAT-100567	CCR Platinum-Rhenium Catalyst	Catalysts	CCR-1	VEND-1077	8	950000	7600000
MAT-200112	Control Valve, 6-inch, Class 600	Spare Parts	Hydrocracker-1	VEND-2033	25	62000	1550000
MAT-200334	Pressure Transmitter, 4-20mA	Instrumentation	PSA Unit 2	VEND-2091	40	18500	740000
MAT-300021	Amine Solution (MDEA, 45%)	Chemicals	LPG Merox	VEND-3010	5000	145	725000
MAT-300088	Ziegler-Natta Catalyst Component	Catalysts	Novolen Plant	VEND-1042	15	620000	9300000
MAT-400015	Carbon Steel Piping, Sch 40, 8-inch	Piping	Aromatic Complex	VEND-4021	300	3200	960000
MAT-400099	Supplied-Air Respirator Set	Safety Equipment	Aromatic Complex	VEND-5001	60	21000	1260000
MAT-500044	Recycle Gas Compressor Seal Kit	Spare Parts	Hydrocracker-2	VEND-2033	6	340000	2040000
MAT-500210	Fixed Benzene Gas Detector	Safety Equipment	Aromatic Complex	VEND-5001	18	95000	1710000
							
							
Category	Item Count						
Catalysts	3						
Spare Parts	2						
Instrumentation	1						
Chemicals	1						
Piping	1						
Safety Equipment	2						
							
							
Vendor Code	Total Inventory Value (Rs.)						
VEND-1042	15060000						
VEND-1077	7600000


**[5] Inspection_Report_CCR1_Regeneration_Cycle.pdf, page/sheet 2** (fused score: 0.0290)

> 4. Recommendations
- Inspect regeneration gas dryer (D-102) desiccant bed condition before Cycle 19.
- Verify moisture analyzer AI-4471 calibration - last calibrated 2026-02-10 (over 6 months).
- If Cycle 19 duration again exceeds 30 hours, escalate to a full chlorination system review per
SOP-140.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


---

## Q4. Why was Tank TK-K-03 at Kasargod held out of service?

**Expected answer:** 0.6% calibration variance exceeding the 0.3% internal tolerance

**Expected source:** Correspondence_Depot_HQ_Thread_Kasargod.docx


**Actual answer (full, verbatim):**

Tank TK-K-03 at Kasargod was held out of service because the third-party calibration agency's dip-chart figures showed a variance of 0.6% against the previous calibration certificate, which is above the internal tolerance of 0.3% for MS tanks as per Depot Operations Manual Section 5.2 [1]. This discrepancy required re-calibration before the tank could be returned to receipt service [1].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0328)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[2] Pipeline_Incident_Report_Hassan_Segment.pdf, page/sheet 1** (fused score: 0.0323)

> Pipeline Incident Report - Hassan Pumping Station
Segment
Report No: PIR-2026-007 | Segment: Mangalore-Hassan (Petronet MHB, 363 km corridor) | Date:
2026-07-22
1. Incident Summary
A pressure drop of 4.2 kg/cm2 was recorded at the Hassan pumping station (intermediate station on
the Mangalore-Hassan-Neriya-Devangonthi corridor) at 03:14 hrs on 2026-07-22. Automatic line
shutdown triggered per the pipeline SCADA logic. Field inspection identified a minor seal leak at pump
P-HS-02 discharge flange. No product loss to the environment was recorded; the leak was contained
within the bunded pump pad area.
2. Incident History by Segment
3. Corrective Actions
Action Owner Target Date Status
Replace P-HS-02 discharge flange gasket Pipeline Maintenance 2026-07-24 Closed
Inspect all pump seals at Hassan station Pipeline Maintenance 2026-08-05 Closed
Review seal replacement interval SOP for HassParno/cNeesrsiy Ea nsgtaintieoenrsing 2026-09-01 In Progress
4. Reference


**[3] Aromatic_Complex_Benzene_Safety_Circular.docx** (fused score: 0.0310)

> HSE Safety Circular No. SC-2026-011
Unit: Aromatic Complex (MSEZ)   |   Classification: Confidential - Internal Use   |   Issue Date: 2026-05-02
Subject: Benzene Exposure Control - Storage Tank Farm TK-701 to TK-704
1. Background
This circular reiterates mandatory exposure control measures for personnel working in or near the Benzene storage and loading area (TK-701 to TK-704) within the Aromatic Complex. Benzene is classified as a Category 1 carcinogen. All requirements below are mandatory and supersede general area PPE guidance for this specific zone.
2. Exposure Limits
Exposure Metric	Limit	Action if Exceeded
8-hour TWA (Time Weighted Average)	1 ppm	Immediate area evacuation, HSE incident report within 4 hours
Short-Term Exposure Limit (STEL, 15 min)	5 ppm	Area evacuation, personal monitor review
Fixed gas detector alarm threshold	0.5 ppm	Automatic area alarm + PA announcement
3. Mandatory Controls
Personal benzene dosimeter badges worn at all times within the tank farm boundary, logged out/in at the HSE gate register.
Supplied-air respiratory protection required for any tank-top gauging, sampling, or connection/disconnection of loading arms.
No hot work within 30 metres of TK-701 to TK-704 without an active Hot Work Permit co-signed by the Aromatic Complex Shift Supervisor and HSE.
Continuous fixed benzene detection required to be in-service before any loading operation commences; loading is prohibited if any detector in the zone is under maintenance without an approved compensatory monitoring plan.
4. Reference Documents
SOP-221 (Benzene Loading Arm Operation), SOP-225 (Confined Space Entry - Aromatic Complex), HSE Manual Section 7.4 (Carcinogen Management)
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[4] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 2** (fused score: 0.0301)

> approximately 40 minutes before DCS alarm response. Batch downgraded to off-spec inventory; grade
changeover checklist (see SOP reference) updated to add a hold point at the 20-minute mark for
feed-rate confirmation.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[5] Inspection_Report_CCR1_Regeneration_Cycle.pdf, page/sheet 1** (fused score: 0.0299)

> Inspection Report: CCR-1 Regeneration Cycle 18
Report No: IR-CCR1-2026-018 | Unit: CCR-1 (Continuous Catalytic Reformer) | Inspection Date:
2026-08-11
1. Summary of Findings
Regeneration Cycle 18 completed in 34 hours, exceeding the normal target of 28 hours by 6 hours.
This is the second consecutive cycle showing extended duration (Cycle 17: 31 hours, Cycle 18: 34
hours), following three cycles within normal range. Preliminary root cause: reduced chlorination
efficiency attributed to moisture ingress in the regeneration gas circuit, under investigation by the
Process Engineering team.
2. Cycle Duration Trend
3. Key Parameters at Cycle Completion
Parameter Cycle 17 Cycle 18 Normal Range
Coke Burn Rate (kg/hr) 142 128 135 - 155
Regeneration Gas O2 (%) 0.6 0.5 0.5 - 1.0
Chlorination Efficiency (%) 91 84 90 - 96
Catalyst Chloride Retention (%) 0.92 0.85 0.9 - 1.1
Bed Outlet Temp (°C) 482 478 470 - 490


---

## Q5. What was the root cause of the Hassan pumping station incident on 2026-07-22?

**Expected answer:** Minor seal leak at pump P-HS-02 discharge flange

**Expected source:** Pipeline_Incident_Report_Hassan_Segment.pdf


**Actual answer (full, verbatim):**

The root cause of the Hassan pumping station incident on 2026-07-22 was a minor seal leak at pump P-HS-02 discharge flange. [1]


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Pipeline_Incident_Report_Hassan_Segment.pdf, page/sheet 1** (fused score: 0.0328)

> Pipeline Incident Report - Hassan Pumping Station
Segment
Report No: PIR-2026-007 | Segment: Mangalore-Hassan (Petronet MHB, 363 km corridor) | Date:
2026-07-22
1. Incident Summary
A pressure drop of 4.2 kg/cm2 was recorded at the Hassan pumping station (intermediate station on
the Mangalore-Hassan-Neriya-Devangonthi corridor) at 03:14 hrs on 2026-07-22. Automatic line
shutdown triggered per the pipeline SCADA logic. Field inspection identified a minor seal leak at pump
P-HS-02 discharge flange. No product loss to the environment was recorded; the leak was contained
within the bunded pump pad area.
2. Incident History by Segment
3. Corrective Actions
Action Owner Target Date Status
Replace P-HS-02 discharge flange gasket Pipeline Maintenance 2026-07-24 Closed
Inspect all pump seals at Hassan station Pipeline Maintenance 2026-08-05 Closed
Review seal replacement interval SOP for HassParno/cNeesrsiy Ea nsgtaintieoenrsing 2026-09-01 In Progress
4. Reference


**[2] Pipeline_Segment_Map_Mangalore_Hassan.png** (fused score: 0.0308)

> Petronet MHB Pipeline Corridor - Segment Map (Illustrative)
ngalore
Hassan
Neriya
Devangont
origin)
Pumping Station
Station
(Bangalore
Mangalore-Hassan
Hassan-Neriya
Neriya-Devangonthi
~156 km
~110 km
~97 km
363 km total corridor. Note: distances illustrative for demo/test purposes.


**[3] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0308)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[4] Pipeline_Incident_Report_Hassan_Segment.pdf, page/sheet 2** (fused score: 0.0306)

> Applicable SOP: Pipeline Emergency Shutdown and Restart Procedure
(Mangalore-Hassan-Neriya-Devangonthi corridor). This report links to Equipment ID P-HS-02 and
PipelineSegment 'Mangalore-Hassan' in the knowledge graph.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[5] Aromatic_Complex_Benzene_Safety_Circular.docx** (fused score: 0.0306)

> HSE Safety Circular No. SC-2026-011
Unit: Aromatic Complex (MSEZ)   |   Classification: Confidential - Internal Use   |   Issue Date: 2026-05-02
Subject: Benzene Exposure Control - Storage Tank Farm TK-701 to TK-704
1. Background
This circular reiterates mandatory exposure control measures for personnel working in or near the Benzene storage and loading area (TK-701 to TK-704) within the Aromatic Complex. Benzene is classified as a Category 1 carcinogen. All requirements below are mandatory and supersede general area PPE guidance for this specific zone.
2. Exposure Limits
Exposure Metric	Limit	Action if Exceeded
8-hour TWA (Time Weighted Average)	1 ppm	Immediate area evacuation, HSE incident report within 4 hours
Short-Term Exposure Limit (STEL, 15 min)	5 ppm	Area evacuation, personal monitor review
Fixed gas detector alarm threshold	0.5 ppm	Automatic area alarm + PA announcement
3. Mandatory Controls
Personal benzene dosimeter badges worn at all times within the tank farm boundary, logged out/in at the HSE gate register.
Supplied-air respiratory protection required for any tank-top gauging, sampling, or connection/disconnection of loading arms.
No hot work within 30 metres of TK-701 to TK-704 without an active Hot Work Permit co-signed by the Aromatic Complex Shift Supervisor and HSE.
Continuous fixed benzene detection required to be in-service before any loading operation commences; loading is prohibited if any detector in the zone is under maintenance without an approved compensatory monitoring plan.
4. Reference Documents
SOP-221 (Benzene Loading Arm Operation), SOP-225 (Confined Space Entry - Aromatic Complex), HSE Manual Section 7.4 (Carcinogen Management)
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


---

## Q6. Did any PSA unit fall below its purity target in the last reporting period?

**Expected answer:** Yes, PSA-3, in the final 3 weeks of the log

**Expected source:** PSA_Hydrogen_Purity_Trend_Log.xlsx


**Actual answer (full, verbatim):**

Yes, PSA-3 fell below its purity target of 99.9% during the final weeks of the reporting period. Specifically:

- On 2026-08-09, PSA-3 Purity was 99.641%, which is below the target.
- This trend continued with further declines on subsequent dates: 
  - On 2026-08-16, PSA-3 Purity was 99.63%.
  - On 2026-08-23, PSA-3 Purity was 99.633%.

This downward drift in purity for PSA-3 was noted as a deliberate test case in the provided synthetic data [1][3].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] PSA_Hydrogen_Purity_Trend_Log.xlsx, page/sheet 1** (fused score: 0.0325)

> Synthetic test data. PSA-3 purity shows a deliberate downward drift in the final 3 weeks, intended as a test case for trend-detection / anomaly-flagging RAG queries.				
[Chart: PSA Hydrogen Purity Trend vs 99.9% Target, type=LineChart]
  PSA-1 Purity (%): 2026-06-07=99.914, 2026-06-14=99.872, 2026-06-21=99.939, 2026-06-28=99.853, 2026-07-05=99.853, 2026-07-12=99.904, 2026-07-19=99.931, 2026-07-26=99.92, 2026-08-02=99.946, 2026-08-09=99.86, 2026-08-16=99.931, 2026-08-23=99.947
  PSA-2 Purity (%): 2026-06-07=99.803, 2026-06-14=99.896, 2026-06-21=99.811, 2026-06-28=99.828, 2026-07-05=99.826, 2026-07-12=99.829, 2026-07-19=99.801, 2026-07-26=99.844, 2026-08-02=99.844, 2026-08-09=99.91, 2026-08-16=99.895, 2026-08-23=99.849


**[2] PSA_Hydrogen_Purity_Trend_Log.xlsx, page/sheet 1** (fused score: 0.0318)

> Sheet: PSA Purity Trend
PSA Hydrogen Purity Trend Log - Units 1, 2, 3 (12-Week Rolling, Synthetic Test Data)				
				
Week Ending	PSA-1 Purity (%)	PSA-2 Purity (%)	PSA-3 Purity (%)	Target (%)
2026-06-07	99.914	99.803	99.853	99.9
2026-06-14	99.872	99.896	99.901	99.9
2026-06-21	99.939	99.811	99.871	99.9
2026-06-28	99.853	99.828	99.881	99.9
2026-07-05	99.853	99.826	99.898	99.9
2026-07-12	99.904	99.829	99.891	99.9
2026-07-19	99.931	99.801	99.917	99.9
2026-07-26	99.92	99.844	99.839	99.9
2026-08-02	99.946	99.844	99.831	99.9
2026-08-09	99.86	99.91	99.641	99.9
2026-08-16	99.931	99.895	99.63	99.9
2026-08-23	99.947	99.849	99.633	99.9
				
				
PSA Downtime Cause	Hours (Q3 2026)			
Adsorbent Bed Degradation (PSA-3)	14			
Valve Cycling Fault	5.5			
Instrument Air Loss	2			
Scheduled Maintenance	6.5			
				
				
Synthetic test data. PSA-3 purity shows a deliberate downward drift in the final 3 weeks, intended as a test case for trend-detection / anomaly-flagging RAG queries.				
[Chart: PSA Hydrogen Purity Trend vs 99.9% Target, type=LineChart]


**[3] PSA_Hydrogen_Purity_Trend_Log.xlsx, page/sheet 1** (fused score: 0.0306)

> PSA-3 Purity (%): 2026-06-07=99.853, 2026-06-14=99.901, 2026-06-21=99.871, 2026-06-28=99.881, 2026-07-05=99.898, 2026-07-12=99.891, 2026-07-19=99.917, 2026-07-26=99.839, 2026-08-02=99.831, 2026-08-09=99.641, 2026-08-16=99.63, 2026-08-23=99.633
  Target (%): 2026-06-07=99.9, 2026-06-14=99.9, 2026-06-21=99.9, 2026-06-28=99.9, 2026-07-05=99.9, 2026-07-12=99.9, 2026-07-19=99.9, 2026-07-26=99.9, 2026-08-02=99.9, 2026-08-09=99.9, 2026-08-16=99.9, 2026-08-23=99.9
[Chart: PSA Downtime Causes - Q3 2026, type=PieChart]
  Hours (Q3 2026): Adsorbent Bed Degradation (PSA-3)=14.0, Valve Cycling Fault=5.5, Instrument Air Loss=2.0, Scheduled Maintenance=6.5


**[4] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0301)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[5] Pipeline_Incident_Report_Hassan_Segment.pdf, page/sheet 1** (fused score: 0.0292)

> Pipeline Incident Report - Hassan Pumping Station
Segment
Report No: PIR-2026-007 | Segment: Mangalore-Hassan (Petronet MHB, 363 km corridor) | Date:
2026-07-22
1. Incident Summary
A pressure drop of 4.2 kg/cm2 was recorded at the Hassan pumping station (intermediate station on
the Mangalore-Hassan-Neriya-Devangonthi corridor) at 03:14 hrs on 2026-07-22. Automatic line
shutdown triggered per the pipeline SCADA logic. Field inspection identified a minor seal leak at pump
P-HS-02 discharge flange. No product loss to the environment was recorded; the leak was contained
within the bunded pump pad area.
2. Incident History by Segment
3. Corrective Actions
Action Owner Target Date Status
Replace P-HS-02 discharge flange gasket Pipeline Maintenance 2026-07-24 Closed
Inspect all pump seals at Hassan station Pipeline Maintenance 2026-08-05 Closed
Review seal replacement interval SOP for HassParno/cNeesrsiy Ea nsgtaintieoenrsing 2026-09-01 In Progress
4. Reference


---

## Q7. Which Kero Merox sample exceeded the sulphur spec limit?

**Expected answer:** 2026-08-19, 11.2 ppm vs 10 ppm limit

**Expected source:** Sulphur_Spec_Compliance_LabSheet.xlsx


**Actual answer (full, verbatim):**

The Kero Merox sample that exceeded the sulphur spec limit was taken on 2026-08-19, with a Sulphur content of 11.2 ppm, which exceeds the Spec Limit of 10 ppm [1].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Sulphur_Spec_Compliance_LabSheet.xlsx, page/sheet 1** (fused score: 0.0328)

> Sheet: Sulphur Compliance
Merox Units - Sulphur Content Compliance Lab Sheet (Synthetic Test Data)					
					
Sample Date	Unit	Product	Sulphur (ppm)	Spec Limit (ppm)	Status
2026-08-01	LPG Merox	LPG	3.2	10	OK
2026-08-05	Kero Merox	SKO	6.8	10	OK
2026-08-08	LPG Merox	LPG	4.1	10	OK
2026-08-12	Kero Merox	SKO	9.4	10	NEAR LIMIT
2026-08-15	LPG Merox	LPG	8.9	10	NEAR LIMIT
2026-08-19	Kero Merox	SKO	11.2	10	EXCEEDANCE
2026-08-22	LPG Merox	LPG	2.7	10	OK
2026-08-26	Kero Merox	SKO	5.5	10	OK
					
					
Synthetic test data. Row for 2026-08-19 (Kero Merox) is a deliberate spec exceedance, intended as a test case for compliance-checking / near-limit-flagging RAG queries.					
[Chart: Sulphur Readings vs Spec Limit (10 ppm), type=BarChart]
  Sulphur (ppm): 2026-08-01=3.2, 2026-08-05=6.8, 2026-08-08=4.1, 2026-08-12=9.4, 2026-08-15=8.9, 2026-08-19=11.2, 2026-08-22=2.7, 2026-08-26=5.5
  Spec Limit (ppm): 2026-08-01=10.0, 2026-08-05=10.0, 2026-08-08=10.0, 2026-08-12=10.0, 2026-08-15=10.0, 2026-08-19=10.0, 2026-08-22=10.0, 2026-08-26=10.0


**[2] Maintenance_Log_Q3_2026.xlsx, page/sheet 1** (fused score: 0.0320)

> Sheet: Maintenance Log Q3 2026
MRPL Maintenance Log - Q3 2026 (Jul-Sep, Synthetic Test Data)					
					
Equipment ID	Unit	Fault Category	Downtime (hrs)	Work Order	Date Closed
R-201	Hydrocracker-2	Catalyst-Related	18.5	WO-30411	2026-07-14
R-101	Hydrocracker-1	Mechanical	6	WO-30422	2026-07-19
K-201	Hydrocracker-2	Mechanical	9.5	WO-30455	2026-08-02
CCR-1 Regen	CCR-1	Instrumentation	4	WO-30460	2026-08-05
CCR-2 Regen	CCR-2	Process Upset	12	WO-30478	2026-08-11
Merox-LPG	LPG Merox	Electrical	3	WO-30490	2026-08-14
Merox-Kero	Kero Merox	Instrumentation	5.5	WO-30501	2026-08-20
PSA-1	Hydrogen Unit 1	Mechanical	7	WO-30512	2026-08-25
PSA-2	Hydrogen Unit 2	Process Upset	2.5	WO-30523	2026-08-29
PSA-3	Hydrogen Unit 3	Instrumentation	4.5	WO-30534	2026-09-03
Novolen-Ext1	Polypropylene Plant	Mechanical	15	WO-30545	2026-09-09
AC-Comp1	Aromatic Complex	Electrical	6.5	WO-30556	2026-09-15
					
		Total Downtime (hrs):	94		
					
					
Fault Category	Total Downtime (hrs)				
Mechanical	37.5				
Electrical	9.5				
Instrumentation	14				
Process Upset	14.5				
Catalyst-Related	18.5				
					
					
Synthetic test data generated for RAG/retrieval accuracy testing. Not actual MRPL maintenance records.					
[Chart: Downtime by Fault Category (Q3 2026), type=PieChart]


**[3] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0313)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[4] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 1** (fused score: 0.0302)

> Novolen Polypropylene Plant - Monthly Batch QA
Report
Report Period: August 2026 | Plant Capacity: 440 KTA (Novolen Gas-Phase, Ziegler-Natta)
1. Production Mix
2. Batch Quality Summary
Grade Batches ProduceAdvg MFI (g/10minS)pec MFI RangeDensity (g/cm3) Off-Spec Batches
Homopolymer H030SG 22 3.4 3.0 - 3.8 0.905 0
Homopolymer H110F 16 11.2 10.0 - 12.0 0.905 1
Random Copolymer RP340 12 3.9 3.5 - 4.5 0.900 0
Impact Copolymer HP500 9 0.8 0.6 - 1.0 0.900 0
3. Off-Spec Batch Detail
Batch H110F-0847 (produced 2026-08-17) recorded MFI of 12.9 g/10min, above the upper spec limit of
12.0. Root cause: catalyst feed rate excursion during grade changeover from H030SG, duration


**[5] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0301)

> 4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.
4.5 Fresh catalyst loading (dense loading method) to the bed density specified in the catalyst vendor's Technical Data Sheet, batch-verified against the Certificate of Analysis.
4.6 Catalyst sulfiding (activation) per the sulfiding curve in Appendix A - typical duration 36-48 hours.
4.7 Gradual introduction of feed, WABT ramp not exceeding 15°C/hour until target conversion is reached.
4.8 Post-changeout performance verification against Section 3 parameters for 72 continuous hours before the unit is declared in normal service.
5. Safety Precautions
Pyrophoric catalyst hazard: spent NiMo catalyst can self-heat on air exposure. Unloading must proceed under continuous nitrogen blanket or water-wetting per vendor guidance. Full-face supplied-air respirators are mandatory for all vessel-entry personnel. H2S monitoring is continuous throughout Sections 4.3-4.4.
6. Revision History
Revision	Date	Description of Change	Approved By
Rev 1	2021-06-02	Initial issue	Process Safety Group
Rev 2	2023-11-18	Updated WABT end-of-run trigger from 405 to 410 °C based on catalyst vendor guidance	Process Safety Group
Rev 3	2026-03-14	Added Section 5 pyrophoric hazard precautions; added Form F-114-A reference	HSE + Process Safety Group
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


---

## Q8. Which vendor supplies both the hydrocracker catalyst and the Ziegler-Natta catalyst component?

**Expected answer:** VEND-1042

**Expected source:** SAP_Mock_Materials_Master_Export.xlsx


**Actual answer (full, verbatim):**

Vendor code VEND-1042 supplies both the hydrocracker catalyst (NiMo Hydrocracking Catalyst) and the Ziegler-Natta Catalyst Component for the Novolen Plant, according to the material master export data provided [4].


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0323)

> SOP-114: Hydrocracker Catalyst Changeout Procedure
Document No: SOP-114-Rev3   |   Unit: Hydrocracker-2 (HCU-2)   |   Effective Date: 2026-03-14   |   Review Cycle: 24 months
1. Purpose
This procedure defines the safe sequence of operations for changing out spent hydrocracking catalyst in HCU-2 Reactor R-201, including bed unloading, sulfiding of fresh catalyst, and return-to-service checks. This SOP applies specifically to the NiMo-alumina extrudate catalyst system currently qualified for HCU-2 service.
2. Scope and Applicability
Applies to: HCU-2 Reactor R-201 (Beds 1-3), associated recycle gas compressor K-201, and feed/effluent heat exchanger train E-201A/B. Does not apply to HCU-1 (R-101), which uses a different catalyst loading pattern under SOP-098.
3. Key Process Parameters (Reference Values)
The table below lists the normal operating envelope used to judge catalyst end-of-run:
Parameter	Normal Range	End-of-Run Trigger	Unit
Weighted Average Bed Temperature (WABT)	365 - 385	> 410	°C
LHSV (Liquid Hourly Space Velocity)	1.1 - 1.4	N/A (design basis)	hr⁻¹
Reactor Delta-P (Bed 2)	0.8 - 1.5	> 3.5	kg/cm²
Conversion (360°C+ fraction)	68 - 72	< 60	%
Recycle Gas H2 Purity	92 - 95	< 88	%
Catalyst Cycle Length (design)	22 - 26	N/A	months
4. Changeout Sequence
4.1 Unit shutdown and depressurization of R-201 per SOP-050 (Reactor Depressurization).
4.2 Nitrogen purge to < 0.5% hydrocarbon (LEL meter confirmation) before vessel entry permit is issued.
4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.


**[2] SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx** (fused score: 0.0315)

> 4.3 Spent catalyst unloading via vacuum system, Beds 1-3 in sequence, with continuous H2S monitoring in the confined space.
4.4 Internals inspection: distributor trays, quench zones, thermocouple wells - findings logged on Form F-114-A.
4.5 Fresh catalyst loading (dense loading method) to the bed density specified in the catalyst vendor's Technical Data Sheet, batch-verified against the Certificate of Analysis.
4.6 Catalyst sulfiding (activation) per the sulfiding curve in Appendix A - typical duration 36-48 hours.
4.7 Gradual introduction of feed, WABT ramp not exceeding 15°C/hour until target conversion is reached.
4.8 Post-changeout performance verification against Section 3 parameters for 72 continuous hours before the unit is declared in normal service.
5. Safety Precautions
Pyrophoric catalyst hazard: spent NiMo catalyst can self-heat on air exposure. Unloading must proceed under continuous nitrogen blanket or water-wetting per vendor guidance. Full-face supplied-air respirators are mandatory for all vessel-entry personnel. H2S monitoring is continuous throughout Sections 4.3-4.4.
6. Revision History
Revision	Date	Description of Change	Approved By
Rev 1	2021-06-02	Initial issue	Process Safety Group
Rev 2	2023-11-18	Updated WABT end-of-run trigger from 405 to 410 °C based on catalyst vendor guidance	Process Safety Group
Rev 3	2026-03-14	Added Section 5 pyrophoric hazard precautions; added Form F-114-A reference	HSE + Process Safety Group
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[3] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 1** (fused score: 0.0315)

> Novolen Polypropylene Plant - Monthly Batch QA
Report
Report Period: August 2026 | Plant Capacity: 440 KTA (Novolen Gas-Phase, Ziegler-Natta)
1. Production Mix
2. Batch Quality Summary
Grade Batches ProduceAdvg MFI (g/10minS)pec MFI RangeDensity (g/cm3) Off-Spec Batches
Homopolymer H030SG 22 3.4 3.0 - 3.8 0.905 0
Homopolymer H110F 16 11.2 10.0 - 12.0 0.905 1
Random Copolymer RP340 12 3.9 3.5 - 4.5 0.900 0
Impact Copolymer HP500 9 0.8 0.6 - 1.0 0.900 0
3. Off-Spec Batch Detail
Batch H110F-0847 (produced 2026-08-17) recorded MFI of 12.9 g/10min, above the upper spec limit of
12.0. Root cause: catalyst feed rate excursion during grade changeover from H030SG, duration


**[4] SAP_Mock_Materials_Master_Export.xlsx, page/sheet 1** (fused score: 0.0309)

> Sheet: Materials Master (Mock)
SAP Materials Master - Mock Export (Structured to Match Real SAP MARA/MARC Shape, Synthetic Data)							
							
Material No.	Material Description	Category	Unit (Plant)	Vendor Code	Stock Qty (UoM)	Unit Value (Rs.)	Line Value (Rs.)
MAT-100234	NiMo Hydrocracking Catalyst (Extrudate)	Catalysts	Hydrocracker-2	VEND-1042	12	480000	5760000
MAT-100567	CCR Platinum-Rhenium Catalyst	Catalysts	CCR-1	VEND-1077	8	950000	7600000
MAT-200112	Control Valve, 6-inch, Class 600	Spare Parts	Hydrocracker-1	VEND-2033	25	62000	1550000
MAT-200334	Pressure Transmitter, 4-20mA	Instrumentation	PSA Unit 2	VEND-2091	40	18500	740000
MAT-300021	Amine Solution (MDEA, 45%)	Chemicals	LPG Merox	VEND-3010	5000	145	725000
MAT-300088	Ziegler-Natta Catalyst Component	Catalysts	Novolen Plant	VEND-1042	15	620000	9300000
MAT-400015	Carbon Steel Piping, Sch 40, 8-inch	Piping	Aromatic Complex	VEND-4021	300	3200	960000
MAT-400099	Supplied-Air Respirator Set	Safety Equipment	Aromatic Complex	VEND-5001	60	21000	1260000
MAT-500044	Recycle Gas Compressor Seal Kit	Spare Parts	Hydrocracker-2	VEND-2033	6	340000	2040000
MAT-500210	Fixed Benzene Gas Detector	Safety Equipment	Aromatic Complex	VEND-5001	18	95000	1710000
							
							
Category	Item Count						
Catalysts	3						
Spare Parts	2						
Instrumentation	1						
Chemicals	1						
Piping	1						
Safety Equipment	2						
							
							
Vendor Code	Total Inventory Value (Rs.)						
VEND-1042	15060000						
VEND-1077	7600000


**[5] SAP_Mock_Materials_Master_Export.xlsx, page/sheet 1** (fused score: 0.0305)

> Instrumentation	1						
Chemicals	1						
Piping	1						
Safety Equipment	2						
							
							
Vendor Code	Total Inventory Value (Rs.)						
VEND-1042	15060000						
VEND-1077	7600000						
VEND-2033	3590000						
VEND-2091	740000						
VEND-3010	725000						
VEND-4021	960000						
VEND-5001	2970000						
							
							
Fully synthetic mock data structured to resemble real SAP MARA/MARC material master shape. Vendor codes and material numbers are fictional placeholders, not real MRPL vendor identities. Generated for RAG/retrieval accuracy testing.							
[Chart: Material Category Mix (Item Count), type=PieChart]
  Item Count: Catalysts=3.0, Spare Parts=2.0, Instrumentation=1.0, Chemicals=1.0, Piping=1.0, Safety Equipment=2.0
[Chart: Total Inventory Value by Vendor (Rs.), type=BarChart]
  Total Inventory Value (Rs.): VEND-1042=15060000.0, VEND-1077=7600000.0, VEND-2033=3590000.0, VEND-2091=740000.0, VEND-3010=725000.0, VEND-4021=960000.0, VEND-5001=2970000.0


---

## Q9. What is MRPL's crude oil sourcing strategy for 2027?

**Expected answer:** Not found in the provided corpus — out-of-corpus negative test case for RAG_SPEC.md §3's refusal behavior

**Expected source:** None — negative test case


**Actual answer (full, verbatim):**

The sources provided do not contain information regarding MRPL's crude oil sourcing strategy for 2027. Therefore, I cannot answer this question based on the given documents.


**Grounding gate:** `found=True`


**Retrieved source passages (top 5, full text):**


**[1] Novolen_Batch_QA_Report_Aug2026.pdf, page/sheet 2** (fused score: 0.0320)

> approximately 40 minutes before DCS alarm response. Batch downgraded to off-spec inventory; grade
changeover checklist (see SOP reference) updated to add a hold point at the 20-minute mark for
feed-rate confirmation.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[2] Correspondence_Depot_HQ_Thread_Kasargod.docx** (fused score: 0.0318)

> Correspondence Thread: Kasargod Depot - Tank Calibration Discrepancy
Thread ID: CORR-KGD-2026-0091   |   Depot: Kasargod (Kerala)   |   Status: Pending HQ Approval
From: S. Nair (Depot Manager, Kasargod)    To: Marketing Ops, HQ Mangalore    Date: 2026-04-11 09:14
During the scheduled quarterly tank calibration for Tank TK-K-03 (MS storage, 500 KL nominal), the third-party calibration agency's dip-chart figures show a variance of 0.6% against the previous calibration certificate. Requesting guidance on whether this falls within acceptable tolerance or requires re-calibration before the tank is returned to receipt service.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-12 11:02
0.6% variance is above our internal tolerance of 0.3% for MS tanks per the Depot Operations Manual Section 5.2. Please hold TK-K-03 out of receipt service and arrange re-calibration. Confirm the calibration agency's accreditation certificate is current before proceeding.
---
From: S. Nair (Depot Manager, Kasargod)    To: R. Kamath, HQ    Date: 2026-04-14 15:47
Noted, TK-K-03 held out of service effective today. Calibration agency accreditation confirmed valid until Dec 2027. Re-calibration scheduled for 2026-04-20. Requesting temporary receipt allocation to TK-K-01 and TK-K-02 in the interim to avoid disrupting the coastal tanker schedule.
---
From: R. Kamath (Marketing Ops Manager, HQ)    To: S. Nair, Kasargod    Date: 2026-04-14 16:30
Approved - temporary reallocation to TK-K-01/02 for the interim period. Please submit the updated re-calibration certificate to HQ Marketing Ops within 48 hours of completion for the tank to be cleared back into service.
---
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL internal document.


**[3] Pipeline_Incident_Report_Hassan_Segment.pdf, page/sheet 2** (fused score: 0.0315)

> Applicable SOP: Pipeline Emergency Shutdown and Restart Procedure
(Mangalore-Hassan-Neriya-Devangonthi corridor). This report links to Equipment ID P-HS-02 and
PipelineSegment 'Mangalore-Hassan' in the knowledge graph.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.


**[4] Maintenance_Log_Q3_2026.xlsx, page/sheet 1** (fused score: 0.0297)

> Catalyst-Related	18.5				
					
					
Synthetic test data generated for RAG/retrieval accuracy testing. Not actual MRPL maintenance records.					
[Chart: Downtime by Fault Category (Q3 2026), type=PieChart]
  Total Downtime (hrs): Mechanical=37.5, Electrical=9.5, Instrumentation=14.0, Process Upset=14.5, Catalyst-Related=18.5
[Chart: Downtime by Equipment (hrs) - Q3 2026, type=BarChart]
  Downtime (hrs): R-201=18.5, R-101=6.0, K-201=9.5, CCR-1 Regen=4.0, CCR-2 Regen=12.0, Merox-LPG=3.0, Merox-Kero=5.5, PSA-1=7.0, PSA-2=2.5, PSA-3=4.5, Novolen-Ext1=15.0, AC-Comp1=6.5


**[5] Inspection_Report_CCR1_Regeneration_Cycle.pdf, page/sheet 2** (fused score: 0.0296)

> 4. Recommendations
- Inspect regeneration gas dryer (D-102) desiccant bed condition before Cycle 19.
- Verify moisture analyzer AI-4471 calibration - last calibrated 2026-02-10 (over 6 months).
- If Cycle 19 duration again exceeds 30 hours, escalate to a full chlorination system review per
SOP-140.
This is a synthetic, illustrative document generated for RAG/retrieval testing purposes. It does not represent an actual MRPL
internal document.
