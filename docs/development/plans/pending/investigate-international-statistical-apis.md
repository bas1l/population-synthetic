# Plan: Investigate International Statistical APIs (SCB Equivalents)

**Date:** 2026-05-10
**Author:** Basil
**Status:** Investigation complete — batch 1 (20 countries), batch 2 (24 countries), batch 3 (29 countries — all remaining Asia + Africa + Americas). 73 jurisdictions covered. Candidate pool exhausted. See [findings](investigate-international-statistical-apis-findings.md).
**Base Branch:** `feature/configurable-identity-pipeline`
**Branch:** N/A (research-only — no code changes)

---

## Overview

The SCB population generator is hard-wired to Statistics Sweden's PxWeb API. To make the synthetic population generator portable, we need to identify equivalent national statistical APIs in other countries and assess their feasibility as drop-in (or adapter-based) replacements.

This investigation runs in **batches of up to 30 countries at a time**, each batch dispatched as one background research agent per country. After each batch, the findings document is appended and the synthesis (tier rankings, recommended pilots) is refreshed.

## Problem Statement

`anxiety_synthetic/utils/scb_client.py` and `anxiety_synthetic/scb_population/fetch_service.py` are tightly coupled to SCB-specific table IDs (`BE0101`, `UF0506`, `AM0401P`, …), Swedish variable codes (`Alder`, `Kon`, `Region`), and Swedish classifications (SUN2020, SNI2007, AKU, läns codes). To support other countries we need (a) a clear inventory of what each national API actually exposes, (b) a feasibility ranking, and (c) a recommended pilot for the first non-Swedish implementation.

## Goals

### In Scope
1. Identify each candidate country's national statistical office and its programmatic API.
2. For every country, document the same 9 facets: API URL, technology stack, auth/limits, coverage of the 16 SCB dimensions, classifications used, an example query, Python wrappers, blockers, and a feasibility verdict (HIGH / MEDIUM / LOW).
3. Maintain a tier ranking (drop-in PxWeb family / adapter required / significant work / not viable) that grows with each batch.
4. Recommend a pilot country for the first non-Swedish adapter once at least one HIGH-feasibility country is documented.

### Out of Scope
- Implementing any adapter, refactor, or `PxWebClient` base class — that is a separate plan once a pilot country is chosen.
- Building the SUN2020↔ISCED, SNI2007↔NACE, etc. classification crosswalks — also a separate plan.
- Microdata access negotiations with national statistical offices.
- Any code change to `anxiety_synthetic/scb_population/` or `anxiety_synthetic/utils/scb_client.py`.

## Success Criteria

- [x] Batch 1 (20 countries) complete with full reports.
- [x] Batch 2 (24 countries) dispatched and completed.
- [x] Batch 3 (29 countries) dispatched and completed.
- [x] Each completed country has a 9-facet report in the findings document.
- [x] Tier ranking refreshed after each batch.
- [ ] Once a HIGH-feasibility pilot country is selected, an implementation plan is opened in `pending/`.

---

## Methodology

### The 16 reference dimensions (SCB baseline)

Every country report assesses coverage of these dimensions from `anxiety_synthetic/scb_population/fetch_service.py`:

| # | Dimension | SCB Table | Classification |
|---|---|---|---|
| 1 | Age × Sex (joint) | `BE0101` | 1-year ages, M/F |
| 2 | Education level | `UF0506` | SUN2020 (≈ ISCED) |
| 3 | Employment status | `AM0401P` | AKU (Swedish LFS) |
| 4 | Industry sector | `AM0401I` | SNI2007 (= NACE Rev. 2) |
| 5 | Employment type | `AM0401I` | Permanent / temp / self-emp |
| 6 | Working hours | `AM0401S` | 1-19h / 20-34h / 35+h |
| 7 | Income source / decile | `HE0110` | D1–D10 + 6 components |
| 8 | Housing tenure | `BO0104` | Owner / rental / bostadsrätt |
| 9 | Household size | `BE0101S` | 1P–7+P |
| 10 | Civil status | `BE0101` | OG/G/ÄNKL/SK |
| 11 | Region (county) | `BE0101` | 21 läns (≈ NUTS-3) |
| 12 | Birth location group | `BE0101E` | Sweden / EU / rest of world |
| 13 | Birth country detail | `BE0101E` | Top 20 countries |
| 14 | Parental structure | `LE0102` | Family type |
| 15 | Urbanization | mappings | Urban / suburban / rural |
| 16 | Time series availability | All | Annual, latest available |

### Batch dispatch protocol

1. **Pick up to 30 countries** that are not yet in the findings document.
2. **Spawn one background research agent per country**, each with the prompt template below.
3. **Wait for completion** — agents report back as task-notification events; no polling.
4. **Append each country's report** to `investigate-international-statistical-apis-findings.md` under the appropriate region heading.
5. **Refresh the synthesis section** of the findings document (tier breakdown, pilot recommendation).
6. **Update the country tracker** in this file.

### Agent prompt template

Each background agent receives this prompt (substitute `{COUNTRY}` and `{HINTS}`):

```
Research {COUNTRY}'s national statistics agency API to assess whether it can substitute
for Statistics Sweden (SCB) PxWeb API in a synthetic population generator.

REFERENCE BASELINE (SCB):
- Endpoint: https://api.scb.se/OV0104/v1/doris/en/ssd/
- Protocol: PxWeb POST queries returning JSON-STAT v2
- No authentication; cached locally
- Used to fetch 16 demographic dimensions

YOUR TASK: Research {COUNTRY}'s equivalent ({HINTS — name of NSO + likely API names + relevant search terms}).
Use web search heavily.

INVESTIGATE:
1. Name and URL of the country's national statistics office and its public API
2. API technology (PxWeb? REST? JSON-stat? CSV-only? GraphQL? SDMX?)
3. Authentication, rate limits, registration requirements
4. Coverage of each of the 16 dimensions [list dimensions 1–16 above] (mark ✓/partial/✗ + 1-line evidence)
5. Classification systems used (ISCED for education? NACE for industry? Local equivalents?)
6. One concrete example query (URL + parameters) for age × sex distribution
7. Known Python SDK/wrapper packages
8. Blockers / gotchas (only aggregated data? English documentation? auth friction?)
9. Overall feasibility score: HIGH / MEDIUM / LOW for substituting SCB

Return a structured report under 500 words with EXACT sections:
## {COUNTRY}
**API name & URL:**
**Technology stack:**
**Auth/limits:**
**Coverage table:** (16 rows)
**Classifications:**
**Example query:**
**Python wrappers:**
**Blockers:**
**Feasibility verdict:** HIGH/MEDIUM/LOW — 1-sentence rationale
```

### Output format

The findings file groups country reports by region. Each report follows the 9-section structure above.

---

## Country Tracker

### Batch 1 — completed (20 countries, 2026-05-10)

**Europe:** Denmark ✅ | Finland ✅ | Norway ✅ | Iceland ✅ | Germany ✅ | France ✅ | UK ✅ | Ireland ✅ | Netherlands ✅ | Spain ✅ | Italy ✅
**Anglophone:** USA ✅ | Canada ✅ | Australia ✅
**Asia:** Japan ✅ | South Korea ✅ | India ✅
**Latin America:** Brazil ✅ | Mexico ✅
**Africa:** South Africa ✅

### Batch 2 — completed (24 countries, dispatched 2026-05-10)

**Rest of EU/EEA:** Austria ✅ | Belgium ✅ | Bulgaria ✅ | Croatia ✅ | Cyprus ✅ | Czechia ✅ | Estonia ✅ | Greece ✅ | Hungary ✅ | Latvia ✅ | Lithuania ✅ | Luxembourg ✅ | Malta ✅ | Poland ✅ | Portugal ✅ | Romania ✅ | Slovakia ✅ | Slovenia ✅ | Switzerland ✅
**Non-EU Europe:** Albania ✅ | Serbia ✅ | Ukraine ✅
**Pan-EU fallback:** Eurostat ✅
**Oceania:** New Zealand ✅

### Batch 3 — completed (29 countries, dispatched 2026-05-10)

**Asia (15):** China ✅ | Indonesia ✅ | Vietnam ✅ | Philippines ✅ | Thailand ✅ | Malaysia ✅ | Singapore ✅ | Taiwan ✅ | Pakistan ✅ | Bangladesh ✅ | Iran ✅ | Saudi Arabia ✅ | UAE ✅ | Israel ✅ | Turkey ✅
**Africa (7):** Nigeria ✅ | Kenya ✅ | Egypt ✅ | Morocco ✅ | Ghana ✅ | Ethiopia ✅ | Tanzania ✅
**Americas (7):** Argentina ✅ | Chile ✅ | Colombia ✅ | Peru ✅ | Venezuela ✅ | Uruguay ✅ | Ecuador ✅

### Candidate pool for future batches

These are reasonable next targets, grouped to make batch construction easy. **Do not exceed 30 per batch.** Pick a coherent mix (regional cluster, or "all remaining EU", etc.).

#### Europe (remaining EU/EEA + non-EU)
- Austria — Statistik Austria (STATcube + OGD portal)
- Belgium — Statbel
- Bulgaria — NSI Bulgaria
- Croatia — DZS
- Cyprus — CYSTAT
- Czechia — ČSÚ (VDB)
- Estonia — Statistikaamet (likely PxWeb)
- Greece — ELSTAT
- Hungary — KSH
- Latvia — CSP (likely PxWeb)
- Lithuania — LSD (likely PxWeb)
- Luxembourg — STATEC
- Malta — NSO Malta
- Poland — GUS (BDL)
- Portugal — INE Portugal
- Romania — INSSE / Tempo Online
- Slovakia — ŠÚSR (DATAcube)
- Slovenia — SURS (SI-STAT, likely PxWeb)
- Switzerland — BFS / OFS
- Albania — INSTAT
- Serbia — SORS
- Ukraine — Ukrstat
- Eurostat (pan-EU SDMX — covers any EU country as a fallback)

#### Asia (beyond batch 1)
- China — NBS
- Indonesia — BPS
- Vietnam — GSO
- Philippines — PSA OpenSTAT
- Thailand — NSO
- Malaysia — DOSM (OpenDOSM)
- Singapore — SingStat (Table Builder API)
- Taiwan — DGBAS
- Pakistan — PBS
- Bangladesh — BBS
- Iran — SCI
- Saudi Arabia — GASTAT
- UAE — FCSC
- Israel — CBS Israel
- Turkey — TÜİK

#### Africa
- Nigeria — NBS Nigeria
- Kenya — KNBS
- Egypt — CAPMAS
- Morocco — HCP
- Ghana — GSS
- Ethiopia — ESS
- Tanzania — NBS Tanzania

#### Americas (beyond batch 1)
- Argentina — INDEC
- Chile — INE Chile
- Colombia — DANE
- Peru — INEI
- Venezuela — INE Venezuela
- Uruguay — INE Uruguay
- Ecuador — INEC

#### Oceania
- New Zealand — Stats NZ (NZ.Stat API)

### Suggested batch 2 composition (≤30)

**Theme: rest of EU/EEA + Eurostat fallback** (24 countries):
Austria, Belgium, Bulgaria, Croatia, Cyprus, Czechia, Estonia, Greece, Hungary, Latvia, Lithuania, Luxembourg, Malta, Poland, Portugal, Romania, Slovakia, Slovenia, Switzerland, Albania, Serbia, Ukraine, **Eurostat (pan-EU)**, New Zealand.

This finishes European coverage and adds the Eurostat fallback layer (which is referenced repeatedly in batch 1 synthesis).

---

## How to launch a new batch

1. Pick a batch from the candidate pool (max 30).
2. Update this file's "Country Tracker" with the batch in flight.
3. From a Claude Code session in this repo, ask Claude to launch the batch — Claude will:
   a. Spawn N background `general-purpose` agents (one per country) using the agent prompt template above.
   b. As each task-notification arrives, append the country's report to `investigate-international-statistical-apis-findings.md`.
   c. Once all complete, refresh the **Synthesis** section of the findings document.
4. Mark the batch ✅ in the tracker.
5. If a new HIGH-feasibility country looks like a better pilot than the current recommendation, update the pilot recommendation in the findings synthesis.

---

## Synthesis (refreshed after each batch)

### Current tier breakdown (after batch 3)

| Tier | Definition | Countries |
|---|---|---|
| **Tier 1 — Drop-in PxWeb** | Existing `SCBPxWebClient` ports with only base-URL/table-ID/language changes | Norway, Iceland, Finland, Ireland, Estonia, Latvia, Slovenia, Switzerland, Croatia, **Philippines, Ghana** |
| **Tier 2 — HIGH, adapter required** | Full coverage but different wire format (REST/OData/SDMX/JSON-stat variants) | Denmark, Netherlands, Germany, Spain, France, UK, Canada, Australia, Japan, South Korea, Brazil, Czechia, Luxembourg, Poland, Slovakia, New Zealand, Eurostat (pan-EU) |
| **Tier 3 — MEDIUM** | Significant work: rate limits, fragmented APIs, microdata-only, or multiple sources to stitch | Italy, USA, Mexico, India, Austria, Belgium, Bulgaria, Cyprus, Greece, Hungary, Lithuania, Malta, Portugal, Romania, Albania, Serbia, **Indonesia, Vietnam, Singapore, Taiwan, Malaysia, UAE, Saudi Arabia, Israel, Turkey, Argentina, Chile, Colombia, Peru** |
| **Tier 4 — LOW / not viable** | No public API equivalent; or coverage too thin/disrupted | South Africa, Ukraine, **China, Thailand, Pakistan, Bangladesh, Iran, Nigeria, Kenya, Egypt, Morocco, Ethiopia, Tanzania, Venezuela, Uruguay, Ecuador** |

### Current recommended pilot

**Norway (SSB Statbank PxWebApi v2)** — co-developed with SCB, identical protocol, full coverage, no auth, mature Python wrappers (`pyjstat`, `pxweb`, `dapla-statbank-client`). Smallest porting cost; best validation that the SCB client architecture is country-portable.

After Norway, the next-best Tier-1 candidates are Switzerland (15/16 ✓, 4-language) → Estonia (clean PxWeb v1, register-based) → Slovenia → Latvia → Croatia → **Philippines (first non-European Tier 1)** → **Ghana (first sub-Saharan-African Tier 1)**.

### Cross-cutting findings (after batch 3)

1. **PxWeb spans 15 of 73 surveyed jurisdictions.** Sweden, Norway, Iceland, Finland, Ireland, Estonia, Latvia, Slovenia, Switzerland, Croatia, Cyprus, Albania, **Philippines (PSA OpenSTAT), Ghana (GSS StatsBank), Vietnam (GSO PxWeb, MEDIUM only due to uptime)**. Refactor `SCBPxWebClient` into a base `PxWebClient` class that all 15 can subclass.
2. **Eurostat remains the universal EU/EEA fallback** (13/16 dimensions). Greece's only viable adapter.
3. **Classification crosswalks are the real porting tax.** SUN2020/ISCED + SNI2007/NACE/ISIC4 + ClaNAE/CIIU4.CL/CIIU4.AC/MSIC/SSIC/PSIC/TSIC/VSIC/KBLI/MASCO/PKD/NKD/EVRK/KVED/NOGA/ÖNACE/TOL/TEÁOR/SBI/JSIC/KSIC/NIC/SCIAN/NAICS/ANZSIC/ROC-SIC/CAEV/NMA/PSCED/CINE. A single `ClassificationMapper` module is essential.
4. **Tier-2 protocol clusters expand to 4 patterns** (batch 3 doubles the SDMX cluster and adds REDATAM): REST + JSON-STAT v2 (Denmark, Czechia, Slovakia, Japan); SDMX 2.1 (Australia, Italy, Lithuania, Luxembourg, NZ, Eurostat, Ukraine, **UAE, Turkey**); country-bespoke JSON (Spain, Brazil, Portugal, Belgium, Serbia, Netherlands, **Indonesia, Singapore, Israel, Saudi Arabia, Malaysia**); **REDATAM (Argentina, Chile, Colombia, Peru, Uruguay, Ecuador, Venezuela)**.
5. **Sample vs. register gap.** Register-based: Sweden, Denmark, Finland, Norway, Estonia, Latvia, Lithuania, Slovenia. Sample-based: USA, UK, Australia, India, Greece, Croatia, Cyprus, Albania, Bulgaria, Romania, Serbia, plus most batch-3 jurisdictions. Sampler may need a "sample noise" floor.
6. **Census-vintage dependency now spans 25+ jurisdictions.** Range from Chile (2024) and Pakistan (2023) down to **Iran (2016), Egypt (2017), Venezuela (2011, ~14 years stale), Ethiopia (2007, ~19 years), Nigeria (2006, ~20 years)**. Pipeline should expose `census_vintage_year` per country.
7. **Auth-required HIGH feasibility:** Germany, Japan, South Korea, New Zealand. Batch 3 adds **Indonesia (BPS app key)** as an auth-gated MEDIUM, plus five Knoema-mediated LOWs (Nigeria, Kenya, Egypt, Ethiopia, Tanzania).
8. **Knoema/OpenDataForAfrica is now the only programmatic surface for 5 African NSOs** but is in maintenance/decline (CRAN R-package removed; datasets vanishing through 2024–2025). Any pipeline depending on it inherits a deprecation risk.
9. **Geopolitical exclusions, geo-blocks, and publication disruptions** now cover at least 10 jurisdictions: Serbia/Kosovo (1999), Ukraine/occupied territories (2014, 2022), South Africa Census 2022 withdrawals (Aug 2024), India 2021 Census slipped to 2027, **China NBS geo-blocks foreign IPs, Iran amar.org.ir intermittent + sanctions, Venezuela INE/REDATAM unreachable + EHM halt + emigration, Ethiopia Tigray exclusion post-2020**.
10. **Region-resolution skew:** Cyprus, Luxembourg, Malta, **Singapore (100% urban)** = 1 NUTS-2; Iceland, Estonia, Latvia, Slovenia = ≤15 NUTS-3.

---

## References

- SCB baseline implementation: `anxiety_synthetic/utils/scb_client.py:24-53`, `anxiety_synthetic/scb_population/fetch_service.py:4-334`
- Companion findings document: `investigate-international-statistical-apis-findings.md`
- Internal scratch (batch 1 raw): `C:\Users\basil\.claude\plans\analyse-scb02-api-and-melodic-jellyfish.md`
