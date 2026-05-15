# Findings: International Statistical APIs (SCB Equivalents)

**Date:** 2026-05-10
**Companion to:** [`investigate-international-statistical-apis.md`](investigate-international-statistical-apis.md)
**Batches completed:** 1 (20 countries — Europe, Anglophone, Asia, Latin America, Africa)
**Methodology:** One background research agent per country, ~500-word structured report each. See companion plan for the prompt template.

---

## Part 1 — SCB02 Baseline Inventory

### API characteristics
- **Endpoint:** `https://api.scb.se/OV0104/v1/doris/en/ssd/`
- **Protocol:** PxWeb POST queries returning JSON-STAT v2
- **Auth:** None; soft rate limits handled via 90-day file cache (`config/assets/scb_cache/`)
- **Implementation:** `anxiety_synthetic/utils/scb_client.py:24-53`

### Tables consumed (16 dimensions)
| # | Dimension | SCB Table | Classification | Implementation |
|---|---|---|---|---|
| 1 | Age × Sex (joint) | `BE0101` | 1-year ages, M/F | `fetch_service.py:24` |
| 2 | Education level | `UF0506` | SUN2020 (Swedish; ≈ ISCED) | `fetch_service.py:40` |
| 3 | Employment status | `AM0401P` | AKU (Swedish LFS) | `fetch_service.py:59` |
| 4 | Industry sector | `AM0401I` | SNI2007 (= NACE Rev. 2) | `fetch_service.py:162` |
| 5 | Employment type | `AM0401I` | Permanent/temp/self-emp | `fetch_service.py:186` |
| 6 | Working hours | `AM0401S` | 1-19h / 20-34h / 35+h | `fetch_service.py:199` |
| 7 | Income source / decile | `HE0110` | D1–D10 + 6 income components | `fetch_service.py:111, 246` |
| 8 | Housing tenure | `BO0104` | Owner / rental / bostadsrätt | `fetch_service.py:215` |
| 9 | Household size | `BE0101S` | 1P–7+P | `fetch_service.py:231` |
| 10 | Civil status | `BE0101` | OG/G/ÄNKL/SK | `fetch_service.py:144` |
| 11 | Region (county) | `BE0101` | 21 läns (≈ NUTS-3) | `fetch_service.py:94` |
| 12 | Birth location group | `BE0101E` | Sweden / EU / rest of world | `fetch_service.py:77` |
| 13 | Birth country detail | `BE0101E` | Top 20 countries | `fetch_service.py:265` |
| 14 | Parental structure | `LE0102` | Family type | `fetch_service.py:127` |
| 15 | Urbanization | category_mappings.json | Urban / suburban / rural | mappings only |
| 16 | Time series availability | All tables | Annual, latest available | implicit |

### Sweden-specific concepts (translation hazards)
- **SUN2020** — Swedish education taxonomy (maps to ISCED but not 1:1)
- **AKU** — Swedish Labour Force Survey codes (≈ EU LFS)
- **SNI2007** — Swedish NACE implementation
- **Bostadsrätt** — Tenant-owned cooperative apartment (no direct equivalent outside Nordics)
- **Läns** — Swedish county codes (NUTS-3 equivalent but proprietary IDs)
- **OG/G/ÄNKL/SK** — Swedish civil status abbreviations

### PxWeb recognition markers (for finding equivalents)
- POST-based queries with dimension filters
- JSON-STAT v2 output
- Variable codes in native language (`Alder`, `Kon`, `Region`, etc.)
- Mandatory `Tid` (time) dimension
- Hierarchical aggregate codes (`BE0101N1` = table + summary indicator)

---

## Part 2 — Country Reports

### Europe — Nordics + Ireland (PxWeb cluster)

#### Denmark
**API name & URL:** Statistics Denmark (DST) — StatBank API. Base: `https://api.statbank.dk/v1/` (`subjects`, `tables`, `tableinfo`, `data`). Console: `https://api.statbank.dk/console`.
**Technology stack:** REST API (POST recommended). Output: JSONSTAT, CSV, PX, DSTML (XML), XLSX, SDMX/BULK streaming. Conceptually parallel to PxWeb but DST's own JSON request schema (not canonical PxWeb POST body).
**Auth/limits:** No API key for data endpoints. 1M-cell hard cap (raised April 2025); streaming/BULK unlimited. CC-BY 4.0.
**Coverage:** 16/16 — all dimensions present. Notable tables: `FOLK1A` (age×sex×region×marital), `HFUDD11` (DISCED-15 education), RAS register tables (employment), `ERHV1` (DB07 industry), `INDKP104` (income deciles), `BOL101` (housing tenure), `FAM44N` (family with children), `VAN1AAR` (birth country). Urbanization is partial — DEGURBA exists but not first-class on most tables (must join via municipality).
**Classifications:** DISCED-15, DB07 (≡ NACE Rev. 2), DEGURBA, Kommunegrupper, NUTS.
**Example query:** `POST https://api.statbank.dk/v1/data` with body `{"table":"FOLK1A","format":"JSONSTAT","lang":"en","variables":[{"code":"OMRÅDE","values":["000"]},{"code":"KØN","values":["*"]},{"code":"ALDER","values":["*"]},{"code":"CIVILSTAND","values":["TOT"]},{"code":"Tid","values":["2026K1"]}]}`
**Python wrappers:** `dstapi` (alemartinello), `pydst` (elben10 / kristianolesenlarsen), `pyjstat` (generic JSON-stat parser).
**Blockers:** Request schema differs from canonical PxWeb — needs adapter, not drop-in. Variable codes Danish (KØN, ALDER, OMRÅDE). Urbanization needs municipality join. Microdata only via DST Research Services.
**Feasibility verdict:** **HIGH** — All 16 dimensions, unauthenticated, mature Python wrappers; only modest adapter work (new client + Danish code map + DEGURBA join).

#### Norway
**API name & URL:** Statistics Norway (SSB) — Statbank PxWebApi v2: `https://data.ssb.no/api/pxwebapi/v2/tables/{tableId}/data`. Legacy v1 deprecated since Oct 2025.
**Technology stack:** PxWebApi v2 (released Oct 2025, **co-developed with SCB** — drop-in compatible at the protocol layer). HTTP GET with query params; default response `json-stat2`; also CSV/XLSX/parquet/px.
**Auth/limits:** No auth, no registration. **30 queries/min per IP** (HTTP 429 on overrun). Max 800,000 cells/extract. URL ≤2100 chars. Avoid 07:55–08:15 CET (publication spike).
**Coverage:** 16/16 — all dimensions covered with strong evidence. Tables: 05810 (population by sex/age 1845–2025), 09429 (NUS/ISCED education), 09174 (NACE Rev. 2 industry), 11081 (housing tenure), 09817 (immigration / country background), 04859 (urbanization / tettsteder). Parental structure is partial (less granular than SCB's child-centric tables).
**Classifications:** NUS (ISCED-mapped), NACE Rev. 2 via NOS D 383, kommune/fylke (LAU/NUTS), landbakgrunn for birth country. Code lists exposed via separate KLASS API.
**Example query:** `GET https://data.ssb.no/api/pxwebapi/v2/tables/07459/data?lang=en&valueCodes[Region]=0&valueCodes[Kjonn]=*&valueCodes[Alder]=*&valueCodes[Tid]=2025&outputFormat=json-stat2`
**Python wrappers:** `pyjstat` (works unchanged), `pxweb`, `dapla-statbank-client` (official), `klass-python` (official KLASS classifications).
**Blockers:** 30/min rate limit tighter than typical SCB usage — fetch service must throttle. v1/v2 schema fork — pin to v2. Variable IDs Norwegian (Kjonn, Alder, Sivilstand). Individual income deciles sparser than SCB. v2 schema may still churn (new release).
**Feasibility verdict:** **HIGH** — Same PxWeb/JSON-stat stack as SCB (co-developed v2), open/unauthenticated, full coverage; port is mostly Norwegian variable-code mapping and a 30/min throttle.

#### Iceland
**API name & URL:** Statistics Iceland (Hagstofa Íslands) PxWeb API. Base: `https://px.hagstofa.is/pxen/api/v1/en/` (English) or `/pxis/api/v1/is/` (Icelandic).
**Technology stack:** Same PxWeb stack as SCB (PxWeb originally developed by SCB and shared across Nordic NSIs). POST JSON queries; response `json-stat`, `json-stat2`, `px`, `csv`, `xlsx`. **Drop-in compatible with PxWeb clients.**
**Auth/limits:** No auth, no registration. 30 calls/sec, 10,000-cell response cap (identical to SCB).
**Coverage:** 13/16 full ✓, 4 partial. Tables: MAN02005 (population by municipality/age/sex), MAN08213 (marital status), MAN04103 (citizenship / country of birth), FYR08001 (NACE employment). Partial: employment type, working hours, income deciles, parental structure (all SILC/LFS sample-based with limited cross-tab depth). Urbanization is locality/postcode proxy only — no explicit DEGURBA dimension.
**Classifications:** ISCED 2011, NACE Rev. 2, ISCO (partial), Sveitarfélög municipality codes, ISO country codes.
**Example query:** `POST .../Ibuar/mannfjoldi/2_byggdir/sveitarfelog/MAN02005.px` with JSON body selecting Sveitarfélag, Kyn, Aldur, Ár dimensions.
**Python wrappers:** `pyaxis` (icane, generic PxWeb→pandas), `hagstofan` (datador, dedicated async wrapper).
**Blockers:** **Population only ~390k** → disclosure-aggregation thins fine cross-tabs. Several socio-econ dimensions are SILC/LFS sample-based, not full registers as in Sweden. Variable names mostly Icelandic. 10,000-cell cap forces chunking.
**Feasibility verdict:** **HIGH** — Same PxWeb/JSON-stat protocol as SCB with no auth, all 16 dimensions at least partially covered, existing client architecture ports with minimal changes; only material caveat is small-population disclosure thinning.

#### Finland
**API name & URL:** Statistics Finland (Tilastokeskus) StatFin PxWeb API. Base: `https://pxdata.stat.fi/PXWeb/api/v1/{lang}/{database}/{level}/{table}.px`. v2 beta at `https://pxwebapi2.stat.fi/`.
**Technology stack:** PxWeb (same family as SCB). GET for metadata, POST for data with JSON query body. Formats: JSON, JSON-stat, JSON-stat2, CSV, XLSX, PX. Languages en/fi/sv via URL.
**Auth/limits:** No auth, CC BY 4.0. Hard limits: **30 queries / 10 s** (HTTP 429), **100,000 cells/query** (HTTP 403), 60 s timeout.
**Coverage:** 16/16 ✓. Tables: vaerak/11rc (age×sex), tyokay/115c (employment), TOL 2008 industry (= NACE Rev. 2), tjt/12hh (income decile), asas/116e (housing tenure), perh (families), 7-class urban-rural grid + DEGURBA.
**Classifications:** TOL 2008 (= NACE Rev. 2), AVO/ISCED, kuntakoodi (municipality), maakunta = NUTS-3, Nordic-harmonised origin classification.
**Example query:** `POST https://pxdata.stat.fi/PXWeb/api/v1/en/StatFin/vaerak/statfin_vaerak_pxt_11rc.px` body `{"query":[{"code":"Sukupuoli","selection":{"filter":"item","values":["1","2"]}},{"code":"Ika","selection":{"filter":"all","values":["*"]}},{"code":"Vuosi","selection":{"filter":"top","values":["1"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** `statfin` (PyPI, Oct 2025, MIT, attribute-style + cache), `pyjstat` (generic).
**Blockers:** Variable codes Finnish (Sukupuoli, Ika, Vuosi) even on `/en/`. Table IDs carry `.px` suffix that SCB omits. 30/10s rate limit tighter than SCB's. Cross-tabulations split across multiple tables.
**Feasibility verdict:** **HIGH** — same PxWeb/JSON-stat2 protocol, no auth, full coverage, mature Python wrapper; substitution = config/table-ID remap + minor URL tweaks.

#### Ireland
**API name & URL:** CSO — PxStat API. JSON-RPC: `https://ws.cso.ie/public/api.jsonrpc`; RESTful: `https://ws.cso.ie/public/api.restful/...`; browser at `https://data.cso.ie`.
**Technology stack:** **PxStat is in the PxWeb family** (.NET/C#, fork). JSON-RPC 2.0 (`PxStat.Data.Cube_API.ReadDataset`) and RESTful path-parameter form. Returns **JSON-stat v2.0** (also PX, CSV, XLSX). Includes a PxAPIv1 compatibility shim for legacy PxWeb clients.
**Auth/limits:** Anonymous read access; no API key, no registration. No documented rate limit; tolerates polite scripted use.
**Coverage:** 15/16 ✓ — Urbanization partial (six-way classification at Small-Area level (BUAs); not always available as cross-tab dimension). Tables: FY006B (age×sex), FY046 (employment), QES01 (NACE 2-digit), SILC SIA (income deciles), Census 2022 Profile 2 tenure / Profile 3 families / Profile 5 country of birth.
**Classifications:** NUTS-1/2/3 (CSO 2018 revision), 31 LAs, NACE Rev. 2 (migrating to Rev. 2.1), ISCED, ILO economic status, Eurostat-aligned tenure/household types.
**Example query:** `GET https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/FY006B/JSON-stat/2.0/en`
**Python wrappers:** `pyjstat` (mature), `cso-ireland-data` (PxStat-specific pandas loader), `CSO_Ireland_JSONStat4Py`. R: `csodata` (official).
**Blockers:** No native CSO Python SDK. High-arity cross-tabs may not exist pre-aggregated. Urbanization is geography-attached (Small Area / BUA), not a typical pivot dimension. Census 5-yearly (2022 latest) vs. SCB's annual cadence. NACE Rev. 2 → Rev. 2.1 migration in progress.
**Feasibility verdict:** **HIGH** — PxStat is a near drop-in PxWeb-family substitute, full JSON-stat v2.0 output, anonymous, all 16 SCB dimensions covered (15 fully); existing SCB client should port with primarily endpoint and table-ID changes.

### Europe — Major EU + UK

#### Germany
**API name & URL:** GENESIS-Online (Destatis). Federal: `https://www-genesis.destatis.de/genesisWS/rest/2020`. Regional: `https://www.regionalstatistik.de/genesis/online`. Census 2022: `https://ergebnisse.zensus2022.de/datenbank/online`.
**Technology stack:** RESTful/JSON service (POST). SOAP shut down 15 Jul 2025; GET REST shut down 27 Nov 2025 — POST-only now. Output: JSON, CSV, XLSX. **No native JSON-STAT** — differs from SCB. Cube/table/timeseries methods + find/catalogue/metadata + async `job` endpoints for large extracts.
**Auth/limits:** **Authentication required for every call** (free registration → username+password or token). No published rate limit but per-query cell limits force async `job=true` for large extracts. Free under "Datenlizenz Deutschland 2.0".
**Coverage:** 14/16 ✓, 2 partial (income decile only via EU-SILC LEB tables, less fine-grained than SCB; urbanization needs derived mapping via BBSR Kreistyp). Tables: 12411-* (age×sex), 12211-0040/0041 (ISCED education), 12211-0007 (employment), Microcensus by WZ 2008, 12211-0102 (marital status), full NUTS-1/2/3 + AGS via Regionaldatenbank, 12211 migration cubes (birth country).
**Classifications:** WZ 2008 (= NACE Rev. 2 = ISIC Rev. 4); ISCED 2011; AGS / NUTS; Datenlizenz Deutschland 2.0.
**Example query:** `POST https://www-genesis.destatis.de/genesisWS/rest/2020/data/table?username=<u>&password=<p>&name=12211-0102&area=all&compress=false&startyear=2023&endyear=2023&language=en&format=json`
**Python wrappers:** `pystatis` (CorrelAid, v0.5.5 March 2026, all three GENESIS DBs + pandas + caching + async jobs — by far the most mature), `genesispy`, `genesisclient`, `pygenesis`, `bundesAPI/destatis-api`. R: `restatis`.
**Blockers:** **Mandatory account registration** breaks SCB's zero-auth pattern. Much documentation German-only. Per-call cell limits force async `job` flow. No JSON-STAT — custom parser needed (pystatis hides this). Urbanization needs BBSR Kreistyp derivation. Recent breaking changes (POST-only since Nov 2025) — many web examples stale. Microcensus is 1% sample → very fine joint cells suppressed.
**Feasibility verdict:** **HIGH** — Matches/exceeds SCB on all 16 dimensions (only urbanization needs derivation), `pystatis` wrapper mirrors role of SCB client, free under permissive licence; only real cost vs SCB is one-time user registration and swapping JSON parser.

#### France
**API name & URL:** INSEE — Mélodi API at `https://api.insee.fr/melodi/V2/` (new unified open-data successor to BDM/DDL); BDM SDMX at `https://bdm.insee.fr/series/sdmx/` (~150,000 macroeconomic series); developer portal at `https://portail-api.insee.fr/catalog`.
**Technology stack:** REST returning JSON (Mélodi) and SDMX-ML 2.1 / SDMX-JSON (BDM). URL pattern `API/method/name/filter`. Mélodi exposes "cubes" per the SDMX/Datacube info model.
**Auth/limits:** Mélodi: **no authentication**, **30 req/min** (HTTP 429 beyond). BDM: free, no auth, soft per-series limits. Sirene requires OAuth2 (irrelevant here).
**Coverage:** 16/16 (only Birth country detail partial — aggregated groupings + specific countries limited by statistical secrecy). Strong coverage incl. FiLoSoFi income deciles at commune level, ZAAV-2020 urban areas (Eurostat FUA-aligned), harmonised census 1968-2022.
**Classifications:** NAF Rev. 2 (= NACE Rev. 2), PCS 2020 (occupations), COG (commune codes), ZAAV-2020 (urban areas), ISCED.
**Example query:** `GET https://api.insee.fr/melodi/V2/data/DS_RP_POPULATION_PRINC?GEO=FR&SEX=_T&AGE_GROUP=Y15T19`
**Python wrappers:** `pynsee` (InseeFrLab, on PyPI, actively maintained — covers BDM macro, local data, metadata, SIRENE, IGN geodata), `api-insee`.
**Blockers:** Mélodi still rolling out — some legacy datasets only on BDM/DDL during transition. Docs primarily French. FiLoSoFi suppresses cells for areas <50 households / <100 persons. 30 req/min cap requires throttling. Census cube structures differ from PxWeb — `fetch_service.py` needs rewriting.
**Feasibility verdict:** **HIGH** — INSEE covers all 16 SCB dimensions with comparable or better granularity, free anonymous via Mélodi, mature `pynsee` wrapper; main cost is rewriting SCB PxWeb client to SDMX/Mélodi REST and remapping classification codes.

#### United Kingdom
**API name & URL:** ONS Beta API (`https://api.beta.ons.gov.uk/v1/datasets`), Nomis RESTful v01 (`https://www.nomisweb.co.uk/api/v01/` — primary census/labour-market gateway). NRS (Scotland) and NISRA (NI) are bulk CSV/XLSX only — no REST API.
**Technology stack:** REST/HTTP (GET). Nomis returns SDMX (XML/JSON), simple JSON, CSV. ONS Beta returns JSON. **No JSON-STAT** — but Nomis SDMX-JSON is structurally comparable.
**Auth/limits:** ONS Beta: no registration; 120 req/10s and 200 req/min. Nomis: free, no registration; guest cap 25k rows/query, registered (free key) 100k rows.
**Coverage:** 14/16 ✓, income partial (ASHE earnings deciles for employees only — HBAI/HMRC not on same API), urbanization partial (RUC is geography lookup, not Nomis dimension). Census 2021 TS-tables + Nomis APS/ASHE/BRES time series.
**Classifications:** SOC 2020, SIC 2007 (= NACE Rev. 2), NS-SEC, NVQ levels, ONS Geography Codes, 2021 RUC.
**Example query:** `https://www.nomisweb.co.uk/api/v01/dataset/NM_2021_1.data.json?geography=2092957699&c2021_age_101=0...100&c_sex=1,2&measures=20100`
**Python wrappers:** `ukcensusapi` (PyPI, virgesmith) — Nomis wrapper with metadata caching, also covers NRS/NISRA scraping.
**Blockers:** Coverage fragmented across Nomis (E&W/most Scotland), NISRA NI (no API, FTB UI only), NRS Scotland (downloads only). Income split across ASHE / HBAI / HMRC. Census reference years differ (E&W/NI 2021 vs Scotland 2022). RUC ships as geography lookup, not queryable dimension. No JSON-STAT — adapter required.
**Feasibility verdict:** **HIGH** — Nomis + ONS Beta cover 14/16 dimensions, free unauthenticated, maintained Python wrapper; main cost is writing a parallel adapter to `SCBPxWebClient`.

#### Netherlands
**API name & URL:** CBS StatLine Open Data API. v3 (legacy OData v3): `https://opendata.cbs.nl/ODataApi/odata/{table_id}/`. v4 (current OData v4): `https://odata4.cbs.nl/CBS/{table_id}/`.
**Technology stack:** OData v3 (legacy) and OData v4 (current), both JSON. RESTful with `$filter`, `$select`, `$top`, `$skip`. Returns OData JSON envelopes (`value` array + `@odata.nextLink`), **not JSON-stat**.
**Auth/limits:** No registration, no key, no auth. Soft cap ~10,000 cells/response; pagination via `@odata.nextLink`. No published hard rate limit.
**Coverage:** 16/16 ✓. Tables: 37296eng (age×sex×region), 85051NED (education ISCED), 80590NED (employment), 81156ENG (SBI 2008 industry), 82900NED (housing tenure), 71486NED (households), 85384ENG (birth country detail), Stedelijkheid 5-class urbanization on 70072ned.
**Classifications:** SBI 2008 (= NACE Rev. 2), ISCO-08, ISCED 2011, CBS `Herkomst` 2022, gemeente/provincie/NUTS 1-3.
**Example query:** `https://opendata.cbs.nl/ODataApi/odata/83765NED/TypedDataSet?$filter=WijkenEnBuurten eq 'GM0363 '&$select=WijkenEnBuurten,AantalInwoners_5&$format=json`
**Python wrappers:** `cbsodata` (J535D165, PyPI, MIT, mature v3 client, pandas-friendly), `cbsodata4`. Reference repos at `statistiekcbs/CBS-Open-Data-v3/v4`.
**Blockers:** OData not JSON-stat — adapter required. v3 vs v4 split: v3 deprecating, some tables only on one side. 10k-cell page cap. Many tables Dutch-only. 2022 `Herkomst` reclassification creates time-series break. v3 has trailing-whitespace quirk.
**Feasibility verdict:** **HIGH** — All 16 dimensions via free, unauthenticated, well-documented OData API with mature Python client; remaining work is OData→internal-distribution adapter and Dutch-label mapping.

#### Spain
**API name & URL:** INE — Tempus3 JSON API. `https://servicios.ine.es/wstempus/js/{lang}/{function}/{input}` (lang = ES/EN). OpenAPI/Swagger published.
**Technology stack:** REST + custom JSON (Tempus3-native, **not JSON-stat**). Backed by Tempus3 RDB plus PC-Axis files. Functions: DATOS_TABLA, DATOS_SERIE, OPERACIONES_DISPONIBLES, VARIABLES_OPERACION, VALORES_VARIABLE.
**Auth/limits:** No auth, no key, no registration. Pagination capped at 500 items/page. No published rate limits.
**Coverage:** 12/16 ✓, 4 partial (income decile/source via ADRH less uniform; birth country detail granularity varies; parental structure single-parent only; urbanization only via municipality size strata or EU-SILC subsets). Tables: EPA 65061 (age×sex), 72987 (education), DIRCE 39371 (CNAE-2009), ECP 59586 (country of birth).
**Classifications:** CNAE-2009 (= NACE Rev. 2), CNAE-2025 (= NACE Rev. 2.1) rolling Jan 2025; CNO-11 occupations; CNED-2014 education; NUTS.
**Example query:** `GET https://servicios.ine.es/wstempus/js/EN/DATOS_TABLA/65061?nult=4&tip=AM`
**Python wrappers:** `INEapy` (PyPI, SDG Group, Jan 2026 — pandas DataFrames), `ineware`, `ine-python`. R: `ineapir` (official).
**Blockers:** INE-proprietary schema requires new parser layer (cannot reuse SCB's `pyjstat`). Substantial docs Spanish-only. Table-id discovery non-trivial. Income/parental/urbanisation split across surveys. CNAE-2025 transition risks classification churn.
**Feasibility verdict:** **HIGH** — Free, unauthenticated, well-documented, all 16 dimensions covered (12 fully + 4 partial), multiple Python wrappers; main cost is Tempus3-to-internal-distribution adapter.

#### Italy
**API name & URL:** ISTAT SDMX RESTful Web Service. `https://esploradati.istat.it/SDMXWS/rest` (legacy `http://sdmx.istat.it/SDMXWS/rest` still alive).
**Technology stack:** SDMX 2.1 RESTful (also partial 3.0 v2 paths). Returns SDMX-ML, SDMX-JSON, JSON-stat via Accept header. **SDMX is structure-heavy**: queries are key-tuples against a Data Structure Definition (DSD), not flat dimension JSON like PxWeb.
**Auth/limits:** No registration, no key, no auth. **Hard limit: 5 queries/min/IP, with 1-2 day IP bans on breach**. Single-response payloads can exceed several GB — strict filtering required.
**Coverage:** 13/16 ✓, 3 partial (income decile less consistent than SCB — quintile-based via IT-SILC; parental structure less granular; urbanization via DEGURBA not always exposed as direct SDMX dimension). Tables: DCIS_POPRES1 (age×sex×region), DCIS_POPSTRRES1 (foreign residents by citizenship).
**Classifications:** ATECO 2007 (= NACE Rev. 2), ATECO 2025 from Jan 2025; ISCED-A/P 2011; NUTS 1/2/3 + ISTAT comune codes; ISO 3166 + ISTAT country list; ISCO-08.
**Example query:** `GET https://esploradati.istat.it/SDMXWS/rest/data/IT1,22_289,1.0/.M.9.99..?startPeriod=2023` with `Accept: application/vnd.sdmx.data+json;version=1.0.0`
**Python wrappers:** `istatapi` (PyPI, ISTAT-specific, lowest friction), `sdmx1` (actively maintained, ISTAT pre-registered), `pandaSDMX` (legacy), `jsonstat.py`.
**Blockers:** **5 req/min hard cap with multi-day bans** is the biggest operational risk vs SCB. SDMX key-tuple queries less ergonomic than PxWeb. Some `/rest/v2` SDMX 3.0 paths documented but not implemented. ATECO 2007→2025 transition. Income is quintile-based not decile. GB-scale default responses force tight filtering.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions reachable and free, but the 5 req/min cap, mandatory DSD-driven query construction, and SDMX-vs-PxWeb impedance mismatch require non-trivial fetch/cache rewrite.

### Anglophone (non-EU)

#### United States
**API name & URL:** Census Bureau Data API (`https://api.census.gov/data/`) — ACS 1-yr/5-yr endpoints + PUMS microdata. Secondary: BLS Public Data API v2 (`https://api.bls.gov/publicAPI/v2/timeseries/data/`). HUD USER APIs for housing affordability.
**Technology stack:** REST + JSON. Census uses simple GET (`get=`, `for=`, `in=`, `&KEY=`) — returns header-row JSON array, **NOT JSON-STAT**. BLS v2 uses POST+JSON. **No PxWeb compatibility**.
**Auth/limits:** Census — no auth for ≤500 queries/IP/day; free 40-char API key required above that. BLS — 25 queries/day anonymous, 500/day registered, 50 series per request, ≤20-yr history.
**Coverage:** 15/16 ✓, urbanization partial (geographic delineation, not an ACS variable; must be joined via TIGER UA codes or USDA RUCA/RUCC). All other dimensions via ACS B-tables + PUMS variables (AGEP, SEX, SCHL, ESR, INDP, COW, WKHP, PINCP, TEN, NP, MAR, NATIVITY, POBP, HHT/PAOC).
**Classifications:** **NAICS** (industry, NOT NACE — ISIC crosswalk required), **SOC** (occupation, not ISCO), Census/OMB race+ethnicity (US-specific), FIPS for geography, PUMA (~100k pop) as smallest microdata geography.
**Example query:** `https://api.census.gov/data/2023/acs/acs1?get=NAME,group(B01001)&for=state:*&key=YOUR_KEY`
**Python wrappers:** `census` (datamade), `CensusData`, `cenpy` (pandas/sqlalchemy-style), `pygris` (geographies), `bls`/`blsAPI`. **None speak JSON-STAT** → existing SCB client cannot be reused.
**Blockers:** Fragmented across Census/BLS/HUD/IRS-SOI. ACS is a 1%/5% **sample** survey (not a register like SCB — sampling error, no continuous coverage). JSON shape differs from PxWeb so `SCBPxWebClient` and category mappings need reimplementation. NAICS↔NACE and SOC↔ISCO crosswalks needed. Urbanization requires geo-join. Place-of-birth coding differs. Puerto Rico has separate PRCS endpoints.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable but fragmented agencies, sample-survey nature, and incompatible JSON-STAT/PxWeb schema mean a new client + mapping layer required.

#### Canada
**API name & URL:** Statistics Canada Web Data Service (WDS). `https://www150.statcan.gc.ca/t1/wds/rest/`. Census Profile additionally exposes SDMX endpoint at `https://www12.statcan.gc.ca/wds-sdw/`.
**Technology stack:** RESTful HTTPS, JSON request/response (POST for data, GET for discovery). Conceptually similar to PxWeb but uses StatCan's **"cube + coordinate" model** rather than JSON-STAT v2.
**Auth/limits:** No auth, no key, no registration. **50 req/sec server-wide, 25 req/sec per IP**. Possible HTTP 409 during 00:00–08:30 EST maintenance.
**Coverage:** 15/16 ✓, urbanization partial (PCRA classification in some Census tables, not consistently joinable with LFS). Tables: 17-10-0005-01 (annual pop by age/sex), 14-10-0287 (LFS by age/gender), 37-10-0130 (education), 14-10-0023 (NAICS industry), 14-10-0027 (FT/PT), 11-10-0239 (income deciles), 98-10-0228 (tenure), 98-10-0309 (~150 places of birth).
**Classifications:** **NAICS 2017** (industry — North-American family, NOT NACE Rev.2); NOC 2021 (occupations); SGC 2021 (geography); ISCED-mappable education levels.
**Example query:** `POST https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods` body `[{"productId": 14100287, "coordinate": "1.1.1.1.1.0.0.0.0.0", "latestN": 1}]`
**Python wrappers:** `stats-can` (ianepreston, actively maintained, pandas-first, NDM-aware), `statscanpy`. R: `cansim`, `cancensus`.
**Blockers:** Coordinate-string model needs metadata round-trip per cube. Census 5-yearly (2021 latest until late 2026). NAICS 2017 vs NACE Rev.2 not interchangeable. Urban/rural not first-class in most labour/income tables. Bilingual EN/FR labels.
**Feasibility verdict:** **HIGH** — All 16 SCB dimensions covered (15 fully, 1 partial), no auth, generous rate limits, mature `stats-can` Python wrapper; main cost is rewriting query layer to productId+coordinate model and swapping NACE for NAICS 2017.

#### Australia
**API name & URL:** ABS Data API (Beta). `https://data.api.abs.gov.au/rest/`. Companion: Indicator API, Time Series Directory API. Detailed Census cross-tabs sit behind TableBuilder/DataLab (login).
**Technology stack:** **SDMX 2.1 fully compliant**. REST. Three formats: SDMX-ML (XML, default), SDMX-JSON, SDMX-CSV. Data key uses dot-separated dimension codes with `+` OR-operator and wildcards.
**Auth/limits:** No mandatory auth; API key strongly recommended for production (request via email, ABS replies in days). Per-key rate limits enforced (numeric value not published). Broad `/all` queries time out — must filter.
**Coverage:** 15/16 ✓, income partial (Census banded INCP/HIND/FINF only — SIH not on Data API; deciles must be derived). Tables: `C21_G04_*` (age×sex), LFS dataflow (monthly since 1978), ANZSIC industry, ASGS Remoteness Areas (5 classes) for urbanization, BPLP at SACC 4-digit (birth country).
**Classifications:** **ANZSIC 2006 Rev 2.0** (industry — distinct from NACE), ANZSCO (occupations), ASGS Edition 3 (geography), SACC (country), ASCED (education).
**Example query:** `GET https://data.api.abs.gov.au/rest/data/ABS,C21_G04_AUS,1.0.0/..AUS..?startPeriod=2021&endPeriod=2021&dimensionAtObservation=AllDimensions` with `Accept: application/vnd.sdmx.data+json`
**Python wrappers:** `sdmx1` (PyPI, actively maintained, built-in `ABS` source), `pandaSDMX` (less active).
**Blockers:** Census every 5 years (2021 latest; 2026 release in 2027). Detailed cross-tabs (4-way) require TableBuilder/DataLab login. SIH income/wealth not in Data API. Beta status — URL already migrated once. Two parallel naming conventions (legacy 2016 `ABS_*` vs new 2021 `C21_*`).
**Feasibility verdict:** **HIGH** — Open SDMX 2.1/JSON REST, no mandatory auth, all 16 dimensions covered (15 fully, income partial via banded Census), mature `sdmx1`/`pandaSDMX`; main caveats are 5-yearly cadence and need to derive income deciles.

### Asia

#### Japan
**API name & URL:** e-Stat — Portal Site of Official Statistics (Statistics Bureau / MIC). `https://api.e-stat.go.jp/rest/3.0/app/`. JSON: `…/app/json/getStatsData?…`. Portal: https://www.e-stat.go.jp/en
**Technology stack:** REST GET. **XML, JSON, CSV, and JSON-stat** outputs. CORS on JSON; gzip; HTTPS.
**Auth/limits:** Free `appId` required (register on MyPage; max 3 IDs per user). No documented rate cap. **100,000-record response cap**, paginated via `<NEXT_KEY>` / `startPosition`.
**Coverage:** 15/16 ✓, **birth country only partial — only nationality (~186 categories), not country of birth**. Tables: 2020 Census 2-1 (age×sex), 62-2 (education), LFS 2-1 (employment), LFS 2-6-1 (JSIC), LFS 2-17-1 (regular/non-regular employment), Housing & Land Survey 2023 (tenure + income), 2020 Census 6-3-1 (household size), DID urbanization since 1960.
**Classifications:** JSIC (Rev.14, 2024); JSCO occupations; native single/5-year age groups; 47-prefecture geo codes; DID flag. **No NACE/ISCO crosswalk built-in.**
**Example query:** `GET https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?appId=YOUR_APP_ID&statsDataId=0003445141&cdCat01=001&lvArea=2&limit=100000`
**Python wrappers:** `jpstat` (Alalalalaki, PyPI, MIT, returns pandas DataFrames; covers e-Stat + RESAS), `pyjstat` (generic JSON-stat parser, works because e-Stat emits JSON-stat). R: `estatapi`, `jpstat` (UchidaMizuki).
**Blockers:** English coverage partial — many sub-tables, metadata, and category labels Japanese-only. 100k-record cap forces pagination. Opaque `statsDataId` registry needs upfront mapping. **Birth country replaced by nationality**. appId registration breaks SCB's zero-auth pattern.
**Feasibility verdict:** **HIGH** — Covers 15/16 dimensions natively (birth-country only partial), exposes JSON-stat like SCB, free key, mature `jpstat` Python wrapper; main cost is upfront table-ID mapping and Japanese-label handling.

#### South Korea
**API name & URL:** KOSIS Open API (Korean Statistical Information Service, KOSTAT/MODS). Portal: `https://kosis.kr/openapi/`. Endpoints: `https://kosis.kr/openapi/statisticsList.do`, `https://kosis.kr/openapi/Param/statisticsParameterData.do`.
**Technology stack:** RESTful HTTP GET, query-string parameters, JSON (`format=json&jsonVD=Y`) or XML. **Not JSON-STAT v2** — flat row arrays with C1..C8, ITM_ID, PRD_DE, DT, UNIT_NM.
**Auth/limits:** **Mandatory registration on KOSIS sharing service** + per-app API key (`apiKey` query param). Rate limits not published in English; community reports ~10k calls/day per key. Free for research.
**Coverage:** 12/16 ✓, 4 partial (income decile/source — micro-data only via MDIS; birth country detail — Korean concept is nationality not birthplace; parental structure less granular than SCB; urbanization — no official binary, proxy via sido or Eup/Myeon/Dong type). Strong: Census + EAPS time series.
**Classifications:** KSIC (industry), KSCO (occupation), KSCED (education), ROK administrative codes.
**Example query:** `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey=YOUR_KEY&itmId=T20+&objL1=ALL&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=3&orgId=101&tblId=DT_1IN1502`
**Python wrappers:** `PublicDataReader` (PyPI, WooilJeong) — `Kosis` class, returns pandas DataFrames, actively maintained. R: `kosis` (CRAN).
**Blockers:** Registration UI Korean-only, historically wanted Korean mobile/i-PIN. Table discovery painful — `tblId`/`orgId` codes via portal lookup; English table names lag. Response shape ≠ JSON-STAT → new parser. Some SCB concepts (urban/rural binary, country-of-birth) don't map 1:1.
**Feasibility verdict:** **HIGH** — Covers 12/16 cleanly + 4 partial, free keyed REST/JSON, maintained Python wrapper, deep time series; main cost is new fetch-layer adapter and Korean-language onboarding for the API key.

#### India
**API name & URL:** **No single PxWeb-equivalent**. Three fragmented entry points:
- **eSankhyiki (MoSPI)** — `https://esankhyiki.mospi.gov.in/` + beta MCP at `https://mcp.mospi.gov.in` (Feb 2026)
- **data.gov.in (OGD)** — `https://api.data.gov.in/` (~198k resources, mostly CSV-backed REST)
- **Census of India (RGI)** — `https://censusindia.gov.in/census.website/data/api/` (Census 2011 only — 2027 census in progress)
- **microdata.gov.in (NADA)** — survey unit-level files (PLFS, HCES); download-only

**Technology stack:** REST + JSON/CSV. eSankhyiki uses tool-style API + MCP server. data.gov.in returns flat CSV/JSON resources keyed by UUID. Census API uses 4-step query workflow with `urbrur` flag. **No JSON-STAT, no PxWeb cube semantics**.
**Auth/limits:** eSankhyiki MCP: no auth. data.gov.in: free API key required. Census: no auth. microdata.gov.in: free registration.
**Coverage:** 10/16 ✓, 6 partial/limited (Age×Sex from 2011 Census only; income/expenditure deciles via HCES microdata only; housing tenure stuck on 2011 Census; parental structure no explicit single-parent breakdown; time series patchy with 16-yr Census gap). Note: religion + caste enumeration uniquely tracked in Census (caste returning in 2027 after 1931).
**Classifications:** NIC-2008 (= ISIC Rev.4), NCO-2015 (= ISCO-08), Census state/district codes, MoSPI religion codes, SC/ST schedules.
**Example query:** `GET https://api.data.gov.in/resource/{uuid}?api-key=KEY&format=json&limit=100`
**Python wrappers:** `datagovindia` (PyPI, addypy/datagovindia), `esankhyiki-mcp` (official MCP reference).
**Blockers:** No unified cube API — 16 dimensions need ~4 different connectors. **Census 2021 delayed to 2027** — joint age×sex, religion, housing, civil status stuck on 2011 vintage. HCES income is microdata-only. data.gov.in patchy — many "datasets" are PDFs/static CSVs. eSankhyiki coverage thin (17 datasets). No JSON-STAT.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable in principle but require stitching ~4 separate APIs plus unit-record processing; core Census-derived dimensions stuck on 2011 vintage. SCB's clean PxWeb model has no real Indian counterpart yet.

### Latin America

#### Brazil
**API name & URL:** IBGE — two complementary public APIs:
- **SIDRA API** (tabular aggregates) — `https://apisidra.ibge.gov.br/values/...`
- **Servico de Dados** (catalog/metadata + 16 sub-APIs incl. Agregados v3, CNAE, Localidades) — `https://servicodados.ibge.gov.br/api/v3/agregados/`

**Technology stack:** REST + JSON over HTTPS. SIDRA uses unusual path-segment query syntax: `/values/t/<table>/n<level>/<geo>/v/<vars>/p/<period>/c<class>/<categories>?formato=json`. Agregados v3 is more conventional REST. **No JSON-STAT** — flat IBGE-specific JSON.
**Auth/limits:** Fully public, no API key, no registration. Documented hard cap of **100,000 records per query** (clients auto-segment). No published rate limit.
**Coverage:** 15/16 ✓, birth country detail partial (foreign-born "país de nascimento" captured but SIDRA aggregation coarser than SCB). Censo 2022 universe tables released Oct 2023 + PNAD Contínua quarterly. Tables: 200 (population), 6373/3584 (working hours), 3193/2472 (estado civil).
**Classifications:** CNAE 2.0/2.3 (industries, ISIC-derived), CBO (occupations, ISCO-mappable), DTB via Localidades API.
**Example query:** `https://apisidra.ibge.gov.br/values/t/200/n6/all/p/last/c2/all?formato=json` (population by sex, last period, all municipalities).
**Python wrappers:** **`sidrapy`** (PyPI, AlanTaranti, Py3.8+, actively maintained, single `get_table()`) is the production choice. Also `ipeadatapy`, `brazilian-data`.
**Blockers:** Portuguese-only payload labels (need Portuguese keyword normalizers). SIDRA's positional URL grammar awkward (Agregados v3 cleaner). No JSON-STAT means new response parser. 100k row cap requires pagination. Two overlapping endpoints (SIDRA vs Agregados v3) — pick one.
**Feasibility verdict:** **HIGH** — IBGE matches all 16 SCB dimensions with public no-auth REST/JSON, mature Python wrapper (sidrapy), and richer recency (Censo 2022 + quarterly PNAD); main porting cost is new JSON adapter and Portuguese label mappings.

#### Mexico
**API name & URL:** INEGI — Banco de Indicadores API. `https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/`. Exposes BISE (sociodemographic, includes Censo 2020) and BIE (economic).
**Technology stack:** REST over HTTPS with **path-parameterised URLs (no POST body — unlike SCB PxWeb)**. Output: plain JSON, JSON-Stat v1, PC-Axis, XML, JSONP. JSON-Stat uses dedicated `JSONSTAT/...` endpoint. Series addressed by numeric IndicatorId.
**Auth/limits:** Free token required (self-registration with email, token emailed automatically). Token appended as last path segment. No published rate limits.
**Coverage:** 12/16 ✓, 4 partial (Age×Sex joint cross-tab requires multiple IndicatorIds; income deciles via ENIGH microdata CSV not API; birth country detail in microdata; parental structure household composition partial in API).
**Classifications:** **SCIAN** (Sistema de Clasificacion Industrial de America del Norte — NAICS-based) for industry; CMO/SINCO for occupation; AGEB/entidad/municipio for geography; CONAPO age groups.
**Example query:** `GET https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/1002000001/es/00/false/BISE/2.0/{TOKEN}?type=json`
**Python wrappers:** `INEGIpy` on PyPI (Indicadores, DENUE, MarcoGeoestadistico classes; not actively maintained — >12 months). `andreslomeliv/DatosMex` broader toolkit. R: `inegiR` (CRAN, updated 2025) more mature.
**Blockers:** Documentation primarily Spanish. **No POST/JSON-body cross-tab querying** like SCB — need IndicatorId numbers up-front from a catalog of tens of thousands. Joint distributions (age × sex × education) require fetching multiple indicators and reconstructing. Income deciles and detailed birth-country need ENIGH/Censo microdata downloads. Token is path-embedded (complicates logging/caching).
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable from INEGI sources and the API is free/stable/JSON-Stat-compatible, but ~3 dimensions need microdata fallback and the per-indicator path-based query model requires substantially more engineering than SCB's PxWeb cross-tab POST queries.

### Africa

#### South Africa
**API name & URL:** Stats SA — `https://www.statssa.gov.za`. Closest programmatic surface is **SuperWEB2** at `https://superweb.statssa.gov.za/webapi/jsf/login.xhtml` (WingArc SuperSTAR; underlying JSON Open Data API exists but Stats SA does not publicly document or expose keys for it). Companions: ISIbalo, Census 2022 dissemination, Time Series Excel/ASCII downloads. Microdata mirrored on **DataFirst (UCT)** and World Bank Microdata Library. **Nesstar discontinued 31 Dec 2024.**
**Technology stack:** WingArc SuperSTAR / SuperWEB2 (JSF UI over a private JSON REST "Open Data API"); ISIbalo is a static-file PHP portal; legacy Nesstar (defunct); time series as Excel/ASCII. **No public PxWeb/JSON-stat endpoint.**
**Auth/limits:** SuperWEB2 needs **manual user registration**. The SuperSTAR Open Data API requires an `APIKey` HTTP header — Stats SA publishes no key-issuance workflow. DataFirst requires registration plus per-dataset access application.
**Coverage:** 7/16 ✓, 7 partial, 1 missing (income decile/source — Census 2022 income **withdrawn** Aug 2024; only stale IES 2010/11 + LCS 2014/15). Census 2022 reliability contested (31% overall undercount). Several other dimensions hit by the Aug 2024 withdrawal.
**Classifications:** South African SIC v7 (from ISIC Rev 4); SASCO 2012 occupations (from ISCO-08); **Population Group** (Black African / Coloured / Indian-Asian / White / Other) — apartheid-legacy taxonomy unique to SA, mandatory for HDI tracking, **no SCB analogue**.
**Example query:** **No reproducible public REST query exists**. Workflow is interactive: login to SuperWEB2 → build (e.g. Age × Sex × Province from Census 2022) → "Download Table" as CSV.
**Python wrappers:** **None.** No `statssa`/`pystatssa` on PyPI or GitHub. `pyjstat` unusable (no JSON-stat endpoint).
**Blockers:** No public open API equivalent to SCB PxWeb — SuperWEB2 is interactive/session-cookie. **Census 2022 withdrew employment, income, mortality, fertility tables in Aug 2024**, hitting 4 of 16 dimensions. DataFirst's per-dataset application gate kills automated nightly fetches. Population Group is a mandatory SA dimension with no SCB analogue.
**Feasibility verdict:** **LOW** — Stats SA has no SCB-style open API; replicating the 16-dimension fetch would mean reverse-engineering an undocumented APIKey-gated SuperSTAR endpoint plus manual DataFirst microdata, while the freshest source (Census 2022) has officially withdrawn 4 target dimensions.

---

### Europe — Rest of EU/EEA (batch 2, in progress)

#### Austria
**API name & URL:** Statistics Austria Open Government Data portal — `https://data.statistik.gv.at` (free CSV catalogue). Premium counterpart: STATcube REST API at `https://portal.statistik.at/statistik.api/...` (subscription).
**Technology stack:** OGD is flat CSV-over-HTTP (NOT PxWeb, NOT JSON-stat, NOT SDMX). Each dataset = main fact CSV + per-dimension classification CSVs + HEADER file. STATcube REST returns proprietary JSON (not JSON-stat).
**Auth/limits:** OGD: no auth, no documented rate limits, CC-BY 4.0. STATcube REST: paid subscription + API key; per-table rate limit endpoint.
**Coverage:** 16/16 (12 ✓, 4 partial). Tables: `OGD_bevstandjbab2002_BevStand_*` and `OGD_regz_rz_vz_aest_dem_*` (1-yr age × sex), AKE/Mikrozensus `OGD_ake100_*` (LFS), ÖNACE 2008 in `OGD_watlas3_*`, GWZ for housing tenure, `OGD_f1741_HH_Proj_1` (household size by type). Partial: detailed employment type, working-hours bands, joint income×demographics, explicit DEGURBA tagging.
**Classifications:** ISCED-2011, ÖNACE 2008 (= NACE Rev. 2), NUTS-1/2/3, ISO country codes, ISCO. Eurostat-compatible.
**Example query:** `GET https://data.statistik.gv.at/data/OGD_bevstandjbab2002_BevStand_2020.csv` (fact table) plus dimension labels at `..._C-ZRSEX1-0.csv` and `..._C-ZRAGE4-0.csv`.
**Python wrappers:** None first-party. Pragmatic path: `requests` + `pandas.read_csv`. R `STATcubeR` is feature-rich but R-only — would need a Python port. `pyaxis`/`sdmx1`/`pandaSDMX` do not apply.
**Blockers:** No PxWeb/JSON-stat — must rebuild SCB query logic against CSV joins (fact + classification CSVs). Free OGD is curated subset (~315 datasets); dense joint distributions may require paid STATcube. German-only column codes (`C-ZRSEX1-0`); HEADER file required for label decode. No conditional query API — full cube download + client-side filter. STATcube subscription is institutional/paid.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions in free OGD with Eurostat-compatible classifications, but absence of a PxWeb/JSON-stat query API means SCB client and conditional sampler must be rewritten around bulk CSV download + local pandas filtering rather than parameterised POST queries.

#### Belgium
**API name & URL:** Statbel — BeStat API at `https://bestat.statbel.fgov.be/bestat/api/views/{VIEW_ID}/result/{FORMAT}`. Bulk downloads via `https://statbel.fgov.be/en/open-data`. NBB.Stat (National Bank of Belgium) exposes some Statbel series via SDMX.
**Technology stack:** REST GET on saved "views" only — no PxWeb, no JSON-stat. Returns proprietary JSON ("facts" array of denormalised rows), plus XML/CSV/XLSX/PDF/HTML. No POST query body, no on-the-fly dimension filtering — each view is a fixed pre-saved cube.
**Auth/limits:** No auth, no registration, no documented rate limits. CC BY 4.0.
**Coverage:** 16/16 (10 ✓, 6 partial). 1-yr ages only in bulk Open Data XLSX (BeStat views give age groups). LFS-derived dimensions (employment status, NACE, employment type, hours) all present but cross-tabs limited to pre-saved views. Income decile from fiscal/admin disposable-income datasets. DEGURBA derivable via Eurostat overlay; not native.
**Classifications:** NACE Rev. 2, ISCED, NUTS-2/3, Eurostat DEGURBA (indirect), Statbel statistical sectors.
**Example query:** `GET https://bestat.statbel.fgov.be/bestat/api/views/3ebe4ddc-27e6-4d3d-a6c0-3121df828953/result/JSON` returns Region × Age Group × Gender for 2025. No query parameters — dimensions are baked into the view ID.
**Python wrappers:** **None on PyPI.** R packages exist (`bnosac/BelgiumMaps.StatBel`, `weRbelgium/BelgiumStatistics`); Python users hand-roll a `requests` client and parse the proprietary "facts" JSON.
**Blockers:** No PxWeb/JSON-stat — cannot port SCB client; need new "facts" parser. No server-side dimension filtering — fetch whole view + client-side filter, or hand-curate a view-ID registry. Some dimensions (1-yr age, custom hour bands, DEGURBA) require parsing bulk Open Data XLSX. Mixed NL/FR/DE/EN labels complicate discovery.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable from open unauthenticated Statbel, but the proprietary non-PxWeb format, lack of dimension-level query parameters, and absence of a Python SDK mean substantial rewrite of `SCBPxWebClient` plus a hand-curated view-ID registry are required.

#### Bulgaria
**API name & URL:** NSI Open Data portal (`https://www.nsi.bg/opendata/`) backed by Infostat (`https://infostat.nsi.bg/infostat/`); plus an SDMX 2.1 dissemination database at `https://www.nsi.bg/ddb2.1/?l=en` (narrower scope: tourism, agriculture, national accounts, SBS).
**Technology stack:** PHP query-string endpoints returning CSV (`getopendata.php`) or JSON-stat (`getopendata_json.php`), plus `getfields.php` and `getcodelists.php` for metadata. **Not** PxWeb. SDMX-RI parallel service for separate domains.
**Auth/limits:** No auth, no registration. No published rate limits. SDMX cited at ~1k records/1–4 s.
**Coverage:** 16/16 (10 ✓, 6 partial). Datasets: 98 (population by region/age/sex), 96 (education ISCED), LFS modules 28-39, EU-SILC 73-75 (income), 27/71 (vital stats). Partial: employment type detail, hours bands, housing tenure (no dedicated dump), birth-country detail, parental structure as clean dimension.
**Classifications:** ISCED 2011, NACE Rev. 2, NUTS-2/3, ISCO, DEGURBA via Eurostat alignment.
**Example query:** `GET https://www.nsi.bg/opendata/getopendata_json.php?l=en&id=98` returns JSON-stat for population by region × age × residence × sex. Field metadata at `getfields.php?l=en&id=98`.
**Python wrappers:** No NSI-specific package on PyPI. Generic JSON-stat parsing works with `pyjstat`. SDMX flows accessible via `pandasdmx`/`sdmx1`.
**Blockers:** PHP query-string endpoints, not PxWeb — existing SCB query builders cannot be reused; numeric dataset IDs hand-discovered (no machine-readable catalogue). Some EU-SILC dimensions easier from Eurostat. No published rate limits/SLA. Infostat richer cube builder requires login and is not API-driven.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions reachable (mostly via JSON-stat open-data endpoints, with EU-SILC/Eurostat fallback for a few), but the non-PxWeb PHP interface and absent dataset catalogue mean the SCB fetch layer must be rewritten rather than reconfigured.

#### Cyprus
**API name & URL:** CYSTAT-DB (Statistical Service of Cyprus) — base API `https://cystatdb.cystat.gov.cy/api/v1/en/8.CYSTAT-DB/`; web UI at `https://cystatdb.cystat.gov.cy/pxweb/en/8.CYSTAT-DB/`.
**Technology stack:** **PxWeb v2.0** (same family as SCB). POST queries returning JSON-STAT, JSON-STAT2, JSON, CSV, XLSX, PC-Axis. Identical mechanics — should be near drop-in for the SCB client.
**Auth/limits:** No auth; public. No documented rate limits in the user manual; PxWeb defaults likely apply (~10 req/10s, ~100k cells/query).
**Coverage:** 16/16 (12 ✓, 4 partial). Tables: 1820045E (age × sex; 5-yr bins), 0112010E (employment × education ISCED), LFS series, 1895114E (households by size), 1895410E (household type), `predefined/31`/`predefined/64` (urban/rural). Partial: 1-yr age (5-yr only), housing tenure (census-only), birth country detail (mostly grouped), annual cadence (some census-only decennial).
**Classifications:** ISCED, NACE Rev. 2 / 2025 update, ISCO, NUTS (Cyprus = single NUTS-2; districts as NUTS-3), EU-SILC.
**Example query:** `POST https://cystatdb.cystat.gov.cy/api/v1/en/8.CYSTAT-DB/Population/Population/1820045E.px` body `{"query":[{"code":"YEAR","selection":{"filter":"item","values":["2024"]}},{"code":"SEX","selection":{"filter":"item","values":["1","2"]}},{"code":"AGE GROUP","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** `pyaxis` (.px → pandas), `pxweb` (R-equivalent in Python via `requests`). Existing SCB client portable by swapping base URL.
**Blockers:** Age binning is 5-yr (not 1-yr). Several rich cross-tabs (housing tenure × age, family-type × district, birth-country detail) are census-only (2021), no annual refresh. Income tables sparser than SCB; deciles often only in PDF EU-SILC publications. Tables split across parallel hosts (`cystatdb20`, `cystatdb23px`). Manual is PDF-only — no OpenAPI/Swagger.
**Feasibility verdict:** **MEDIUM** — A real PxWeb v2 instance technically interchangeable with SCB and covering ~12/16 dimensions adequately, but coarser age granularity, census-only housing/family tables, and weak PxWeb income-decile coverage mean adaptation plus partial reliance on Census-2021 snapshots.

#### Croatia
**API name & URL:** Croatian Bureau of Statistics (Državni zavod za statistiku, DZS) PxWeb API. Base: `https://web.dzs.hr/PxWeb/api/v1/en/` (browse UI: `https://web.dzs.hr/PxWeb/pxweb/en/`). The newer portal `podaci.dzs.hr` is a download/publication portal (XLSX, no API).
**Technology stack:** **PxWeb v1** (PC-Axis). Same protocol family as SCB — HTTP GET for navigation, POST queries for data. Returns JSON, JSON-stat, JSON-stat2, CSV, XLSX, .px. ~20 thematic databases (Stanovništvo/Population, Zaposlenost i plaće/Employment & Wages, Cijene, Turizam, Regionalna statistika, etc.).
**Auth/limits:** No auth, no registration. Open Licence. Standard PxWeb cell-count limit per query (typically 100k–800k cells; not publicly documented for DZS — chunking required for large age × sex × region cubes).
**Coverage:** 16/16 (10 ✓, 6 partial). Population DB + 2021 Census (1-yr ages × M/F), Census + Science/Technology DB (education ISCED), Anketa o radnoj snazi LFS, NKD 2007 (= NACE Rev. 2), 2021 Census housing tenure + household size, Census + vital stats (civil status), 21 counties = NUTS-3, Census birth location, Census family composition. Partial: ISCED granularity, employment type detail, hours bands, EU-SILC income deciles, top-20 birth-country breadth, DEGURBA (urban/other only — derivable via Eurostat crosswalk).
**Classifications:** NKD 2007 (≡ NACE Rev. 2), NUTS 2021 (HR0 → 4 NUTS-2 → 21 NUTS-3 counties), KLASUS classification database, ISCO-08, ISCED 2011. Census 2021 is the primary source for most demographic dimensions.
**Example query:** `POST https://web.dzs.hr/PxWeb/api/v1/en/Stanovni%C5%A1tvo/<table>.px` body `{"query":[{"code":"Spol","selection":{"filter":"item","values":["1","2"]}},{"code":"Starost","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`. Exact dbid path resolved by walking `/api/v1/en/` then descending — same pattern as SCB.
**Python wrappers:** `pyaxis` (.px parser), `pxweb` (R, well-supported); generic Python PxWeb clients (`pxwebpy`, `pyjstat`). The SCB-targeted `scb_client.py` in this repo is trivially repointable since the protocol is identical.
**Blockers:** Croatian-language dbids/codes (`Stanovništvo`, `Spol`, `Starost`) require URL-encoding and a Croatian category-mapping file analogous to `category_mappings.json`; English UI exists but variable codes often remain Croatian. Cell-count cap forces query chunking. Income decile granularity and DEGURBA weaker than SCB. Census 2021 is the latest full demographic snapshot — annual updates only for LFS/wages/vital stats. `podaci.dzs.hr` is the newer public-facing site but **does NOT expose an API**; the working API still lives on the legacy `web.dzs.hr/PxWeb/` host, which could be deprecated.
**Feasibility verdict:** **HIGH** — Genuine PxWeb v1 API covering 10/16 dimensions cleanly and the rest partially; existing SCB client and conditional sampling architecture port over with minimal changes (new base URL, Croatian category mapping, chunked queries).

#### Estonia
**API name & URL:** Statistics Estonia (Statistikaamet) PxWeb API at `https://andmed.stat.ee/api/v1/{lang}/stat/` (lang = `en` or `et`). Migrated from legacy `andmebaas.stat.ee` to PxWeb in Feb 2021.
**Technology stack:** PxWeb API v1 (same family as SCB). POST queries with JSON body; responses in JSON-stat, json-stat2, CSV, XLSX, .px. REST metadata via GET.
**Auth/limits:** No auth, no registration. CORS enabled. Per `?config`: max 25M cells/call, 1k calls/10 s window.
**Coverage:** 16/16 (14 ✓, 2 partial). Tables: RV021/RV022 (1-yr age × sex), Tooturg (LFS), Sissetulek ST… (income decile + components), Rahvaloendus 2021 (housing tenure), Leibkonnad (households 1P-7+). Partial: hours bands, DEGURBA (settlement type only).
**Classifications:** ISCED 2011, NACE Rev. 2 (national EMTAK 2008), NUTS-3 maakond (15), ESA-aligned LFS, ISO-3166 birth country.
**Example query:** `POST https://andmed.stat.ee/api/v1/en/stat/rahvastik/rahvastikunaitajad-ja-koosseis/rahvaarv-ja-rahvastiku-koosseis/RV021` body `{"query":[{"code":"Sugu","selection":{"filter":"item","values":["M","N"]}},{"code":"Vanus","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** `pxwebpy` (PyPI; json-stat2 → pandas/polars; works against `andmed.stat.ee`); `pyaxis` (.px parser); R `pxweb` lists Estonia. No Estonia-specific SDK.
**Blockers:** Variable codes Estonian (`Sugu`, `Vanus`, `Maakond`) even on `/en/`. Table IDs change after annual revisions. Some legacy series under "Discontinued datasets". Hours bands and DEGURBA need post-processing. PDF-only manual.
**Feasibility verdict:** **HIGH** — Same PxWeb v1 contract as SCB with all 16 dimensions covered (14 full, 2 partial), no auth, generous limits, mature Python tooling; SCB client + chained-sampling logic should port with minimal refactor beyond Estonian variable-code mappings.

#### Hungary
**API name & URL:** Hungarian Central Statistical Office (KSH/HCSO) High-Value Datasets API. Base: `https://data.ksh.hu/`. Catalogue: `https://data.ksh.hu/datasets.json`. STADAT bulk tables: `https://www.ksh.hu/stadat_files/...` (XLSX/CSV per table). OpenAPI spec at `https://data.ksh.hu/openapi.yaml`.
**Technology stack:** REST endpoints returning a DCAT-style JSON catalogue with RDF metadata per dataset; distributions in **CSV and SDMX (XML)**. **No JSON-stat, no PxWeb, no SDMX-JSON.** Bulk STADAT tables only via XLSX/CSV scraping.
**Auth/limits:** No auth, no quotas published; "act responsibly" guidance only. CORS blocked for browser clients (server-side OK).
**Coverage:** 16/16 (8 ✓, 8 partial). API exposes only ~13 High-Value datasets; demographic richness (housing tenure, household size, family type, DEGURBA) lives in STADAT HTML/XLSX, requiring scraping. Tables: nep0035 (age group × sex; no 1-yr ages), mun0001/0136 (LFS), mun0079/0112/0164 (NACE), jov0023 (income deciles), ele0004/0011 (housing tenure), nep0023 (foreign citizens by country), fol0006 (DEGURBA).
**Classifications:** NACE Rev. 2 (national TEÁOR'08), NUTS 2007/2021, ISCED, ICD-10, DEGURBA via Eurostat.
**Example query:** Catalogue: `GET https://data.ksh.hu/datasets.json` (find `f44d314b` = Population) → metadata: `GET https://data.ksh.hu/datasets/f44d314b/metadata.rdf` → parse `dcat:downloadURL` for CSV/SDMX. STADAT fallback: `GET https://www.ksh.hu/stadat_files/nep/en/nep0035.csv` (semicolon-separated, annual 2001-2026).
**Python wrappers:** No KSH-specific package. SDMX via `sdmx1`; CSV via `pandas.read_csv(sep=';')`; RDF via `rdflib`. No `pyjstat` path.
**Blockers:** Only ~13 HVD datasets via API; rest of demographics require STADAT scraping. No PxWeb-style POST queries — full distribution download + client-side slice. No JSON-stat — dropping the JSON-STAT v2 ingestion path used for SCB. Distribution URL pattern undocumented (RDF parse first). 1-yr age detail not in API; only Census-2022 microdata, behind a different portal.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions exist somewhere in KSH outputs (8 strong + 8 partial), but two parallel ingestion paths (HVD API + STADAT CSV scraping) and a custom CSV/SDMX adapter are required because there is no PxWeb/JSON-stat equivalent.

#### Latvia
**API name & URL:** Official Statistics Portal (OSP) of CSB Latvia — base API `https://data.stat.gov.lv/api/v1/{lang}/` (lang = `en` or `lv`); browseable PxWeb UI at `https://data.stat.gov.lv/pxweb/en/OSP_PUB/`.
**Technology stack:** **PxWeb v1** (same family as SCB/StatFin). POST queries with JSON body return JSON, JSON-stat v2, CSV, XLSX, PX. GET retrieves the database/table tree and metadata.
**Auth/limits:** No auth, no registration. Documented limits: max 3,800 cell values per call, 100 calls per 10 seconds.
**Coverage:** 16/16 (13 ✓, 3 partial). Tables: IRS010 (sex × age × territory annual), NBL series (LFS), NBL061 (NACE Rev. 2 employment), MVS020 (households by status), IRG011/IRG031 (marital status by sex × age), IRV040/050 (country of birth), RIG061 (urban/rural; experimental 2022-2025). Partial: working-hours bands, EU-SILC income decile detail, family/parental structure machine-friendliness.
**Classifications:** ISCED 2011, NACE Rev. 2 / 2.1, ISCO-08, NUTS-3, DEGURBA experimental, native marital-status codelist.
**Example query:** `POST https://data.stat.gov.lv/api/v1/en/OSP_PUB/START/POP/IR/IRS/IRS010` body `{"query":[{"code":"Sex","selection":{"filter":"item","values":["M","F"]}},{"code":"TIME","selection":{"filter":"top","values":["1"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** Generic PxWeb clients work directly — `pyaxis`, `pxstat`, `pxweb` (rOpenGov; Python ports exist), plus the SCB client in this repo can be repointed by swapping the base URL. CSBLatvia GitHub org has no Python wrapper.
**Blockers:** Table IDs and dimension codes differ entirely from SCB (`IRS010` vs `BE0101N1`); category mapping JSON must be rebuilt. Some labour/SILC variables aggregated rather than joint-distributed → conditional chained sampling for income × education × employment may need recoding. English labels exist but a few experimental tables are LV-only.
**Feasibility verdict:** **HIGH** — Same PxWeb stack as SCB with all 16 dimensions covered (13 full, 3 partial); existing client/sampler ports cleanly with only a new code-mapping layer.

#### Poland
**API name & URL:** Statistics Poland (GUS) — Bank Danych Lokalnych (BDL / Local Data Bank). Base: `https://bdl.stat.gov.pl/api/v1/`. Portal: `https://api.stat.gov.pl/Home/BdlApi`. Companion: DBW Knowledge Databases API at `https://api-dbw.stat.gov.pl/`.
**Technology stack:** REST API returning XML, JSON, JSON:API. **Not PxWeb, not JSON-stat, not SDMX.** Multidimensional variables identified by integer IDs queried via `/data/by-variable/{id}`. Geography conforms to NUTS.
**Auth/limits:** Optional `X-ClientId` header API key (free email registration). Anonymous: 5/sec, 100/15min, 1k/12h, 10k/7d. Registered: 10/sec, 500/15min, 5k/12h, 50k/7d.
**Coverage:** 16/16 (10 ✓, 6 partial). BDL covers single-year age × sex (Census 2021-fed), LFS variables, PKD-2007 (= NACE Rev. 2), Census household sizes, civil status by sex/age, NUTS-2/3 + powiats, official DEGURBA gmina classification. Partial: employment type joint cross-tabs, hours bands, income decile components (means per decile rather than full per-component decile tables), housing tenure (census tenure but coding differs from SCB), birth-location group, top-20 birth countries (granular cross-tabs in census Excel publications).
**Classifications:** PKD-2007 (= NACE Rev. 2), ISCED 2011, ISCO-08, NUTS 2021, TERYT, DEGURBA. EU-aligned.
**Example query:** Age × sex population, all voivodeships, 2023: `GET https://bdl.stat.gov.pl/api/v1/data/by-variable/72305?format=json&year=2023&unit-level=2`. Variable ID via `/api/v1/variables/search?subject-id=P2425&name=ludność`; `unit-level=2` = voivodeships.
**Python wrappers:** No official PyPI package. Community: `pygus` (mdyzma), `bdlapi` (doman84), MCP server `dvvbk/mcp-gus`. Official wrapper is R-only (`statisticspoland/R_Package_to_API_BDL`). For Python, a thin `requests`-based client mirroring `SCBPxWebClient` is the pragmatic path.
**Blockers:** Different protocol — not PxWeb/JSON-stat, so `SCBPxWebClient` cannot be reused. Two-step variable discovery (subjects → variables → integer IDs). Income decile components and detailed birth-country cross-tabs may live in published Excel rather than as BDL variables — scrape or use DBW. Documentation partly Polish-only; English Swagger exists but variable names bilingual at best.
**Feasibility verdict:** **HIGH** — All 16 dimensions obtainable from a single, free, well-documented REST API with EU-compatible classifications; only material work is writing a new `BDLClient` to replace `SCBPxWebClient` and resolving 3-4 partial dimensions via supplementary endpoints or DBW.

#### Czechia
**API name & URL:** Czech Statistical Office (ČSÚ / CZSO) — DataStat API at `https://data.csu.gov.cz/api/` (catalog: `/katalog/v1/`, query: `/dotaz/v1/`). Swagger UI at `https://data.csu.gov.cz/api/katalog/v1/swagger-ui/index.html`. Legacy LKOD endpoint at `https://vdb.czso.cz/pll/eweb/package_show?id=<id>`.
**Technology stack:** REST + **JSON-STAT v2** (also CSV, XLSX, HTML). Catalog of "sady" (datasets) → "ukazatele" (indicators) × "dimenze" (dimensions). Custom queries via POST `/dotaz/v1/data/sady/{sadaKod}/vlastni` with JSON body `{sloupce, radky, filtryTabulky}`. Predefined "vybery" selections retrievable as JSON-STAT or CSV. Not PxWeb, not SDMX.
**Auth/limits:** No auth, no registration, free reuse with attribution. No published rate limits.
**Coverage:** 16/16 (12 ✓, 4 partial). Tables: SLD050/OBY02B (age × sex × territory), SLD005/SLD042 (education), SLD021A043 (employment status), CZ-NACE codelist 5106 (RES02QNACEOBCE, SLD21A052 industry), SLD024 (housing tenure), SLD032/033 (households), SLD001/041 (marital status), SLD004 (place of birth). Partial: employment type detail, working-hours bands, income decile (mostly PDF/XLSX), top-20 birth-country, DEGURBA-labelled urbanization (uses size-of-settlement bands).
**Classifications:** CZ-NACE (= NACE Rev. 2), CZ-NUTS / KRAJ-OKRES-ORP, CZ-ISCO, education codelist mapped to ISCED. Exposed via `/katalog/v1/dimenze/{kod}/polozky`.
**Example query:** `GET https://data.csu.gov.cz/api/dotaz/v1/data/sady/SLD050/hodnoty/{ukazatelKod}?verze=1&kodyDimenzi=Vek,Pohlavi,Uzemi,CasR&kodyPolozek=...,M,CZ,2021&format=JSON-STAT`. Catalog: `GET /api/katalog/v1/sady/SLD050`.
**Python wrappers:** No first-class Python package on PyPI. Mature R package `czso` (petrbouchal) targets the legacy LKOD endpoint. DataStat itself has only Swagger — `requests` + `pyjstat` is the natural Python path.
**Blockers:** Most catalog UI labels Czech-only — discovery requires translation. DataStat is "trial run" — endpoint stability/versioning not fully guaranteed. Income deciles weakly represented (mostly PDFs). Top-20 birth-country and DEGURBA-style urban/suburban/rural may need derivation from Census micro-tables. No native Python SDK.
**Feasibility verdict:** **HIGH** — Documented REST + JSON-STAT API, no auth, covers 12/16 cleanly + 4 partial, and uses NACE/NUTS/ISCED-aligned classifications; swapping the SCB `PopulationDistributions` fetcher for a CZSO equivalent is a straightforward port (replace PxWeb POSTs with DataStat GETs / `/vlastni` POSTs and add Czech→English label maps).

#### Greece
**API name & URL:** **No native ELSTAT public API exists.** Realistic substitutes: (a) Eurostat SDMX 2.1/3.0 dissemination filtered to `geo=EL` — `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/` (and JSON-stat at `.../statistics/1.0/data/`); (b) data.gov.gr REST — `https://data.gov.gr/api/v1/query/{dataset}` (operational, not census).
**Technology stack:** Eurostat: REST + SDMX 2.1/3.0 + JSON-stat 2.0 (OpenAPI/Swagger). data.gov.gr: REST + JSON. **ELSTAT itself only publishes PDF/XLSX**; programmatic ingestion requires PDF table extraction (e.g. Camelot — confirmed by tdiam/greece-population-census-2021).
**Auth/limits:** Eurostat — no auth, soft fair-use cap (~50 req/min, 10 MB/response). data.gov.gr — Bearer token required (free registration at `data.gov.gr/token`). ELSTAT site — no auth but no API.
**Coverage:** 16/16 (13 ✓, 3 partial via Eurostat) — `demo_pjan` (1-yr age × sex), `edat_lfse_03` (ISCED), `lfsa_pganws` (employment), `lfsa_egan2` (NACE), `lfsa_etpga` (employment type), `lfsa_ewhun2` (hours, partial bands), `ilc_di01/04` (income decile, partial joint), `ilc_lvho02` (tenure), `lfst_hhnhtych`/`ilc_lvph03` (households), `demo_marsta` (civil status), `demo_r_pjangrp3` (NUTS-3 by age/sex), `migr_pop3ctb`/`migr_pop5ctz` (birth country, partial top-20), `lfst_hhindws` (parental, partial), `urt_pjanaggr3` (DEGURBA).
**Classifications:** ISCED 2011, NACE Rev. 2, NUTS 2021 (`EL30`-`EL65`), DEGURBA, ICSE, EU-SILC. All EU-harmonised.
**Example query:** `GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?geo=EL&sex=M,F&age=Y_LT1,Y1,...,Y_GE100&time=2024&format=JSON`
**Python wrappers:** `eurostat` (PyPI, JSON-stat); `pandasdmx`/`sdmx1` (Eurostat configured as built-in source `ESTAT`); `pyjstat`; `pydatagovgr` (ilias-ant) for data.gov.gr — but does not expose census/LFS endpoints.
**Blockers:** ELSTAT has no machine-readable API; native census results PDF/XLSX only. Sub-national income deciles and detailed birth-country tails are confidentiality-suppressed in Eurostat — full granularity requires SUF/PUF microdata application. Eurostat tables sometimes lag 1-2 years vs. SCB latest. Architectural change required: replace `SCBPxWebClient` with SDMX/JSON-stat client.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions sourceable via Eurostat at EU-harmonised classifications, but it is not a drop-in PxWeb replacement: client must be rewritten, several dimensions are partial (hours bands, deciles, birth-country tail, parental structure) and may need PDF/XLSX scraping of ELSTAT census tables.

#### Lithuania
**API name & URL:** OSP SDMX 2.1 RESTful Web Service (Official Statistics Portal, State Data Agency / LSD). Entry points: `https://osp-rs.stat.gov.lt/rest_json/` (JSON) and `https://osp-rs.stat.gov.lt/rest_xml/` (XML). Docs: https://osp.stat.gov.lt/rdb-rest. Portal: https://osp.stat.gov.lt.
**Technology stack:** **SDMX 2.1 REST** (NOT PxWeb — Latvia uses PxWeb, Lithuania does not). Responses in SDMX-ML 2.1 generic schema or SDMX-JSON. Agency ID `LSD`. Despite naming, fully different surface from SCB's PxWeb.
**Auth/limits:** No auth, anonymous queries only. Hard caps: 1,000,000 observations per response; URL length max 1000 chars. Only `startPeriod`/`endPeriod` query params supported. Annual format `YYYY`.
**Coverage:** 16/16 (12 ✓, 4 partial). "Determination of the Usually Resident Population" survey (1-yr age × sex × citizenship × country of birth × marital status), Census 2021 (education ISCED), LFS (employment), EVRK Rev. 2.1 = NACE Rev. 2 (industry), Census 2021 housing tenure, household sizes, marital status, 10 apskritys (NUTS-3). Partial: employment type cross-tabs, hours bands, full SILC income deciles, top-20 birth-country tail (small-cell suppression), DEGURBA tri-class (urban/rural binary only).
**Classifications:** EVRK Rev. 2.1 (= NACE Rev. 2), ISCED-aligned, NUTS (10 counties), Eurostat-aligned LFS/SILC. Codelists exposed via SDMX `datastructure` and `codelist` resources.
**Example query:** `GET https://osp-rs.stat.gov.lt/rest_json/data/S3R629_M3010217/?startPeriod=2023&endPeriod=2024`. Metadata: `GET https://osp-rs.stat.gov.lt/rest_xml/dataflow/LSD/S3R629_M3010217`. DSD: `GET https://osp-rs.stat.gov.lt/rest_xml/datastructure/LSD/M3010217/`. Generic shape: `protocol://entry/resource/flowRef/key/providerRef?queryStringParameters`.
**Python wrappers:** `pandaSDMX` and `sdmx1` (khaeru/sdmx) — LSD is registered. Caveats: XML endpoint returns `Content-Type: application/force-download` (breaks reader auto-detection) and produces malformed messages. **JSON endpoint is the recommended path.**
**Blockers:** Architectural mismatch — SCB code is PxWeb POST-with-JSON-query, LSD is SDMX REST with flow/key path syntax. `SCBPxWebClient` and `FetchService` query layer would need rewrite, not parameterisation. Dataflow IDs opaque (e.g. `S3R629_M3010217`); category mappings file would need full rebuild. JSON-STAT v2 (used by SCB) ≠ SDMX-JSON. Cross-tabs may only be marginals on OSP, forcing extra conditioning logic. DEGURBA 3-class and income deciles partial — Eurostat fallback needed.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions conceptually covered by LSD/Eurostat-harmonised data, but the API is SDMX (not PxWeb), so the existing `SCBPxWebClient`, query construction, and JSON-STAT parsing layers must be rewritten end-to-end rather than reconfigured.

#### Luxembourg
**API name & URL:** LUSTAT Data Explorer / STATEC SDMX REST API. Base: `https://lustat.statec.lu/rest/`. Browser portal: `https://lustat.statec.lu/`. Agency code: `LU1`. Built on .Stat Suite (OECD), launched April 2022 with 650+ tables.
**Technology stack:** **SDMX 2.1 REST** (.Stat Suite). Returns SDMX-CSV (default), SDMX-JSON, SDMX-ML. Format selectable via `Accept` header (`application/vnd.sdmx.data+json`) or `?format=jsondata|csvfile|csvfilewithlabels`. Different protocol than SCB; new client adapter required.
**Auth/limits:** No auth, no API key, no documented rate limit. Public open-data on data.public.lu under open licence. No registration.
**Coverage:** 16/16 (13 ✓, 3 partial). Census 2021 + annual `DF_B1113` (population × nationality × age × sex), `DSD_ESS_EARN_M@DF_C1218` (ISCED), `DSD_EMPLOI_*` (LFS), NACE Rev. 2, `DSD_SILC_2@DF_C1100` (income decile + components), Census housing tenure, Census + EU-SILC household composition, marital status, `DSD_CENSUS_HIST@DF_B1754` (country of birth 1880-2021), family types. Partial: employment type/self-emp split, working-hours bin alignment, region (LU = single NUTS-2; sub-national = 12 cantons / 100 communes), DEGURBA (derivable from commune-level density grid).
**Classifications:** ISCED 2011, NACE Rev. 2, ISCO-08, EU-SILC, DEGURBA derivable, NUTS (LU = single NUTS-2). Census 2021 is "combined" (questionnaires + administrative registers).
**Example query:** `GET https://lustat.statec.lu/rest/data/LU1,DF_B1113,1.0/all?startPeriod=2024&endPeriod=2024&dimensionAtObservation=AllDimensions` with `Accept: application/vnd.sdmx.data+json`. Dataflow discovery: `GET https://lustat.statec.lu/rest/dataflow/LU1/all/all`. Key syntax: `dim1+code.dim2.dim3` (`+` = OR, `.` = separator).
**Python wrappers:** `sdmx1` and legacy `pandaSDMX` both speak SDMX 2.1 REST and can register a custom source pointing at `https://lustat.statec.lu/rest/` (LU1 is not built-in but a 5-line `sdmx.add_source(...)` call). Returns pandas DataFrames natively.
**Blockers:** Different protocol from SCB — existing PxWeb client cannot be reused. Dataflow IDs opaque (`DF_B1113`, `DSD_SILC_2@DF_C1100`); discovery returns large XML and is paginated by topic — mapping the 16 SCB tables is a manual upfront task. LU = 1 NUTS-2 region — "regional" granularity differs (use cantons or communes). Smaller population (~660k) → high cell-suppression risk for joint distributions. Census decennial (latest 2021); inter-census years rely on register-based estimates.
**Feasibility verdict:** **HIGH** — Public, unauthenticated SDMX 2.1 REST covering all 16 dimensions with mature Python SDK support (`sdmx1`); the only real cost is writing a new SDMX adapter to replace the PxWeb-specific SCB client.

#### Portugal
**API name & URL:** Statistics Portugal (Instituto Nacional de Estatística, INE) — JSON Indicators API at `https://www.ine.pt/ine/json_indicador/pindica.jsp` (data) and `pindicaMeta.jsp` (metadata); catalog at `xpgid=ine_api_catalogo`; metadata system at `http://smi.ine.pt/`.
**Technology stack:** Custom REST/JSON (NOT PxWeb, NOT JSON-stat). GET requests with query params: `op=2&varcd={indicator}&Dim1={time}&Dim2={geo}&Dim3=...&lang=EN|PT`. Response is bespoke INE JSON shape (array of indicators with `Dados.{period}` blocks listing dimension code combinations).
**Auth/limits:** No auth, no API key, no registration. Free public access. Hard cap of **40,000 data points per call** (wrappers paginate internally). No documented per-second rate limit.
**Coverage:** 16/16 (12 ✓, 4 partial). Indicator 0008273 (resident pop by sex × age group; 5-yr bands, not 1-yr — 1-yr ages exist in cohort/estimates tables). Census 2021 indicators (education ISCED, tenure, household size, marital status, family-nucleus type), Inquérito ao Emprego (LFS), CAE Rev.3 (= NACE Rev. 2) industry, indicator 0001236 (foreign residents by country). Partial: 1-yr age, hours bands, EU-SILC income deciles cross-tabbed with demographics, DEGURBA (Tipologia de Áreas Urbanas APU/AMU/APR).
**Classifications:** NUTS-2013, CAE Rev.3 (= NACE Rev. 2), CNP/ISCO-08, education aligned to ISCED 2011, ICC for citizenship/country.
**Example query:** `https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=0008273&Dim1=S7A2021&Dim2=0&Dim3=T&lang=EN` (varcd=0008273 resident pop; Dim1=year; Dim2=geo; Dim3 sex codes 1=M, 2=F, T=both).
**Python wrappers:** No mature Python package specific to INE Portugal. `ineptR` (R, CRAN) handles pagination. `mmngreco/ine-python` exists but unmaintained/thin. `ineware` and `INEapy` on PyPI are for **Spain's** INE, not Portugal. Direct `requests` client is the realistic path.
**Blockers:** No JSON-stat / PxWeb — bespoke response shape requires custom parser; SCB code cannot be reused. Dimension codes (`S7A2021`, sex=`1/2/T`) must be discovered via metadata endpoint or web UI. Age usually in 5-yr bands; 1-yr ages need a different indicator. 40k-point cap forces chunking by year/region. Income deciles cross-tabbed with demographics thinner than SCB. No actively maintained Python SDK.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable with broadly comparable depth to SCB, but the bespoke JSON format and absence of a maintained Python wrapper mean a new `INEPortugalClient` parser plus dimension-code discovery layer is required before substitution.

#### Romania
**API name & URL:** Institutul Național de Statistică (INS / INSSE) — TEMPO-Online. Public JSON API at `http://statistici.insse.ro:8077/tempo-ins/` (context + matrix endpoints); browser UI at `http://statistici.insse.ro:8077/tempo-online/`.
**Technology stack:** REST-ish JSON over HTTP (note: **HTTP only, non-standard port 8077**). POST queries to `/tempo-ins/matrix/{CODE}` with JSON body listing dimension selections (`arr`, `nomItemId`, `offset`, `parentId`); metadata via `/tempo-ins/context/`. Not PxWeb, not JSON-stat. Minimal SDMX 2.1 endpoint exists on community mirrors but unofficial.
**Auth/limits:** No auth, no API key, no documented rate limit. Hard cap ~30,000 cells per response (large pulls split by judet/year). HTTP-only (no TLS).
**Coverage:** 16/16 (10 ✓, 6 partial). Matrix POP107D (resident pop × age × sex × county), POP/EDU (education attainment), AMIGO/HLFS quarterly (FOM series), NACE Rev. 2 across FOM/SAL, AMIGO LFS (employment type), Census household sizes, POP census/vital stats (marital status), 41 judete + Bucharest (NUTS-3), Census 2021 + migration (foreign-born EU/non-EU). Partial: hours bands, ABF income deciles (PDF/XLSX), Census-only housing tenure, top-20 birth countries, parental structure, urbanization (urban/rural binary, no DEGURBA suburban tier).
**Classifications:** NACE Rev. 2, ISCO-08, ISCED 2011, NUTS 2021 (judet = NUTS-3), national urban/rural (no DEGURBA tier).
**Example query:** `POST http://statistici.insse.ro:8077/tempo-ins/matrix/POP107D` body `{"language":"en","matrixName":"POP107D","matrixDetails":{"nomJud":0,"nomLoc":0},"arr":[[{"label":"Total","nomItemId":1,"offset":1,"parentId":null}],[{"label":"Male","nomItemId":1,"offset":1,"parentId":null},{"label":"Female","nomItemId":2,"offset":2,"parentId":null}]]}`.
**Python wrappers:** `tempo-py` (PyPI, GitHub mark-veres/tempo.py) — wraps context + matrix endpoints. `LeafNode.by_code('POP105A').query(...)`. Lower-level scrape pipeline `gov2-ro/tempo-ins-dump`. R: `rTempo`.
**Blockers:** HTTP-only on non-standard port 8077 (proxies/firewalls block); no formal API spec or SLA; 30k-cell cap forces per-county pagination; matrix labels/IDs mostly Romanian; ISCED/NACE labels need normalising; income-decile and detailed birth-country in PDFs; no DEGURBA suburban category; `tempo-py` is small single-author package with limited maintenance.
**Feasibility verdict:** **MEDIUM** — TEMPO-Online + `tempo-py` cover core demographic/LFS dimensions cleanly, but ~6 dimensions need partial workarounds (PDF parsing or Census micro-tables), and the brittle HTTP-only endpoint plus cell cap demand more engineering than SCB's PxWeb.

#### Slovakia
**API name & URL:** Statistical Office of the Slovak Republic (Štatistický úrad SR / SO SR) — Open data API to DATAcube. Base: `https://data.statistics.sk/api/v2/` (root portal: `slovak.statistics.sk`; browser DB: `datacube.statistics.sk`). Successor "STATdata" being migrated in.
**Technology stack:** RESTful HTTP GET, **URL-path parameter style** (no POST query body, unlike SCB PxWeb). Returns JSON-stat v2 (default), plus CSV, XML, XLSX, ODS. Three endpoints: `/collection`, `/dimension/{cube}/{dim}`, `/dataset/{cube}/{P1}/{P2}/...`. Selectors: `all`, `lastN`, comma-list, `a:b` ranges, `*` wildcard.
**Auth/limits:** No registration, no API key, free, CC-BY 4.0. URL ≤ 2000 chars; ≤ 10,000 cells per response. Refreshed twice daily (10:00, 22:00). No documented per-IP rate limit.
**Coverage:** 16/16 (10 ✓, 6 partial). DATAcube tables: demography by sex/age/marital status (1-yr ages at municipal level), Census + LFS education ISCED, VZPS LFS, NACE Rev. 2, EU-SILC + Census 2021 housing, census household sizes, marital status, NUTS-3 kraj (8) + LAU-1 okres. Partial: working-hours bands, EU-SILC quintile vs decile, top-N birth country (low immigrant share → suppression), parental structure, urban/rural at municipal level (full DEGURBA via external join).
**Classifications:** ISCED 2011, NACE Rev. 2, ISCO-08, NUTS 2021 (SK01-SK04), LAU, COICOP. Codelists exposed via `/dimension/{cube}/{dim}`.
**Example query:** Cube `om7102rr` ("Population by sex, age and family status"): `https://data.statistics.sk/api/v2/dataset/om7102rr/all/all/last1?lang=en&type=json`
**Python wrappers:** No SO-SR-specific SDK. Output is standard JSON-stat v2 → `pyjstat` (predicador37) reads responses straight into pandas DataFrames; `requests` + `pyjstat` is the canonical stack. `pxweb` does **not** work — SO SR is not a PxWeb server.
**Blockers:** URL-only query model — no POST body; large dimension selections must use `all`/ranges or risk exceeding 2000 chars. 10k-cell ceiling forces pagination. Cube codes are opaque 8-char IDs requiring catalog discovery. Slovak labels by default — must pass `?lang=en`. DATAcube → STATdata migration may break cube codes mid-2025/26. Census granularity drops to 2021 (next 2031). Low immigrant share → cell suppression for country-of-birth detail.
**Feasibility verdict:** **HIGH** — All 16 SCB dimensions have direct or near-direct DATAcube analogues over a free, no-auth, JSON-stat REST API; the SCB PxWeb client just needs a thin adapter that swaps POST-body queries for SO-SR's path-parameter URLs.

#### Slovenia
**API name & URL:** SiStat Database PxWeb API (Statistical Office of the Republic of Slovenia, SURS). Base: `https://pxweb.stat.si/SiStatData/api/v1/{lang}/Data/{table_id}.px` (lang = `en` or `sl`). Portal: `https://pxweb.stat.si/sistat/en`.
**Technology stack:** Standard **PxWeb v1** API. GET returns JSON metadata; POST with JSON query body returns JSON-stat (default), JSON, CSV, XLSX, PX. Identical query grammar to SCB.
**Auth/limits:** No auth, no registration. PxWeb-typical limits (~100,000 cells per query, 30 requests / 10 seconds → HTTP 429). Slovenian help advertises up to 10,000,000 values per call — generous compared to SCB.
**Coverage:** 16/16 (13 ✓, 3 partial). Table 05C4002S (population × SEX × MUNICIPALITIES × HALF-YEAR × AGE 0-85+; M/F/Total), education subject (ISCED 2011), LFS quarterly, NACE Rev. 2, LFS detailed status-in-employment, EU-SILC accommodation tenure, "Households and families" 2021, demographics marital status, 12 statistical regions (NUTS-3), foreign-born EU/non-EU + top countries (BiH, Croatia, Serbia, Germany), family typology (lone-parent, consensual unions, couples). Partial: working-hours bin alignment, full D1-D10 deciles (likely quintiles), DEGURBA (5-class settlement type, no native DEGURBA).
**Classifications:** NACE Rev. 2, ISCED 2011, ISCO, NUTS-3 (12 statistical regions), municipality codes (Obc2015 map), country codes for citizenship/birth.
**Example query:** Metadata `GET https://pxweb.stat.si/SiStatData/api/v1/en/Data/05C4002S.px`. Data POST to same URL with body `{"query":[{"code":"SEX","selection":{"filter":"item","values":["1","2"]}},{"code":"AGE","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`.
**Python wrappers:** `pxwebpy` (PyPI) and R's `pxweb` work against any PxWeb v1 endpoint and should work with SiStat by URL substitution (not in the officially tested list, but protocol-identical). `pyaxis` parses raw .px exports. `sebenik/sistat-api` exists but is PHP and stale.
**Blockers:** No native v2/JSON-stat2-only endpoint advertised — code paths assuming SCB's exact base path need parameterising. Income deciles may resolve only to quintiles. DEGURBA may need Eurostat fallback. SURS table IDs and Slovenian-only labels in some tables require an English-language toggle and a category-mapping file analogous to the existing `category_mappings.json`.
**Feasibility verdict:** **HIGH** — Tier-1 PxWeb installation with the same query grammar, no auth, generous limits, and coverage of 13/16 dimensions cleanly plus 3 partials; substituting SCB is mostly swapping the base URL, table IDs, and label mappings.

#### Malta
**API name & URL:** NSO Malta StatDB (".Stat Suite" / SIS-CC). Browser UI: `https://statdb.nso.gov.mt/`. SDMX REST endpoints: `https://apidesign-statdb.nso.gov.mt/rest/` (design space, has data) and `https://apirelease-statdb.nso.gov.mt/rest/` (release, only 2 flows).
**Technology stack:** **SDMX 2.1 REST + SDMX-JSON 2.0 + SDMX-ML 2.1** (NSI Web Service v8.9.2). Not PxWeb. JSON-stat NOT supported. Format negotiated via `Accept: application/vnd.sdmx.data+json;version=2.0`.
**Auth/limits:** No auth required (Keycloak realm advertised but `required:false`). CORS open. No published rate limits. `dataflow/all` rejects HEAD (405) — GET only.
**Coverage:** 16/16 (7 ✓, 2 partial, 7 ✗). `DF_TOT_POP_BY_SEX_SINGLE_YEARS_AGE` (1-yr × sex × time) ✓, `DF_LABOUR_STATUS_*` (LFS) ✓, `DF_TOTAL_EMP_CLASSIFIED_BY_ECONOMIC_ACTIVITY` / `DF_NA_NAMA10A64E` (NACE) ✓, `DF_TOT_POP_BY_REG_DIST_LOC` (Malta/Gozo NUTS-3) ✓, `DF_POPSTAT_05R` (birth group) ✓, time-indexed ✓. Partial: education `DF_EDU_LVL_SUCC_COM_PER_AGE_15_PLUS_YEARS` (not joint with age/sex), employment type (employee/self-emp only — perm/temp absent), birth country detail (grouped, not country-level). **Missing entirely:** working-hours bands, income deciles, housing tenure, household size, civil status, parental structure, DEGURBA.
**Classifications:** NACE Rev. 2, ISCO-08, ISCED, ESA 2010, ECOICOP v2, Eurostat-aligned LFS/EU-SILC. Region: Malta/Gozo (NUTS-3) + 6 districts + ~68 localities (LAU-1).
**Example query:** `GET https://apidesign-statdb.nso.gov.mt/rest/data/DF_TOT_POP_BY_SEX_SINGLE_YEARS_AGE/all/all/?format=jsondata&dimensionAtObservation=AllDimensions` with header `Accept: application/vnd.sdmx.data+json;version=2.0`. Verified live — returns SDMX-JSON 2.0 with sex × age × time observations.
**Python wrappers:** `sdmx1` (PyPI, recommended — supports SDMX 2.1/3.0 and custom .Stat Suite endpoints) and `pandaSDMX` (legacy). Neither ships a built-in "MT/NSO" source — must register the Malta endpoints manually via `sdmx.add_source({...})`. No PxWeb client will work.
**Blockers:** **Roughly 7 of the 16 dimensions have NO dataflow** (tenure, household size, civil status, hours, deciles, family structure, DEGURBA) — would require Excel/PDF scraping of Census 2021 + EU-SILC reports or fallback to Eurostat. Every dataflow on the design endpoint carries `NonProductionDataflow=true`; release endpoint exposes only 2 flows — stability/SLA uncertain. DSD codelists differ from Eurostat IDs. Malta is a single NUTS-2 / 2-NUTS-3 country, so regional granularity coarser than Sweden's 21 counties.
**Feasibility verdict:** **MEDIUM** — Clean SDMX 2.1 API with real current data covers ~9 of 16 SCB dimensions directly, but ~7 require Eurostat fallback or document scraping, and the production-readiness flag is concerning; substituting SCB requires a hybrid SDMX + Eurostat strategy plus a new client class.

### Europe — Non-EU (batch 2)

#### Albania
**API name & URL:** INSTAT Statistical Database (Databaza Statistikore), PxWeb portal at `https://databaza.instat.gov.al:8083/pxweb/en/DST/`. Programmatic API: `https://databaza.instat.gov.al:8083/pxweb/api/v1/{lang}/DST/{level}/{TABLE_ID}` (legacy host `instat.gov.al:8080/api/al/DST/...` is documented but unreliable).
**Technology stack:** **PxWeb** (Statistics Sweden's open-source platform — same family as SCB). GET returns JSON metadata; POST returns JSON-stat / JSON / CSV / XML / PX. No SDMX endpoint. Separate ArcGIS REST + GeoServer at `geodatahub.instat.gov.al` for spatial only.
**Auth/limits:** No auth, no API key. Standard PxWeb soft cap (~10 calls/10s, max ~100,000 cells/query) applies; not formally published. HTTPS works on port 8083; root `:8083/api/v1/` returned 404, so callers must hit `/pxweb/api/v1/...`.
**Coverage:** 16/16 (6 ✓, 9 partial, 1 ✗). POP01 (5-yr age groups × M/F/Total 2001-2025; **no 1-yr ages**), START__ED (enrolment/graduation flows; stock ISCED only via Census 2023), START__TP__LFS (LFS quarterly + yearly), NACE Rev. 2, LSMS51 (avg household size), START__BD__MAR (marriage flows; stock via Census 2023), 12 prefectures (NUTS-3), MIM6 (foreign residents by **continent** only — no country detail), Census 2023 household composition, urban/rural. Missing entirely: top-20 birth-country detail.
**Classifications:** ISCO-08, NACE Rev. 2, ISCED 2011, COICOP, NUTS-equivalent (12 prefectures / 61 municipalities). Census 2023 is the third post-1990 census.
**Example query:** `POST https://databaza.instat.gov.al:8083/pxweb/api/v1/en/DST/DE/POP01/` body `{"query":[{"code":"Grupmosha","selection":{"filter":"all","values":["*"]}},{"code":"Gjinia","selection":{"filter":"item","values":["Meshkuj","Femra"]}},{"code":"Viti","selection":{"filter":"item","values":["2024"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** No Albania-specific wrapper. Generic options: `pyaxis`, `pxweb` (R; Python via `requests` is trivial since protocol matches SCB). Existing SCB client in `utils/scb_client.py` could be parameterised with minor changes.
**Blockers:** Many critical dimensions (tenure, civil-status stock, birth country, parental structure, urban-rural classes, ISCED stock) live only in **Census 2023** tables — single snapshot, no annual updates. **No country-detail birthplace breakdown** anywhere. Income deciles published as poverty/AROPE indicators rather than D1-D10 shares. Variable codes Albanian (`Grupmosha`, `Gjinia`, `Viti`). Non-standard port 8083 + occasional 500s suggest infrastructure less hardened than SCB.
**Feasibility verdict:** **MEDIUM** — Same PxWeb protocol as SCB makes the client trivially portable, and ~11 of 16 dimensions are achievable, but ~5 are partial/missing/Census-snapshot-only.

#### Serbia
**API name & URL:** Statistical Office of the Republic of Serbia (SORS / RZS) Open Data Service. Catalog UI: `https://opendata.stat.gov.rs/odata/?id=en-us`. Live REST API: `https://opendata.stat.gov.rs/data/WcfJsonRestService.Service1.svc/dataset/{INDICATOR_ID}/3/{json|csv}` (verified HTTP 200, ~3.9 MB JSON for indicator `010101IND01`). Parallel browse-only portal at `data.stat.gov.rs` (SDDB) has no documented machine API.
**Technology stack:** Custom WCF (Microsoft IIS / ASP.NET) JSON & CSV REST service. Despite the `/odata/` URL prefix, **NOT real OData** — `$metadata`, `$filter`, `$top` all return 404. Returns flat row arrays (one fact row per dimension combination), Serbian-Cyrillic property names (`idindikator`, `IDTer`, `nTer`, `god`, `vrednost`). Not PxWeb, not SDMX, not JSON-stat.
**Auth/limits:** No auth, no API key, no documented rate limit. Public CC-BY-style reuse (attribution required). Slow first-byte (~7 s observed); responses are full-table dumps with no server-side filtering.
**Coverage:** 16/16 (8 ✓, 8 partial). LFS quarterly + 10k-household sample (employment, NACE Rev. 2, ICSE perm/temp/self), Census 2022 (households by size, marital status, urban/other in `IDTipNaselja`/`nTipNaselja`), NSTJ classification (Serbian NUTS — region/area/municipality), most indicators since 2006 + LFS revised to 2011. Partial: 1-yr age (5-yr groups standard, 1-yr only in census book exports), hours bands, EU-SILC deciles (no D1-D10 indicator confirmed), Census-only housing tenure, Census-only birth location/country detail, parental structure (Census family-nucleus tables only).
**Classifications:** NSTJ (Serbian NUTS), NACE Rev. 2, ISCO-2008, ISCED-2011, ISCED-F 2013, ICSE-93. Census 2022 is the freshest reference.
**Example query:** `GET https://opendata.stat.gov.rs/data/WcfJsonRestService.Service1.svc/dataset/18010403IND01/3/json` (indicator IDs follow `{subject_path}IND{nn}`). Whole-table fetch, client-side filter on `IDTer`, `god`, age/sex columns.
**Python wrappers:** **None found.** No PyPI/GitHub package wraps SORS. Standard `requests` + `pandas.json_normalize` works directly. `pyjstat`/`pxweb` are NOT compatible.
**Blockers:** **No query-time filtering** — must download full multi-MB JSON per indicator and filter locally. Property names are Serbian; ad-hoc per-table column mapping needed. **No discovery endpoint** — ~688 indicator codes must be scraped from catalog HTML. **No joint `(age, sex)` 1-year table** — Sweden's `BefolkningR1860` equivalent does not exist; need census flat files. Excludes Kosovo since 1999. UI-driven SDDB at `data.stat.gov.rs` is unrelated and offers no API.
**Feasibility verdict:** **MEDIUM** — Coverage of all 16 dimensions exists in raw form and the REST endpoint is open and stable, but the absence of PxWeb/SDMX server-side filtering, lack of a Python SDK, Serbian-only field names, and the need to scrape 688 indicator codes plus stitch census flat-files for 1-yr age × sex mean a SCB-equivalent adapter is roughly 2-3× more engineering work than Sweden.

#### Switzerland
**API name & URL:** Swiss Federal Statistical Office (FSO/BFS/OFS) — STAT-TAB PxWeb API. Base: `https://www.pxweb.bfs.admin.ch/api/v1/{en|de|fr|it}/`. Catalog: `https://www.pxweb.bfs.admin.ch/pxweb/en/`. A successor "Swiss Stats Explorer" (.Stat / SDMX) is also rolling out.
**Technology stack:** **PxWeb** (same engine as SCB), POST-based JSON queries, JSON-stat v2 responses, also PX, CSV, XLSX. Multilingual (EN/DE/FR/IT). CORS enabled.
**Auth/limits:** No auth, no registration. Hard limits via `/api/v1/en/?config`: `maxValues=5000`, `maxCells=100000` per query, max **50 calls per 15 min** (HTTP 429 confirmed). Identical envelope to SCB.
**Coverage:** 16/16 (15 ✓, 1 partial). Tables: px-x-0102010000_101 (resident pop × citizenship × sex × age 2010-2024), px-x-1502040100_131 (education ISCED-aligned), SAKE/ESPA LFS (px-x-0302/0602), NOGA 2008 (= NACE Rev. 2), px-x-0302010000_106 (cross-border by employment status), px-x-0602010000_102 (full-time/part-time), Structural Survey housing tenure, household size, px-x-0102010000_103 (marital status × age class), 26 cantons (= NUTS-3), px-x-0103030000_221 / 0103020200_103 (country of birth top-N), one-family households (asset 34507027), DEGURBA on 300m grid → commune-level. Partial: full income decile cubes (most as static publications/HBS).
**Classifications:** ISCED, NOGA 2008 (= NACE Rev. 2), ISCO-08, DEGURBA (Eurostat), cantons (NUTS-3), ISO country codes. Highly Eurostat-aligned.
**Example query:** `POST https://www.pxweb.bfs.admin.ch/api/v1/en/px-x-0102010000_101/px-x-0102010000_101.px` body `{"query":[{"code":"Year","selection":{"filter":"item","values":["2024"]}}],"response":{"format":"json-stat2"}}`
**Python wrappers:** `pyaxis` (co-maintained by Swiss Data Science Center, explicit BFS examples); `pxwebpy` (generic PxWeb, json-stat2); `pyjstat`; `jsonstat.py`. R has dedicated `BFS` (lgnbhl) — no first-party Python equivalent, but generic PxWeb clients work unchanged because the API surface matches SCB.
**Blockers:** 50-calls / 15-min throttle is **tighter than SCB** and will need backoff/caching for 16-table fetches. Some cubes migrating off STAT-TAB to Swiss Stats Explorer (.Stat/SDMX) — table IDs may churn over 1-2 years. Income-decile coverage thinner than SCB (publication-style rather than full cubes). Table identifiers are opaque `px-x-NNNNNNNNNN_NNN` codes requiring catalog discovery.
**Feasibility verdict:** **HIGH** — Same PxWeb/JSON-stat protocol as SCB means existing client and ingestion code transplant almost unchanged; 15/16 dimensions fully covered with only income-decile granularity needing care.

#### Ukraine
**API name & URL:** State Statistics Service of Ukraine (Derzhstat / SSSU). SDMX endpoint at `https://stat.gov.ua/sdmx/workspaces/default:integration/registry/sdmx/` (docs: `https://stat.gov.ua/en/development-api`). Legacy site `ukrstat.gov.ua` hosts static HTML/PDF only.
**Technology stack:** **SDMX 2.1 and SDMX 3.0** over REST/HTTP GET; output in JSON or XML (no PxWeb, no JSON-stat). ~80+ dataflows registered under agency ID `SSSU`. Also Excel/CSV/SDMX-ML downloads on the portal.
**Auth/limits:** No documented auth, registration, or rate limits.
**Coverage:** 16/16 (3 ✓, 7 partial, 6 ✗). LFS dataflow ✓, KVED (= NACE Rev. 2) ✓, 27 oblasts (NUTS-3 proxy) ✓, annual time series ✓ (interrupted/footnoted from 2014 Crimea/Donbas, 2022 full invasion). Partial: age × sex (estimates, not census; last census 2001), education (ISCED mapping "not fully comparable"), employment type cross-tabs, hours bands, income decile (HLCS publishes ratios; full D1-D10 not consistently in SDMX), household size (HLCS publications, SDMX exposure thin), civil status (stock tied to 2001 census), urbanisation (urban/rural binary, no DEGURBA). **Missing entirely:** housing tenure, birth-location group, birth-country detail, parental structure.
**Classifications:** KVED 009:2010 (= NACE Rev. 2), KVED-NACE 2.1-UA from 2027; ISCED via UNESCO UIS (partial); COICOP-HBS for consumption; oblast codes (no official NUTS).
**Example query:** `GET https://stat.gov.ua/sdmx/workspaces/default:integration/registry/sdmx/2.1/data/DF_POPULATION/*.*.*.*.*/SSSU?format=jsondata`. Dataflow listing: `…/2.1/dataflow/SSSU/all/latest`.
**Python wrappers:** No Ukrstat-specific package. Generic SDMX clients work: `pandasdmx`/`sdmx1` (add custom source pointing at SSSU endpoint). `govpack` wraps `data.gov.ua` CSV/Excel datasets, not the SDMX API.
**Blockers:** **No census since 2001** — every "stock" distribution (civil status, birth country, household composition, education attainment) is extrapolated and stale. Wartime data: Crimea excluded since 2014, Donetsk/Luhansk/Zaporizhzhia/Kherson partly excluded since 2022; ~7M refugees abroad uncounted. English coverage of dataflow/codelist labels patchy. SDMX heavier than PxWeb. **No tenure, parental-structure, or birth-country dataflows at all.**
**Feasibility verdict:** **LOW** — The SDMX API is well-formed, but ~6 of 16 dimensions are missing outright and another 6 rely on a 25-year-old census plus war-disrupted estimates, so it cannot stand in for SCB without major substitution.

### Pan-European fallback (batch 2)

#### Eurostat (pan-EU)
**API name & URL:** Eurostat Dissemination API. Two co-existing endpoints — SDMX 2.1 REST: `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{dataset}` and Statistics (JSON-stat 2.0): `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}`.
**Technology stack:** REST/HTTP GET. Two formats: SDMX 2.1 ML/JSON (full structural metadata) and JSON-stat 2.0 (lightweight). CSV/TSV bulk download facility also available. Asynchronous endpoint for large extracts.
**Auth/limits:** No registration, no API key, no per-minute rate limit published. Hard limits: max 50 categories per dimension request; 500k–5M cells routed asynchronously; >5M cells rejected (HTTP 400); URL length cap also triggers 400.
**Coverage:** 16/16 (13 ✓, 3 partial) **across all EU/EEA states from one harmonised endpoint**. Datasets: `demo_pjan` (national 1-yr ages), `demo_r_d2jan` (NUTS-2), `demo_r_pjangrp3` (NUTS-3, 5-yr bands only), `edat_lfs_9918`/`edat_lfse_04` (ISCED, NUTS-2), `lfsa_*` LFS NUTS-2 (NUTS-3 voluntary only), `lfst_r_lfe2en2` (NACE × NUTS-2), `lfsi_pt_a`/`lfsa_etgan` (perm/temp/self-emp), `lfsa_ewhuis`/`lfsa_ewhan2` (hours), `ilc_di01`/`ilc_di03` (income deciles, national + partial NUTS-2), `ilc_lvho02` (tenure × household type), `lfst_hhnhtych`/`ilc_lvph01` (households), `migr_pop3ctb`/`lfst_r_lfsd2pwn` (birth group), `lfst_hhnhwhtc` (parental), `urb_*` (DEGURBA 3-class). Partial: civil status (`demo_pjanmarsta` national-only, no NUTS), bilateral country-of-birth detail (some MS suppress, T+2 lag).
**Classifications:** NUTS 2024, ISCED 2011, NACE Rev. 2, ISCO-08, DEGURBA, SDMX code lists. Country codes ISO-3166-1 alpha-2 (with `EU27_2020`, `EA20` aggregates).
**Example query:** Sweden age × sex 2024 (JSON-stat): `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?format=JSON&lang=EN&geo=SE&time=2024&sex=M&sex=F`
**Python wrappers:** `eurostat` (PyPI, JSON-stat + bulk TSV, well-maintained), `pandasdmx`/`sdmx1` (Eurostat configured as built-in source `ESTAT`), `eurostatapiclient` (REST → pandas), `pyjstat`, `pyrostat` (official Eurostat repo), `pyeurostat`. The `eurostat` package is the most production-ready.
**Blockers:** NUTS-3 only ~5-yr age bands, no 1-yr granularity below national; bilateral country-of-birth incomplete (several MS don't transmit, T+2 lag); demographic data published T+14 months vs national NSIs T+3 months; civil status not regionalised; cell suppression on small populations; LFS variables harmonised to EU concepts may diverge from national NSI definitions; household/SILC samples can be too small for fine cross-tabs.
**Feasibility verdict:** **HIGH** — Eurostat covers 13/16 dimensions fully and 3 partially across all EU/EEA states from one harmonised endpoint, making it the strongest universal fallback when national NSI APIs are unavailable, accepting NUTS-2 (not NUTS-3 1-year) granularity and a longer publication lag.

### Oceania (batch 2)

#### New Zealand
**API name & URL:** Aotearoa Data Explorer (ADE), Stats NZ / Tatauranga Aotearoa. Browse UI: `https://explore.data.stats.govt.nz`. SDMX REST base: `https://api.data.stats.govt.nz/rest/`. **Replaced NZ.Stat in September 2024.**
**Technology stack:** **SDMX 2.1 RESTful** (.Stat Suite framework, same OECD-built platform as OECD/UNESCO). Response formats: SDMX-JSON, SDMX-ML, CSV (with labels). Path: `/rest/data/{agency},{flow},{version}/{key}?dimensionAtObservation=AllDimensions&format=...`. Different protocol from SCB.
**Auth/limits:** Free but **registration required** at `portal.apis.stats.govt.nz`; subscribe to "Aotearoa Data Explorer" product to get a key. Pass header `Ocp-Apim-Subscription-Key: <key>`. Specific quotas not published. Stricter than SCB (which is fully anonymous).
**Coverage:** 16/16 (13 ✓, 3 partial). 2023 Census tables (single-year age × sex), Census 2023 highest qualification (NZSCED-aligned), HLFS quarterly + Census, ANZSIC06 (industry), HLFS hours-worked bands, Census income bands + HES, 22 new 2023 Census housing topic tables, Census household composition, Census legal partnership status, Regional Council & Territorial Authority, Census birthplace by broad region + country detail, 31 Census family/household topic tables, Statistical Area / Urban Rural classification. Partial: employment type (status-in-employment less granular than SCB), income decile components (less itemised), annual cadence (HLFS quarterly back to 1998; **Census every 5 yrs — last 2023, 2028 cancelled, annual admin-data census from 2030**).
**Classifications:** ANZSIC06, ANZSCO, NZSCED, Statistical Area 1/2 + Urban Rural 2023, Territorial Authority/Regional Council, modified-OECD equivalised income.
**Example query:** `GET https://api.data.stats.govt.nz/rest/data/STATSNZ,CEN23_POP_001,1.0/all?dimensionAtObservation=AllDimensions&format=csvfilewithlabels` with header `Ocp-Apim-Subscription-Key: <key>`. Dataflow IDs follow `CEN23_*`/`HLF_*` pattern.
**Python wrappers:** `statsnz` on PyPI (low-maintenance, wraps older REST product APIs). For ADE, the recommended path is generic SDMX clients — `sdmx1` (formerly pandasdmx) and `pysdmx` work against any SDMX 2.1 endpoint; ADE not yet a built-in source but a custom `Source` is trivial.
**Blockers:** **API key + subscription gate** (vs SCB anonymous); **Māori/iwi data sovereignty** under the Mana Ōrite agreement — some iwi-level cuts are restricted/suppressed; full microdata only via IDI with Stats NZ approval. Traditional 5-yearly census ending — 2023 final classical census, 2028 cancelled, transition to admin-data + annual surveys from 2030 introduces methodology discontinuity. SDMX-JSON shape differs from JSON-STAT v2 → SCB parsing code must be rewritten. Per-flow dataflow IDs must be discovered via `/rest/dataflow/STATSNZ`.
**Feasibility verdict:** **HIGH** — All 16 dimensions covered by 2023 Census + HLFS through a single, well-documented SDMX 2.1 REST endpoint; the only real costs are an API-key subscription, a JSON-STAT-to-SDMX-JSON parser swap, and respecting Māori data sovereignty suppressions.

### Asia — East & Southeast (batch 3)

#### China
**API name & URL:** National Bureau of Statistics (NBS) "National Data" / EasyQuery — `https://data.stats.gov.cn/english/easyquery.htm` (English mirror) and `data.stats.gov.cn/easyquery.htm` (Chinese).
**Technology stack:** Undocumented JSON-over-HTTP. Single endpoint, GET requests with method param `m=QueryData`, dimension filters via JSON-encoded `wds`/`dfwds` arrays, plus `dbcode` (e.g. `hgnd` annual national, `fsnd` regional, `hgjd` quarterly), `rowcode`, `colcode`, and a `k1` cache-buster timestamp. Returns proprietary JSON (not JSON-stat, not SDMX, not PxWeb). No official OpenAPI spec exists — all known clients are reverse-engineered.
**Auth/limits:** No auth, no API key, no published rate limit. However the server returns 403/timeouts for many foreign IPs and applies aggressive anti-scraping (cookies, referer checks). No SLA.
**Coverage:** 5 ✓, 6 partial, 5 ✗. Age × sex = 5-yr bands (1-yr only in tabulation volumes); industry = GB/T 4754-2017 (≈ ISIC); urbanization = urban/town/rural; region = 31 provinces; annual time series ✓ since 1978. Working hours, income deciles (only quintiles), birth country detail, full housing tenure, parental structure largely absent from API.
**Classifications:** GB/T 4754-2017 (industry, ISIC-mappable); GB/T 6565-2015 (occupation); local 6-tier education scheme (not ISCED); GB/T 2260 region codes; hukou-based migration (no DEGURBA).
**Example query:** `GET https://data.stats.gov.cn/english/easyquery.htm?m=QueryData&dbcode=hgnd&rowcode=zb&colcode=sj&wds=[]&dfwds=[{"wdcode":"zb","valuecode":"A0301"}]&k1=1715300000000`. Joint 1-yr age × sex requires `dbcode=rkpc` census sub-DB which is not consistently exposed.
**Python wrappers:** `nbsc` (mbk-dev/nbsc, narrow CPI/GDP-only); `khaeru/data` cn_nbs.py reference scraper; R package `pedquant::ed_nbs`. No mature, maintained PyPI client.
**Blockers:** Endpoint unofficial and partially geo-blocked from foreign IPs ("reverse Great Firewall"); reverse-engineered JSON not JSON-stat/SDMX so per-dimension hand-rolled ETL; Chinese-only `valuecode` metadata; only quintiles (no deciles); census micro-cuts in yearbook tables not API; no shipped ISCED/DEGURBA crosswalk.
**Feasibility verdict:** **LOW** — unofficial geo-blocked endpoint, no JSON-stat/PxWeb semantics, and several SCB dimensions (working hours, deciles, birth-country detail, joint age×sex×edu) not retrievable via API at all.

#### Indonesia
**API name & URL:** BPS WebAPI (Badan Pusat Statistik) — developer portal `https://webapi.bps.go.id/developer/`, base `https://webapi.bps.go.id/v1/api/`, docs `https://webapi.bps.go.id/documentation/`.
**Technology stack:** REST + JSON (proprietary BPS schema, NOT JSON-stat or SDMX). GET with `model=` switches (`subject`, `var`, `vervar`, `th`, `turvar`, `data`). Three data classes: dynamic tables, static tables, census/SIMDASI interoperability endpoints. No PxWeb compatibility.
**Auth/limits:** Free registration required at `webapi.bps.go.id`; mandatory `key=<APP_ID>` query parameter on every call. No published rate-limit numbers but key is per-application.
**Coverage:** 12 ✓, 3 partial, 0 ✗. SP2020 + SAKERNAS + SUSENAS supply age × sex (5-yr), education, employment status, KBLI 2020 industry, status pekerjaan utama, working hours, expenditure deciles, housing tenure, household size, marital status, 38 provinces / ~514 regencies, internal migration. Income deciles, birth-country detail, parental structure thin.
**Classifications:** KBLI 2020 (ISIC Rev.4-aligned, 21 sections); KBJI for occupations (ISCO-08-aligned); Indonesian education levels SD/SMP/SMA/Diploma/S1-S3 (ISCED-mappable); BPS region codes.
**Example query:** `GET https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/<VAR_ID>/th/<YEAR_ID>/key/<APP_ID>` — first discover the var id via `GET /v1/api/list/model/var/domain/0000/key/<APP_ID>` (filter subject "Kependudukan").
**Python wrappers:** `stadata` (official, `pip install stadata`); `bpsr` (R, dzulfiqarfr); community Postman collection `bps-pinrang/Web-API-BPS-Postman-Collection`.
**Blockers:** API key registration required; non-standard JSON schema needs custom parser (no JSON-stat reuse); multi-step ID lookup chain (subject→var→vervar→turvar→th); Bahasa-dominant labels with inconsistent `lang=eng`; joint distributions split across multiple tables; no published rate limits (opaque throttling risk).
**Feasibility verdict:** **MEDIUM** — all 16 dimensions obtainable from BPS surveys and the WebAPI is free/JSON-based, but bespoke schema, mandatory key, language inconsistencies, and multi-step ID discovery require a fully custom client (cannot reuse `SCBPxWebClient`/`SSBPxWebClient`).

#### Vietnam
**API name & URL:** GSO/NSO PxWeb — `https://pxweb.gso.gov.vn/pxweb/api/v1/en/` (English) and `/vi/`. Browse UI at `https://pxweb.gso.gov.vn/pxweb/en/`. SDMX endpoint exists but reportedly unstable. Aggregate dashboard at `https://dashboard.gso.gov.vn/`.
**Technology stack:** PxWeb (older version) — same protocol family as SCB. POST queries return JSON, JSON-stat, JSON-stat2, CSV, XLSX, or PX. URL pattern `…/api/v1/{lang}/{database}/{path}/{TABLE}.px`.
**Auth/limits:** No authentication, no registration, public/open. No published rate limits, but third-party monitors report intermittent outages and SDMX endpoint described as "unstable".
**Coverage:** 9 ✓, 6 partial, 1 ✗. Age × sex (5-yr dominant), education, employment status, VSIC 2018 industry (NACE-aligned), household size, civil status (e.g. `E02.29.px` SMAM), 63 provinces, urban/rural, annual series 2009+. Birth country detail ✗; working hours, income deciles, housing tenure, parental structure, employment type partial.
**Classifications:** VSIC 2018 (NACE Rev. 2-aligned); ISCED-mappable education; ISCO-08-aligned occupation; 63-province admin codes.
**Example query:** `POST https://pxweb.gso.gov.vn/pxweb/api/v1/en/Population%20and%20Employment/Population%20and%20Employment/E02.03-07.px` body `{"query":[{"code":"Sex","selection":{"filter":"item","values":["Male","Female"]}},{"code":"Age group","selection":{"filter":"all","values":["*"]}},{"code":"Year","selection":{"filter":"item","values":["2023"]}}],"response":{"format":"json-stat2"}}`.
**Python wrappers:** No GSO-specific SDK. Generic PxWeb tools: `pyaxis`, `pxweb`/`pxwebpy`, `pandasdmx` (for SDMX). R: `rOpenGov/pxweb`, `epix-project/gso`. Existing repo `SCBPxWebClient` structurally reusable.
**Blockers:** Older PxWeb version with inconsistent `?format=json` metadata; intermittent uptime / SDMX outages; URL-encoded Vietnamese in some branches; microdata gated; deeper cross-tabs pre-aggregated, limiting conditional sampling chains; English coverage lags Vietnamese.
**Feasibility verdict:** **MEDIUM** — PxWeb compatibility makes the SCB client largely reusable and core dimensions are well covered, but uptime concerns, sparser cross-tabs (income/tenure/parental structure), and gated microdata yield thinner conditional richness than SCB.

#### Philippines
**API name & URL:** PSA OpenSTAT PxWeb API — `https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/` (browser UI at `https://openstat.psa.gov.ph/`). Separate token-gated Statistical Classification Systems API at `https://psa.gov.ph/classifications-api`.
**Technology stack:** PxWeb v1 (PC-Axis backend, identical protocol family to SCB/SSB/Stat-Fi). GET for metadata; POST a JSON `{query, response:{format}}` body to a `.px` endpoint; supports `px`, `csv`, `xlsx`, `json`, `json-stat`, `json-stat2`. JSON-STAT2 = full structural parity with SCB pipeline.
**Auth/limits:** No authentication, no registration, no API key. Standard PxWeb cell limits (~100 k cells/query, 10 queries/10 s) apply implicitly.
**Coverage:** 11 ✓, 4 partial, 1 ✗. LFS Key Employment Indicators, PSCED-2017 education, PSIC-2009 industry, FIES income deciles, 2020 CPH housing tenure, household size, 135-value geographic dim, urban via HUC flag, LFS quarterly Apr 2005 – Mar 2026. Age × sex 5-yr (single-year only via projections); civil status, migration partial; birth-country detail ✗; parental structure not as cross-tab in OpenSTAT.
**Classifications:** PSCED-2017 (≈ ISCED), PSIC-2009 (NACE Rev. 2 / ISIC Rev. 4), PSOC-2012 (≈ ISCO-08), PSGC for geography. All have published cross-walks.
**Example query:** `POST https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/1A/PO/0021A6DPAG0.px` body `{"query":[{"code":"Geographic Location","selection":{"filter":"item","values":["PHILIPPINES"]}},{"code":"Sex","selection":{"filter":"item","values":["Male","Female"]}},{"code":"Age Group","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`.
**Python wrappers:** `pyaxis` (PC-Axis to pandas), `pxwebpy` (generic PxWeb client), `pxweb` R package. Existing `SCBPxWebClient` / `SSBPxWebClient` pattern transfers almost verbatim.
**Blockers:** Age × sex granularity 5-year in 2020 CPH; civil status / birth-country / parental structure not as discrete OpenSTAT `.px` cross-tabs (CPH publications/PSADA microdata only); some `.px` paths return 404 even when UI shows folder (case-sensitive IDs, `rxid` cookies); variable codes contain spaces; no SDMX/GraphQL/bulk dump.
**Feasibility verdict:** **HIGH** — OpenSTAT is a stock PxWeb v1 server with JSON-STAT2 output and no auth, so existing `SCBPxWebClient`/`SSBFetchService` architecture ports directly; only real losses vs SCB are single-year age and a few niche cross-tabs.

#### Thailand
**API name & URL:** No PxWeb-equivalent at NSO. Closest: NSO Data Catalog `https://catalog.nso.go.th/` (CKAN-style, ~889 datasets); Open Government Data `https://data.go.th/` and `https://opend.data.go.th/opend-search/{dataset_id}/query`; static reports `http://statbbi.nso.go.th/`; NSO Interactive Dashboard `https://ittdashboard.nso.go.th/`.
**Technology stack:** CKAN REST API + JSON metadata + CSV/XLSX/JSON file resources; Open-D query API returning JSON rows. No JSON-stat, PC-Axis, SDMX. statbbi tables are ASPX-rendered HTML/PDF/CSV.
**Auth/limits:** data.go.th requires registration + API key in HTTP header. NSO Data Catalog/statbbi unauthenticated. No published rate limits.
**Coverage:** 1 ✓ (region 77 provinces), 13 partial, 2 weak. All other dimensions exist in static CSV/PDF reports (LFS, SES, Census, Migration Survey) but are not as a queryable cube.
**Classifications:** TSIC-2009 (ISIC Rev.4 aligned, 21 sections); Thai MOE levels mappable to ISCED 2011. ISIC→NACE crosswalks exist.
**Example query:** No PxWeb-style query exists. CKAN equivalent: `GET https://opend.data.go.th/opend-search/{dataset_id}/query?dsname={dataset_id}&path={dataset_id}&loadAll=1&type=json&limit=100&offset=0` with header `api-key: <token>`.
**Python wrappers:** None for NSO Thailand. Generic `pxweb` (ropengov) does not work — no PxWeb endpoint. `ckanapi` PyPI for CKAN access.
**Blockers:** No PxWeb / JSON-stat — entire SCB client architecture would need replacement with per-dataset CSV ingestion; heavy reliance on Statistical Yearbook PDFs; Thai-language metadata dominant; statbbi flaky / unreachable; API-key registration on data.go.th; Census 2020 disrupted by COVID; conditional joint distributions only in LFS microdata at IHSN/ILO catalogs.
**Feasibility verdict:** **LOW** — Thailand publishes the underlying data but lacks a queryable multi-dimensional statistics API; substituting SCB would require a custom CSV/PDF ingestion layer plus likely LFS microdata licensing.

#### Malaysia
**API name & URL:** OpenDOSM / data.gov.my Open API — `https://api.data.gov.my/opendosm` and `https://api.data.gov.my/data-catalogue`. Catalogue UI: `https://open.dosm.gov.my/data-catalogue`. Parquet bulk: `https://storage.dosm.gov.my/<group>/<id>.parquet`.
**Technology stack:** REST + plain JSON (NOT JSON-stat, NOT PxWeb). Each dataset is a tabular resource selected by `id=` plus column filters (`limit`, `date_start`, `date_end`, equality filters). Bulk Parquet snapshots are the recommended path for large pulls.
**Auth/limits:** No registration, no API key, CC BY 4.0. **Hard limit: 4 requests/minute per endpoint, returns HTTP 429** — headline blocker forcing Parquet-first design.
**Coverage:** 5 ✓, 6 partial, 5 ✗. LFS month/qtr/annual, MSIC sector employment, status-in-employment, HIES percentile (100 percentiles), state/district/parliamentary/DUN granularity, population back to 1970. Tenure, birth location/country, parental structure, urbanization, fine education attainment ✗; age × sex 5-yr only.
**Classifications:** MSIC 2008 v1.0 (= ISIC Rev. 4) for industry; LFS follows ILO; no published ISCED crosswalk on the API; ethnicity uses local categories.
**Example query:** `GET https://api.data.gov.my/data-catalogue?id=population_malaysia&date=2024-01-01&ethnicity=overall&limit=50`. Bulk: `pd.read_parquet("https://storage.dosm.gov.my/population/population_malaysia.parquet")`.
**Python wrappers:** No mature dedicated wrapper. Idiomatic usage = `requests` against JSON endpoint or `pandas.read_parquet` against `storage.dosm.gov.my`.
**Blockers:** 4 req/min ceiling forces Parquet-first design (breaks SCB pattern of many small POSTs); 7/16 dimensions absent from open API (only Census 2020 PDFs / gated microdata); no JSON-stat means the SCB parser cannot be reused; age in 5-year bands.
**Feasibility verdict:** **MEDIUM** — core demographics, LFS, MSIC, HIES deciles cleanly available via REST/Parquet, but ~7/16 dimensions missing from open API and 4-req/min plus non-JSON-stat schema mean a Malaysia client must be rewritten around Parquet snapshots.

#### Singapore
**API name & URL:** SingStat Table Builder API — base `https://tablebuilder.singstat.gov.sg/api/table/`. Companion portal `data.gov.sg` (~2,200 tables from 70 agencies, CSV/JSON downloads).
**Technology stack:** REST over HTTPS, GET, returns proprietary JSON (not JSON-stat, not PxWeb): `{Data:{id, title, row:[{seriesNo, rowText, uoM, columns:[{key,value}]}]}}`. Flat row/column model, very different from SCB JSON-STAT v2.
**Auth/limits:** No registration, no API key. Public throttle (form `form.gov.sg/6902ced6ce3eea899bff13d6` to request higher limits). Specific quota numbers not documented.
**Coverage:** 12 ✓, 2 partial, 1 N/A (urbanization — Singapore is 100% urban; drop the field). M810011 age × sex (5-yr in time series, 1-yr via Census M-tables), M810791 resident/non-resident, LFS hours, "Key Household Income Trends" deciles, dwelling type by HDB room count, household structure, marital status, planning area, annual since 1957.
**Classifications:** SSIC 2020 (ISIC-derived), SSOC 2020 (ISCO-derived), ISCED-equivalent education bands. All mappable.
**Example query:** `GET https://tablebuilder.singstat.gov.sg/api/table/tabledata/M810011`. Optional params `seriesNoORrowNo`, `timeFilter`, `offset`, `limit`.
**Python wrappers:** `singstat` on PyPI (yuhui/singstat, GPLv3, low maintenance) — Client class with one method per endpoint. Also `xkexuan/singstat-tables`. A thin `requests`-based client is straightforward.
**Blockers:** Proprietary row/column JSON, not JSON-stat (parser rewrite); no public rate-limit numbers; many cross-tabs only as static Census M-tables (not freely re-pivotable like PxWeb cube queries); fine joint distributions require composing multiple M-tables; urbanization meaningless and must be dropped.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions exist (with #15 dropped as inherent), but proprietary row/column JSON, rigid pre-aggregated M-tables (vs PxWeb's free cube slicing), and need to compose distributions across fixed tables make this a substantive port rather than a drop-in client swap.

#### Taiwan
**API name & URL:** DGBAS Macro Statistics Database (`nstatdb.dgbas.gov.tw`) and PxWeb-2007 PC-Axis portal (`statdb.dgbas.gov.tw/pxweb/`). Bulk XML at `https://nstatdb.dgbas.gov.tw/dgbasAll/download/XML/{TableId}.xml` with master index `MacroDatabase.csv`. Open-data front door at `data.gov.tw` and `eng.stat.gov.tw`.
**Technology stack:** NOT JSON-stat / PxWeb-v1/v2 REST. Custom XML bulk-download (one URL per table) plus an ASP-based PxWeb 2007 portal serving PC-Axis (.px), CSV, XLS via `varval.asp` / `Quickview.asp`. `data.gov.tw` is CKAN-style; per-agency download URLs.
**Auth/limits:** No registration, no API key, no documented rate limit. OGDL-Taiwan-1.0.
**Coverage:** 9 ✓, 4 partial, 2 ✗. `Po0206A1A.xml` age × sex (joint, 1-yr), education attainment LFP series, Manpower Survey LM0101A1A LFP, LM6101A1A industry (ROC SIC), monthly hours-worked, FIES decile cut-offs, marriage/divorce, 22 cities/counties, most series from 1980s. Housing tenure, household size, birth-loc, urbanization partial; birth country detail and parental structure ✗.
**Classifications:** ROC SIC (≈ ISIC, not NACE — concordance needed); ROC SOC (≈ ISCO-08); MOE education levels broadly map to ISCED 0-8; civil status follows UN standard.
**Example query:** `GET https://nstatdb.dgbas.gov.tw/dgbasAll/download/XML/Po0206A1A.xml` (no params, full series). Single-age JSON alternative: `GET https://pop-proj.ndc.gov.tw/Common/Custom/Custom_GetOpenDatas.ashx/464/?sYear=2024&eYear=2024`.
**Python wrappers:** None mature. `g0v/twstat` (Node-based crawler scraping the PxWeb-2007 .px files); no PyPI equivalent to `pxweb`/`pyjstat` for DGBAS.
**Blockers:** No standard JSON-stat / PxWeb v1+ REST — must parse custom XML or PC-Axis; English coverage uneven (Chinese-only labels in many XML); census housing/parental/birth-country in PDF/XLSX only; ROC-SIC↔ISIC bridge needed; PxWeb 2007 portal occasional 5xx.
**Feasibility verdict:** **MEDIUM** — core demographic dimensions reachable via stable bulk XML/JSON URLs, but substituting SCB requires a new XML/PC-Axis parser, ROC-SIC mapping, and PDF scraping for housing/parental fields, since DGBAS does not speak the PxWeb v1/v2 REST protocol.

### Asia — South & West (batch 3)

#### Pakistan
**API name & URL:** No official PBS API. Channels: `https://www.pbs.gov.pk/` (PDF/Excel reports), `https://census23.pbos.gov.pk/` (interactive dashboard, UI-only), `https://www.pbs.gov.pk/digital-census/detailed-results`, third-party `https://opendata.com.pk/` (CKAN-style portal with some PBS datasets, no documented programmatic API).
**Technology stack:** No PxWeb, no JSON-stat, no SDMX, no documented REST/GraphQL endpoint. Distribution is PDF + Excel/CSV + Stata `.dta` microdata bundles. Census23 dashboard is a JS SPA with no advertised JSON endpoints. Microdata via formal Data Request + treasury fee.
**Auth/limits:** No API auth (no API). Microdata gated by institutional Data Request form + treasury fee. No rate limit (no API).
**Coverage:** 4 ✓, 8 partial, 4 ✗. LFS 2024-25, Census 2023 housing tenure, household size avg 6.33, marital status by age 15+, 36 provinces + districts, urban/rural 38.82/61.18 (2023). Age × sex 5-yr only; income deciles only in microdata; birth country detail and parental structure ✗.
**Classifications:** PSIC Rev. 4 (= ISIC Rev. 4 to 4-digit). Education uses local Pakistani grade-level scheme — not ISCED-coded; ISCED mapping must be done manually. PSCO (≈ ISCO-08).
**Example query:** None possible — no API. Closest equivalent: download `https://www.pbs.gov.pk/sites/default/files/population/2023/Pakistan.pdf` or Excel from `census23.pbos.gov.pk` (manual click-through; no documented JSON endpoint).
**Python wrappers:** None for PBS. CRAN `PakPC2023` (R-only, static, district-level Census 2023). World Bank `gld` repo for LFS Stata harmonisation. No `pip install`-able PBS client.
**Blockers:** No API of any kind — substitution of SCB's live PxWeb POST queries is impossible without scraping PDFs or pre-loading Stata microdata; microdata gated by paper Data Request + fee; classification mismatch on education (no ISCED); Census23 dashboard XHR endpoints undocumented/unstable; many tables only as scanned PDFs (OCR needed).
**Feasibility verdict:** **LOW** — PBS publishes rich underlying data but offers zero programmatic API; substituting SCB would require ingesting PDFs, Excel workbooks, and Stata microdata, violating the project's "no static data substitution" rule.

#### Bangladesh
**API name & URL:** BBS Central Microdata Catalog — `http://data.bbs.gov.bd/index.php/home` (NADA platform). Companions: `nsds.bbs.gov.bd` (browsable reports) and `data.gov.bd` (mixed-publisher Open Data Portal). No PxWeb/JSON-stat dissemination service exists.
**Technology stack:** NADA (IHSN cataloging system, Laravel/PHP). REST API returns JSON; primary purpose is metadata + microdata distribution (DDI CodeBook 2.5). Newer `/tables` endpoint exposes statistical tables as CSV/JSON. No PxWeb, SDMX, JSON-stat. Most aggregates are PDF + Excel on `bbs.gov.bd`. HDX hosts Census 2022 Excel (Admin-02 / district level).
**Auth/limits:** Browsing/metadata anonymous. Microdata downloads require free researcher account + license-application step (manual approval, 1–7 days). Server HTTP-only and intermittently unreachable (ECONNREFUSED during research).
**Coverage:** 0 ✓, 11 partial, 5 weak. PHC 2022 + LFS 2022 + HIES 2022 cover all dimensions in PDF/Excel form, but as queryable cubes virtually nothing.
**Classifications:** BSIC 2020 (mapped to ISIC Rev.4), COICOP for HIES 2022, ISCED-equivalent education levels reported but no published crosswalks via API.
**Example query:** No PxWeb-style query exists. NADA-style metadata fetch: `GET http://data.bbs.gov.bd/index.php/api/catalog/search?format=json` returns dataset list. Aggregate retrieval requires manual download of Census 2022 Excel from HDX.
**Python wrappers:** `pynada` (PyPI) and `nadar` (R) — IHSN-maintained NADA clients; built for catalog admin / metadata, not bulk aggregate retrieval. No country-specific BBS wrapper.
**Blockers:** No PxWeb/JSON-stat/SDMX endpoint — full SCB substitute does not exist; most aggregate distributions live in PDF reports (PDF/Excel scraping required); microdata gated behind manual license approval; server availability unreliable; Census 2022 only released to Admin-02 (no 1-yr ages, no fine geography); Bangla-only on many BBS pages.
**Feasibility verdict:** **LOW** — no PxWeb-equivalent live-query API; substituting SCB would require building a PDF/Excel ETL plus manual microdata licensing, breaking the project's "live API, no static data" constraint.

#### Iran
**API name & URL:** Statistical Centre of Iran (SCI / Markaz-e Amar-e Iran), `https://www.amar.org.ir/english`. No public, documented programmatic API — only HTML/PDF/XLSX portal. Third-party: Iran Open Data (`iranopendata.org`), Iran Data Portal — Syracuse (`irandataportal.syr.edu`), GitHub `Iran-Open-Data/HBSIR` (Python loader for HEIS microdata).
**Technology stack:** SCI publishes static files (PDF, XLSX, CSV, MS Access `.mdb`) on a CMS site. No PxWeb, JSON-stat, SDMX, REST. Iran Open Data is a dataset catalogue with CSV downloads (no public REST API).
**Auth/limits:** SCI site unauthenticated but uses CAPTCHA and is intermittently geo-blocked / unreachable from outside Iran (WebFetch confirmed `ECONNREFUSED` and 403). Iran Open Data: free tier 25 dataset views/month + 1 CSV download/month — hard limit.
**Coverage:** 4 ✓, 8 partial, 4 ✗. LFS 2017–2024 microdata (ILO), Census 2016 housing/marital/region/urbanization. Age × sex 5-yr only; education / employment status / industry / type / hours / income deciles partial; birth country detail and parental structure ✗.
**Classifications:** ISIC Rev.4 (industry, via LFS); ISCO-08 partial; national education levels loosely mappable to ISCED; 31 provinces + shahrestans. SCI uses ISIC directly.
**Example query:** No PxWeb-style query. Closest: download fixed XLSX, e.g. `https://www.amar.org.ir/Portals/0/Files/abstract/1395/sarshomari95_n_koll.xlsx` (Census 1395/2016). Programmatic age × sex requires HTTP GET + pandas `read_excel` per province.
**Python wrappers:** `HBSIR` (`pip install hbsir`, by Iran-Open-Data) — HEIS microdata loader; `IRHEIS` (IPRCIRI, R/Stata-style scripts); `jalilian/iran2016census` GitHub. No SCI-official SDK.
**Blockers:** No machine-readable API at all; Persian-only labels for many tables; geo-blocking from non-Iranian IPs intermittent and confirmed; US sanctions chill third-party tooling; microdata (LFS, HEIS) requires registration via ILO/IHSN.
**Feasibility verdict:** **LOW** — absence of any structured API (PxWeb/JSON-stat/SDMX), pervasive XLSX/PDF-only delivery, geo-blocking, Persian-only metadata make Iran a poor drop-in substitute; a working pipeline would require static-file scraping plus manual schema curation rather than live conditional-distribution fetches.

#### UAE
**API name & URL:** UAE.Stat (FCSC). SDMX-REST endpoint `https://uaestat.fcsc.gov.ae/rest/` (release mirror `https://releaseeuaestat.fcsc.gov.ae/rest/`). Secondary CKAN portal `https://opendata.fcsc.gov.ae/`. Emirate-level: SCAD (`scad.gov.ae`, separate Abu Dhabi Census `census.scad.gov.ae`) and DSC via Dubai Pulse (`dubaipulse.gov.ae`, OAuth-secured CKAN).
**Technology stack:** Federal layer is `.Stat Suite` (SIS-CC) exposing **SDMX 2.1 REST** (XML, SDMX-JSON, CSV, CSV-with-labels). Opendata portal is **CKAN 2.9.5** (Datopian build). DSC adds OpenDataSoft-style Dubai Pulse CKAN. **No PxWeb / no JSON-stat v2** anywhere.
**Auth/limits:** UAE.Stat SDMX REST is open. CKAN at `opendata.fcsc.gov.ae` open read. **Dubai Pulse requires OAuth2** client_credentials (per-dataset key + secret; ~30-min tokens). No published rate limits for FCSC.
**Coverage:** 7 ✓, 5 partial, 4 ✗. LFS resumed 2016, annual `DF_LFOUT_*`; 7 emirates; ISCED education; ISIC industry; HIES 2024 (19k HH); marital status. Age × sex usually 5-yr; nationality split dropped post-2020; income deciles only as bands; urbanization, parental structure, birth-country detail ✗.
**Classifications:** ISCO-08, ISIC Rev.4, ISCED. No NACE.
**Example query:** `GET https://releaseeuaestat.fcsc.gov.ae/rest/data/FCSA,DF_LFOUT_AGE,2.0.0/all?dimensionAtObservation=AllDimensions&format=csvfilewithlabels`. Structure via `GET /rest/dataflow/FCSA/DF_LFOUT_AGE/2.0.0?references=all`.
**Python wrappers:** No FCSC-specific package. `pandaSDMX` / `sdmx1` work — must register UAE.Stat as a custom source (URL + agency `FCSA`). CKAN side: `ckanapi`. Dubai Pulse: hand-rolled OAuth2.
**Blockers:** SDMX 2.1 ≠ PxWeb — non-trivial rewrite of the SCB client; age in 5-yr bands; nationality split dropped post-2020 hurts the Emirati/expat dimension that is the defining UAE feature; household-level data fragmented across federal LFS/HIES + emirate censuses (SCAD, DSC) with non-aligned codelists; DSC OAuth friction; bilingual Arabic/English labels.
**Feasibility verdict:** **MEDIUM** — SDMX-REST endpoint is real, open, and covers ~10/16 dimensions cleanly, but switching from PxWeb to SDMX 2.1 plus losing 1-yr ages, post-2020 nationality, urban/rural, and income deciles forces meaningful schema changes and reduces fidelity vs. SCB.

### Africa (batch 3)

#### Nigeria
**API name & URL:** No first-party API at NBS. Closest options: (a) Knoema-powered Nigeria Data Portal `https://nigeria.opendataforafrica.org/` (NBS-mirrored at `https://nso-nigeria.opendataforafrica.org/`) with API explorer at `https://opendataforafrica.org/dev/explorer`; (b) World Bank Microdata Library for survey-level access. NBS itself (`nigerianstat.gov.ng`) and microdata portal (`microdata.nigerianstat.gov.ng`) publish PDF/XLS reports + NADA — no PxWeb, no JSON-stat.
**Technology stack:** Knoema atlas exposes REST + JSON, optional SDMX, Excel, Python, R, C# wrappers. NBS microdata uses NADA (CSV/SPSS/Stata bulk download, not query API). No PxWeb deployment.
**Auth/limits:** Knoema: anonymous browse OK; programmatic access requires `app_id`/`app_secret` (free signup); rate limits scale with auth tier (undocumented hard caps). NBS microdata: registration + access request per dataset.
**Coverage:** 3 ✓, 9 partial, 4 ✗. NLFS quarterly since Q1 2023 (ILO methodology), 36 states + FCT, urban/rural standard. Age × sex from 2006 census + projections; income/decile in NLSS microdata only; birth-location and birth-country ✗; 2023 census postponed indefinitely.
**Classifications:** Education roughly ISCED-aligned in NLSS/NLFS; employment per ILO 19th ICLS (2023 revision); industry uses ISIC Rev. 4 (no domestic NSIC standard); 36 states + FCT, 774 LGAs.
**Example query:** Knoema atlas — `GET https://knoema.com/api/1.0/data/raw?dataset=<id>&country=NG&dimensions=...&Token=<app_secret>`. No SCB-style PxWeb POST exists.
**Python wrappers:** `knoema` (PyPI, official Knoema driver — `knoema.get(dataset_id, country='Nigeria', ...)`); `pandas-datareader` via World Bank WDI for aggregates; `sdmx1` against UN/WB mirrors but not NBS direct. No NBS-specific package.
**Blockers:** NBS publishes no machine-readable query API; 2006 census is last full census, with 2023 postponed indefinitely (age × sex are projections); microdata requires per-dataset registration; Knoema mirror is third-party and may lag NBS releases; no urbanization or housing aggregates in queryable form.
**Feasibility verdict:** **LOW** — no first-party query API, the third-party Knoema fallback requires auth and offers thinner coverage, and the demographic baseline rests on a 20-year-old census; from-scratch microdata-tabulation pipeline required.

#### Kenya
**API name & URL:** No native KNBS REST/PxWeb API. Closest: (1) Kenya Data Portal (Knoema) `https://kenya.opendataforafrica.org/` + NSO mirror `https://nso-kenya.opendataforafrica.org/`; (2) KeNADA microdata catalog `https://statistics.knbs.or.ke/nada/`; (3) `https://www.opendata.go.ke/` (ArcGIS Hub, geospatial-focused); (4) bulk Excel/PDF on `knbs.or.ke`.
**Technology stack:** Knoema portal exposes REST/JSON (`/api/2.0/data?datasetId=...`) with optional SDMX-JSON output. KeNADA exposes IHSN NADA REST API (study/metadata/microdata, DDI/XML + JSON). opendata.go.ke offers ArcGIS REST/GeoJSON/CSV. KNBS itself: PDF + Excel only.
**Auth/limits:** Knoema requires App ID + App Secret (free signup; undocumented rate cap). KeNADA: anonymous browse + metadata; microdata gated by registration + research-use agreement.
**Coverage:** 4 ✓, 9 partial, 3 ✗. Census 2019 housing tenure, household size, marital status, 47 counties + sub-counties, urban/rural. Age × sex / education / employment status / industry / type / hours / income partial (PDF + microdata). Birth country detail ✗; time series effectively absent for direct API consumption.
**Classifications:** ISCED-mapped education; ISIC Rev. 4 for industry (per QLFS); ICSE for status-in-employment; 47 counties (ISO 3166-2:KE).
**Example query:** Knoema (closest queryable API): `GET https://kenya.opendataforafrica.org/api/1.0/data/details/{datasetId}?Time=2019&Region=KE&Sex=M;F&Age=0..100`. Native equivalent age × sex requires downloading `2019-Kenya-population-and-Housing-Census-Volume-3.pdf`.
**Python wrappers:** `knoema` (PyPI, official); `pynada` (IHSN admin client); `ipumsr`/`ipumspy` for census microdata. No KNBS-specific package.
**Blockers:** No first-party machine-readable API; Knoema is a third-party intermediary with auth, opaque coverage, unknown freshness; aggregates locked in PDF; microdata behind registration; opendata.go.ke is GIS-shaped, not statistical tables; time-series availability effectively absent for direct API consumption.
**Feasibility verdict:** **LOW** — without a PxWeb-style queryable API and with most KNBS aggregates locked in PDF/Excel, an automated, live-fetch generator equivalent to the SCB pipeline is not achievable; would require IPUMS microdata + manual PDF/Excel ETL.

#### Egypt
**API name & URL:** No native CAPMAS API. Indirect routes: (a) Egypt Data Portal (Knoema) `https://egypt.opendataforafrica.org/` + Knoema base `https://knoema.com/api/1.0/`; (b) NADA 4.0 microdata catalog at `https://censusinfo.capmas.gov.eg/Metadata-en-v4.2/` (metadata-only, file-download). CAPMAS itself (`capmas.gov.eg`) publishes only PDFs/Excel.
**Technology stack:** Knoema mirror exposes REST + JSON + `/sdmx/get` Compact-SDMX endpoint and `/data/pivot` POST. NADA catalog uses DDI Codebook 2.n; data files SPSS/Stata. No PxWeb anywhere.
**Auth/limits:** Knoema requires App ID + App Secret (free signup; HTTP 403 without). Microdata via ERF/CAPMAS NADA require researcher account + license; HIECS public release only 50% sample.
**Coverage:** 3 ✓, 10 partial, 3 ✗. 2017 census tabulations on Knoema for marital status, 27 governorates, urban/rural. Age × sex / education / employment / industry / type / hours / income / housing tenure / household size / migration partial. Birth country detail ✗; parental structure ✗.
**Classifications:** ISCED-compatible education; ISIC Rev.4 (since Jan 2020) for industry — not NACE; ICSE for employment status; CAPMAS-internal governorate codes (not NUTS).
**Example query:** Age × sex via Knoema SDMX — `GET https://knoema.com/api/1.0/sdmx/get/CAFPMSEPE2016?dimensions=location,age,sex&format=compact` (requires `?client_id=...&client_secret=...`). No equivalent direct CAPMAS URL.
**Python wrappers:** `knoema` on PyPI (official driver, MIT, pandas≥2.0). No CAPMAS-specific package. NADA has no maintained Python client.
**Blockers:** No native CAPMAS programmatic API — must rely on Knoema mirror, which lags and is incomplete; Knoema requires registration + secret; most granular data (1-yr age × sex, education × age, income deciles) lives in PDFs or licensed microdata; bilingual Arabic/English with inconsistent English coverage; HIECS public release truncated to 50%.
**Feasibility verdict:** **LOW** — CAPMAS lacks a PxWeb-equivalent API and the only programmatic path (Knoema) is auth-gated, partial, and would still leave ~half the 16 dimensions to be scraped from PDFs or licensed microdata.

### Asia — Middle East (batch 3)

#### Saudi Arabia
**API name & URL:** GASTAT Statistical Database `https://database.stats.gov.sa` (interactive web only); GASTAT Open Data "APIDex" `https://dp.stats.gov.sa/opendata`; National Data Bank (CKAN) `https://data.gov.sa`; KAPSARC Data Portal (Opendatasoft, GASTAT-sourced) `https://datasource.kapsarc.org`. No PxWeb-equivalent first-party API.
**Technology stack:** GASTAT itself: web portal + bulk PDF/XLSX/CSV. APIDex page is a black-box JS app with no documented endpoints. data.gov.sa: CKAN REST (`/api/3/action/package_search`, JSON, ~1000 req/h). KAPSARC: Opendatasoft Explore API v2.1 (REST/JSON, ODSQL filtering, CSV/JSON/GeoJSON exports). GASTAT participates in SDMX events but exposes no public SDMX endpoint.
**Auth/limits:** No auth on data.gov.sa (1000/h/IP). KAPSARC public read unauthenticated. APIDex effectively unusable programmatically.
**Coverage:** 7 ✓, 6 partial, 2 ✗. Census 2022 1-yr age × sex via KAPSARC, ISIC4 industry, LFS, household tenure, household size, marital status, 13 admin regions, Saudi/non-Saudi split. Income deciles ✗; parental structure ✗.
**Classifications:** ISIC Rev. 4 (national since ~2018); ISCED for education; ISCO; 13 admin regions.
**Example query:** `GET https://datasource.kapsarc.org/api/explore/v2.1/catalog/datasets/population-by-detailed-age-gender-governorate-nationality-and-region/records?select=age,gender,sum(population)%20as%20pop&group_by=age,gender&limit=100`.
**Python wrappers:** None GASTAT-specific. Generic: `ckanapi` for data.gov.sa; plain `requests` against Opendatasoft v2.1 (community `opendatasoft-explore` clients); `sdmx1` unusable.
**Blockers:** GASTAT has no first-party machine-readable API comparable to SCB PxWeb; APIDex is undocumented and JS-only; conditional cross-tabs (e.g. employment | education | age × sex) not exposed; income deciles and parental structure unavailable; many primary tables in PDF/XLSX; KAPSARC and RCRC are GASTAT-derived but coverage partial; bilingual schema inconsistent.
**Feasibility verdict:** **MEDIUM** — Core dimensions obtainable via KAPSARC/RCRC Opendatasoft and data.gov.sa CKAN, but absence of a true PxWeb-style cross-tab API means conditional sampling for income deciles, parental structure, and education×employment requires manual ETL from PDFs.

#### Israel
**API name & URL:** Israel CBS — Time Series DataBank API at `https://apis.cbs.gov.il/series/`, separate Price Indices API at `https://api.cbs.gov.il/index/`. Doc landing: `https://www.cbs.gov.il/en/Pages/API-Time-Series.aspx`. Census 2022 dashboard at `census.cbs.gov.il/en` (no documented API).
**Technology stack:** REST over HTTPS. Output: `xml | json | csv | xls` via `format=`. Hierarchical catalog navigation (`/catalog/level?id=N`, `/catalog/path?id=2,1,1,2,379`) plus data retrieval (`/data/list?id=<series>`, `/data/path`). Separate SDMX endpoint advertised. NOT PxWeb, NOT JSON-stat — bespoke schema. English + Hebrew via `lang=en|he`.
**Auth/limits:** No API key/registration. **Mandatory `User-Agent` header**. Pagination via `page` and `pagesize` (max 1000). No published rate limit.
**Coverage:** 4 ✓, 11 partial, 1 ✗. LFS monthly since 1954, Israeli SIC 2011 (ISIC4-aligned) industry, hours worked, 6 districts + 15 sub-districts, Israel-born / foreign-born split, time series. Age × sex partial (no documented joint single-year API table); parental structure ✗.
**Classifications:** Israeli SIC 2011 (ISIC4-aligned, NOT NACE; 21 sections / 91 divisions); Israeli ISCED adaptation; ISCO-aligned occupation. No NUTS.
**Example query:** `GET https://apis.cbs.gov.il/series/catalog/level?id=1&format=json&lang=en` then drill via `/catalog/path?id=<comma_codes>` and `GET https://apis.cbs.gov.il/series/data/list?id=<seriesCode>&startPeriod=01-2022&endPeriod=12-2022&format=json&lang=en`. Mandatory User-Agent header.
**Python wrappers:** No mature PyPI package. `amirrosi/israeli-cbs-mcp` (MCP server, statistical series + price indices only) and `LiorVainer/data-israel`. Both narrow; would write a thin HTTP client.
**Blockers:** No JSON-stat / PxWeb — bespoke response schema; subject codes not publicly enumerated, recursive `/catalog/level` walks needed; most demographic tables are 1-D time series, not n-dimensional crosstabs (Census 2022 has no API); English/Hebrew label inconsistencies; microdata gated; mandatory User-Agent gotcha.
**Feasibility verdict:** **MEDIUM** — REST API is open, free, covers most marginal distributions, but lack of multi-dimensional crosstabs (especially Census 2022) and absence of PxWeb/JSON-stat means conditional-chained-sampling architecture used for SCB/SSB needs significant adaptation and per-dimension hand-mapping rather than a near-drop-in port.

#### Turkey
**API name & URL:** TÜİK NSI Web Service. Catalog UI: `https://data.tuik.gov.tr` (redirects to `veriportali.tuik.gov.tr`). API root: `https://nsiws.tuik.gov.tr/rest/` (NSI Web Service v8.15.1.0).
**Technology stack:** SDMX 2.1 REST (NOT PxWeb). Native format SDMX-ML (XML); SDMX-JSON via content negotiation. URL pattern: `/rest/dataflow/{agencyID}/{flowID}/{version}` for structures and `/rest/data/{agency},{flow},{version}/{key}/?startPeriod=...&endPeriod=...` for data. 367 dataflows under agency ID `TR`.
**Auth/limits:** No authentication, no API key, plain HTTPS (HSTS enforced). NSI endpoint open. No documented rate limit; only GET allowed (HEAD/POST return 405). Microdata via separate research-application.
**Coverage:** 13 ✓, 2 partial, 1 ✗. `DF_ADNKS_T16` age × sex × province (5.4 MB live for 2024), `DF_BED_NUFUS_DAGILIM` education, monthly LFS, NACE Rev. 2 industry, status in employment, working hours, household size + type, marital status, 81 il (NUTS-3), birth location + country detail, urban/rural, time series via `startPeriod`/`endPeriod`. SILC income deciles partial (only enterprise-level dataflow); housing tenure ✗ (only census bulletin PDFs); parental structure partial.
**Classifications:** NACE Rev. 2 (= ISIC Rev. 4); ISCED-2011 (nationally adapted); ISCO; NUTS-equivalent SR (Statistical Regions) Levels 1-3 plus 81 il. DSDs include `DSD_ADNKS` v1.7.
**Example query:** `GET https://nsiws.tuik.gov.tr/rest/data/TR,DF_ADNKS_T16,1.0/ALL/?startPeriod=2024&endPeriod=2024` `Accept: application/xml`. Returns SDMX-ML 2.1 GenericData (~5.4 MB). Structure: `GET /rest/dataflow/TR/DF_ADNKS_T16/latest?references=Descendants`.
**Python wrappers:** No TUIK-specific Python package. TUIK is not registered in `pandaSDMX` / `sdmx1` source lists, but since endpoint is standards-compliant SDMX 2.1 REST, adding via `sdmx.add_source({"id":"TUIK","url":"https://nsiws.tuik.gov.tr/rest/", ...})` is trivial. R: `emraher/tuikr` (uses `rsdmx::readSDMX`).
**Blockers:** Dataflow IDs/dimensions in Turkish (labels EN via `lang=en` metadata but ID strings TR); no SILC income-decile distribution in SDMX catalog (significant gap vs SCB); no housing-tenure dataflow (only census bulletins); version pinning required (`1.0` vs `1.1` returns 404); only GET (no POST fallback for very long keys); developer docs almost zero — must reverse-engineer from `tuikr` source.
**Feasibility verdict:** **MEDIUM** — Live, unauthenticated, standards-compliant SDMX 2.1 REST with strong coverage of 13/16 dimensions makes integration architecturally straightforward, but absent income-decile and housing-tenure dataflows plus Turkish-only field IDs and minimal documentation require fallbacks (bulletin scraping or dropping fields per the project's no-hardcoded-data rule).

### Africa — extended (batch 3)

#### Morocco
**API name & URL:** Three overlapping channels: HCP institutional (`https://www.hcp.ma`, `https://bds.hcp.ma`, BDS interactive, Excel only); national CKAN portal `data.gov.ma` hosting ~79 HCP datasets at `https://www.data.gov.ma/data/api/3/action/`; Knoema mirror `morocco.opendataforafrica.org` (third-party).
**Technology stack:** CKAN 2.x Action API (JSON) on data.gov.ma. No PxWeb. No SDMX. No JSON-stat. HCP itself publishes XLSX/PDF/Word; "APIs activées" refers to back-end automation feeding data.gov.ma. Knoema mirror exposes proprietary REST/JSON.
**Auth/limits:** data.gov.ma CKAN: anonymous read, no documented rate limits. Knoema requires login/API key. HCP microdata: anonymized files, no automated download.
**Coverage:** 4 ✓, 8 partial, 4 ✗. ENE quarterly bulletins, NMA 2010 industry (ISIC4-aligned), 12 régions, urban/rural. Income deciles, birth location group, birth country detail, time series ✗.
**Classifications:** NMA 2010 (full concordance with ISIC Rev. 4); HCP national education levels (loosely ISCED-mappable); no formal NACE.
**Example query:** `GET https://www.data.gov.ma/data/api/3/action/package_list` returns JSON. Resource-level data via `…/datastore_search?resource_id=<uuid>&limit=1000` (CKAN standard) — no native age × sex query; download whole resources and parse client-side.
**Python wrappers:** No official package. `ckanapi` (generic CKAN client) works. `mohtamimad/datagovma-mcp` wraps it as MCP. No PxWeb/JSON-stat library applies.
**Blockers:** No PxWeb-style cube query — cannot request a sliced (age, sex, region) tensor in one call; documentation French/Arabic; latest RGPH 2024 results published primarily as Apache Superset dashboards (`resultats2024.rgphapps.ma`), not raw API; most HCP microdata locked to 2014 RGPH and 2013/14 ENCDM; HCP "APIs" referenced are internal feeds, not user-facing endpoints.
**Feasibility verdict:** **LOW** — Morocco offers rich underlying data but lacks a queryable statistical-cube API; substituting would require rewriting `FetchService` to download CKAN XLSX/CSV resources and parse offline, abandoning the chained conditional sampling architecture's clean per-dimension fetches.

#### Ghana
**API name & URL:** Ghana Statistical Service (GSS) StatsBank — PxWeb portal `https://statsbank.statsghana.gov.gh/pxweb/en/` with REST API base `https://statsbank.statsghana.gov.gh/api/v1/en/`. Microdata catalog at `microdata.statsghana.gov.gh`; census portal `census2021.statsghana.gov.gh`.
**Technology stack:** PxWeb (same Statistics Sweden stack as SCB) — RESTful, JSON-stat output, POST queries with `query`/`response` body, GET for metadata. Identical query semantics to SCB; `pyaxis`/`pxweb` Python clients work out of the box.
**Auth/limits:** No authentication, no registration, no documented rate limit. Per-table cell ceiling: 100,000 cells; on-screen 1,000 rows × 150 cols. Latest update April 2023.
**Coverage:** 11 ✓, 3 partial, 3 ✗. PHC 2021 covers age × sex (single ages 0-100+), 18-cat education, employment status, industry, housing tenure, household size, marital status, 295-cat geography, place of birth, urban/rural. Working hours, parental structure, time series ✗.
**Classifications:** Ghana ISCED 2011 mapping (Nursery/Primary/JSS/SSS/Tertiary), ISIC Rev. 4 for industry, ILO LFS-style employment status. Locality types GSS-defined (urban threshold 5,000 pop).
**Example query:** `POST https://statsbank.statsghana.gov.gh/api/v1/en/PHC%202021%20StatsBank/PHC%202021%20StatsBank__Population/population_table.px` body `{"query":[{"code":"Geographic_Area","selection":{"filter":"item","values":["Ghana"]}},{"code":"Sex","selection":{"filter":"item","values":["Male","Female"]}},{"code":"Age","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}`.
**Python wrappers:** `pyaxis` (parses PX into pandas), `pxweb` (PyPI generic) — both work without modification; existing `anxiety_synthetic/utils/scb_client.py` reusable with only base-URL swap.
**Blockers:** Single census snapshot (no annual updates like SCB); income deciles not exposed via PxWeb (would require GLSS7 microdata, DDI-XML); most PHC tables forced through District/Region/Locality/Education axes (cell-budget pressure for 100k limit); no working-hours, employment-type, or parental-structure tables; PDF user-guide image-scanned.
**Feasibility verdict:** **HIGH** — Ghana's StatsBank runs the same PxWeb engine as SCB so the existing client/fetch architecture transplants directly, with 11/16 dimensions fully covered; income decile and working-hours gaps would need to be dropped or sourced from GLSS7 microdata.

#### Ethiopia
**API name & URL:** ESS (formerly CSA) at `https://ess.gov.et`. Listed portals: ESS Stat Bank `https://databank.ess.gov.et/reports` (HTTP probes refused/timed out), Redatam web at `http://imisethiopia.gov.et/redbin/RpWebEngine.exe/Portal` (403/refused), Knoema-hosted `https://ethiopia.opendataforafrica.org` plus dev endpoint `https://opendataforafrica.org/dev/explorer`. No first-party PxWeb/JSON-stat.
**Technology stack:** No PxWeb, no SDMX, no JSON-stat from ESS itself. Public dissemination is browser-only download of PDF/Excel reports. Programmatic access only through third-party Knoema (proprietary REST + OAuth-style App ID/Secret), and CSPRO/Redatam for census tabulations. Microdata external (IPUMS, World Bank Microdata, ILO surveyLib).
**Auth/limits:** ESS site itself: none, but no API. Knoema/ODA: free read, beyond browser scraping requires `knoema.com/user/apps` registration for App ID + App Secret; rate limits unpublished. IPUMS/WB microdata project-approval gated. Redatam returns 403 to programmatic clients.
**Coverage:** 1 ✓, 12 partial, 3 ✗. Urban/rural split standard; everything else partial via PDF reports or microdata. Birth location, birth country, time series ✗.
**Classifications:** Education roughly ISCED-mapped via DHS/ESPS variables; industry uses ISIC Rev. 4 in NLFS 2021; ILO ICSE/ICLS for employment status. No published SDMX code-list service.
**Example query:** No native ESS API. Closest: `GET https://opendataforafrica.org/api/1.0/data/{datasetId}?Country=Ethiopia&Indicator=Population&Time=2020` with `Authorization: Knoema {AppId}:{Hash}` headers. For age × sex no single canonical dataset — must scrape 2007 census Excel from `ess.gov.et/download/...`.
**Python wrappers:** `knoema` on PyPI (`pip install knoema`) pointed at `host='opendataforafrica.org'`; no ESS-specific package. `pxweb` irrelevant (no PxWeb endpoint). IPUMS has `ipumspy` for microdata extracts.
**Blockers:** No first-party machine-readable API (fatal for SCB-style live-fetch architecture); latest full census 2007 (~19 years stale); 4th census reference April 2026 — no results yet; Knoema is third-party with patchy coverage; Redatam/Stat Bank/IMIS reject programmatic requests; microdata gated by manual project approval; birth-country and time-series essentially absent.
**Feasibility verdict:** **LOW** — Ethiopia has no PxWeb/SDMX/JSON-stat equivalent; only PDF/Excel reports and a third-party Knoema mirror, with the most recent census 19 years old, violating "all distributions from live API calls" rule.

#### Tanzania
**API name & URL:** No native PxWeb/REST API at NBS Tanzania. Closest: (1) NBS Tanzania Data Portal hosted by Knoema `https://nso-tanzania.opendataforafrica.org/` and `https://tanzania.opendataforafrica.org/`, exposing Knoema API at `https://knoema.com/api/1.0/data/...`; (2) NADA microdata at `https://microdata.nbs.go.tz/`; (3) TISP front-end at `https://tisp.nbs.go.tz/` (no documented API).
**Technology stack:** No JSON-stat / SDMX. Knoema mirror provides proprietary JSON REST API (NOT JSON-stat). NADA exposes DDI/XML metadata only — microdata downloads zipped CSV/Stata after login. NBS itself publishes mostly PDF + Excel/CSV. No PxWeb implementation found.
**Auth/limits:** Knoema mirror — public access ~50 requests for unauthenticated; authenticated requires App ID + App Secret. Knoema is in legacy/decline (CRAN package removed; Snowflake users report dataset disappearance 2024–2025). NADA microdata requires free user registration + research-purpose declaration per dataset.
**Coverage:** 2 ✓, 12 partial, 2 ✗. PHC 2022 mean HH size by region, 31 regions + 184 districts, urban/rural strata. Birth country detail, parental structure ✗.
**Classifications:** ISCED 2011, ISIC Rev.4, ICLS-19, region → district → ward → village hierarchy. No NACE; no harmonised income deciles.
**Example query:** Knoema REST (best available) — `GET https://knoema.com/api/1.0/data/nso-tanzania/PHC2022?dimensions=Region,Age,Sex&format=json` (requires App ID/Secret header). No equivalent direct NBS endpoint.
**Python wrappers:** `knoema` (PyPI, GitHub Knoema/knoema-python-driver) — works but service in maintenance mode and dataset coverage shrinking. No `pyscbwrapper`/`pxweb`-style native NBS package.
**Blockers:** No native API (must scrape Knoema mirror or PDFs); Knoema platform unstable (datasets vanishing; CRAN R-package removed); NADA microdata gated behind manual registration + per-dataset purpose statement; many dimensions only in PDF; HBS uses consumption proxy (not income deciles); decennial census means most dimensions are 2022 snapshot.
**Feasibility verdict:** **LOW** — Tanzania has rich underlying surveys (PHC 2022, ILFS 2020/21, HBS 2017/18) but exposes them through PDFs, registration-gated microdata, and a deprecating third-party Knoema mirror; live PxWeb-style chained-conditional sampling cannot be built without manual data ingestion.

### Latin America (batch 3)

#### Argentina
**API name & URL:** Primary: API de Series de Tiempo `https://apis.datos.gob.ar/series/api/` (centrally hosted by Jefatura de Gabinete; aggregates INDEC indicators). Census processing: Redatam REST API (REST4Red / Redatam7) `https://redatam.indec.gob.ar/`. Microdata FTP: `https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/` (EPH .txt/.dbf zips, no API).
**Technology stack:** Series de Tiempo — REST + JSON/CSV/XLSX, query by series IDs (no PxWeb, no JSON-stat). Redatam — CGI executing SPC scripts (Redatam DSL), returns JSON via REST4Red. Not URL-parametric — POST a Redatam program string. EPH bulk file download only (DBF/TXT in ZIP/RAR).
**Auth/limits:** Series de Tiempo: no auth; max 1000 observations and 100 series per request; CORS open. Redatam: no auth, session-based interactive console; programmatic use undocumented and fragile. EPH FTP: no auth.
**Coverage:** 13 ✓, 3 partial, 0 ✗. Censo 2022 + EPH cover age × sex (1-yr), education, employment, ClaNAE-2018 industry (ISIC Rev.4-aligned), employment type, hours, ingresos deciles, housing tenure, household size, marital status, 24 provincias + departamentos, migration (incl. country-of-birth), parental structure derivable, urban/rural at radio level.
**Classifications:** Education ≈ ISCED but uses local categories; ClaNAE-2018 (CIIU Rev.4 / ISIC Rev.4 derivative); CNO-2001 occupations (ISCO-88-mappable); provincia (24) → departamento/partido → localidad → radio censal.
**Example query:** Series API: `GET https://apis.datos.gob.ar/series/api/series?ids=458.1_PROYECCIONES_AGENT_0_M_38&format=json&limit=1000`. Redatam SPC: `POST https://redatam.indec.gob.ar/cgi-bin/RpWebEngine.exe/PortalAction` with body `RUNDEF Job; SELECTION ALL; TABLE T1 AS CROSSTABS OF PERSONA.P02 BY PERSONA.P03`.
**Python wrappers:** `pyeph` (institutohumai/pyeph, on PyPI) — EPH download + labor/poverty calcs; `microdatos-EPH-INDEC` (matuteiglesias) — CLI EPH ZIP→CSV; `PyRedatam` — early-stage Redatam library. R `eph` (rOpenSci) more mature. No PxWeb-style wrapper.
**Blockers:** No PxWeb / JSON-stat — every dimension needs different access path (Series API for aggregates, Redatam for census crosstabs, FTP+DBF for EPH microdata) — three distinct clients. Redatam API poorly documented in English, requires SPC scripts; programmatic stability uncertain. EPH covers only 31 urban agglomerates (~63% of population). Spanish-only docs. Historical INDEC credibility issues 2007–2015 (CPI manipulation). Census 2022 microdata not yet IPUMS at time of writing.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable from authoritative INDEC sources, but heterogeneous stack (Series-API + Redatam-SPC + EPH-FTP+DBF) means a substitution would require 3 distinct clients rather than the single PxWeb client used for SCB/SSB.

#### Chile
**API name & URL:** INE Chile. Browseable: `https://stat.ine.cl/` (INE.Stat — OECD .Stat / ASP.NET-based), `https://redatam-ine.ine.cl/` (Redatam web for census microdata), `https://www.ine.gob.cl/` (publication site), `https://datos.gob.cl/` (CKAN open-data catalog). 2024 Census micro-database released Dec 2025 at censo2024.ine.gob.cl.
**Technology stack:** stat.ine.cl runs OECD .Stat platform — same family as SCB's PxWeb conceptually but NOT PxWeb. UI exports xls/csv/sdmx-xml; URLs use `Index.aspx?DataSetCode=XXX` and `OECDStat_Metadata/ShowMetadata.ashx?DataSet=XXX`. NO publicly documented SDMX-JSON / REST endpoint (unlike OECD's main `sdmx.oecd.org/public/rest/`). Redatam-INE uses Redatam7 SPC programs over HTTP (`RpWebEngine.exe/Portal?BASE=...`). Bulk microdata as CSV/SPSS/Stata.
**Auth/limits:** No registration, no API key, no published rate limits. Aggregated data fully open; microdata downloads public but require accepting terms.
**Coverage:** 12 ✓, 4 partial, 0 ✗. Censo 2024 + ENE + ESI cover age × sex (single-year), CINE 2011 education, CIIU4.CL industry (ISIC Rev.4), employment type, hours, ESI deciles, housing tenure, household size, civil status, 16 regiones + 346 comunas, urban/rural. Birth location/country detail, parental structure, time series partial.
**Classifications:** CINE 2011 (= ISCED 2011); CIIU4.CL 2012 (ISIC Rev.4 adapt., interconvertible with NACE Rev.2 via ISIC); CIUO-08.CL occupation; CAENES (CIIU4.CL subset) used in ENE coding API.
**Example query:** No documented JSON-stat / SDMX-JSON endpoint for stat.ine.cl. Closest: `https://stat.ine.cl/OECDStat_Metadata/ShowMetadata.ashx?DataSet=ENE_TD&Lang=en` (metadata XML), bulk via `Index.aspx?DataSetCode=ENE_TD` plus SDMX-XML export button. Redatam programmatic queries via SPC programs to `redatam-ine.ine.cl/redbin/RpWebEngine.exe/Portal?BASE=CENSO_2017`.
**Python wrappers:** None first-class for Chile. `ine-python` and `ineware` on PyPI both target Spain's INE. R has `redatamx` and `censo2017` (rOpenSci); no Python equivalent — would need (a) HTML/XML scraping, (b) Redatam SPC over HTTP, or (c) CSV/SPSS dumps via pandas/`pyreadstat`.
**Blockers:** No documented machine-readable REST on stat.ine.cl — only manual SDMX-XML/CSV per dataset; would need to reverse-engineer the .Stat endpoints. Census 2024 microdata only released Dec 2025 in CSV/dictionary form, not via API. Documentation Spanish only. Redatam needs bundled .dicx + parser or SPC programs — heavier than PxWeb POST-JSON. No equivalent of SCB's clean joint cross-tab in a single API call.
**Feasibility verdict:** **MEDIUM** — All 16 dimensions conceptually covered by INE Chile sources (Censo 2024, ENE, ESI), but absence of a documented PxWeb/SDMX-JSON REST API means substituting the SCB client requires either scraping stat.ine.cl SDMX-XML exports or writing a Redatam-CSV ingestion layer.

#### Colombia
**API name & URL:** DANE — multiple fragmented endpoints, no unified PxWeb. REDATAM webserver (Census 2018/2005): `https://systema59.dane.gov.co/bincol/RpWebEngine.exe/PortalAction`. Microdata catalog (NADA): `https://microdatos.dane.gov.co/`. Open data (Socrata SODA): `https://www.datos.gov.co/`. Geoportal REST (ArcGIS): `https://geoportal.dane.gov.co/mparcgis/rest/services`. Static PDF/XLS bulletins: `https://www.dane.gov.co/`.
**Technology stack:** No PxWeb, no JSON-stat, no SDMX. REDATAM (CELADE proprietary CGI returning HTML/XLS, no JSON), ArcGIS REST (geo only), Socrata SODA (REST/JSON for `datos.gov.co`), NADA microdata (DDI-XML metadata + raw CSV/SAV after registration). Headline labour/demographic figures as PDF + XLSX annexes.
**Auth/limits:** Public web pages no auth. Microdata (GEIH, CNPV raw) requires free account on `microdatos.dane.gov.co`. Socrata supports anonymous; recommends app tokens. No documented rate limit on REDATAM.
**Coverage:** 11 ✓, 4 partial, 1 ✗. CNPV 2018 + GEIH cover age × sex (1-yr + projections), CINE-N 2011 education, employment status, CIIU Rev. 4 A.C. industry, formal/informal type, housing tenure, household size, civil status, departamento/municipio (DIVIPOLA), migration (lugar de nacimiento), parental structure (nuclear/monoparental), urban/cabecera/rural disperso. Working hours, income decile, birth country detail partial; time series partial.
**Classifications:** CIIU Rev. 4 A.C. (CIIU/NACE Rev. 2 adapt., Resolución 066/2012); CINE-N 2011 A.C. + CINE-F 2013 A.C. (= ISCED 2011 / ISCED-F 2013); DIVIPOLA; CIUO-08 A.C.
**Example query:** REDATAM CrossTab (HTML/XLS, not JSON): `GET https://systema59.dane.gov.co/bincol/RpWebEngine.exe/CrossTab?BASE=CNPVBASE4V2&ITEM=DICVIV42&MAIN=WebServerMain.inl&MODE=MAIN&lang=esp` plus `VAR1=`/`VAR2=` form parameters.
**Python wrappers:** No official DANE SDK. `pyredatam` (abenassi/pyredatam, Argentina-focused, generates SPC), `open-redatam` (pachadotdev, C++/R/Python, reads .dicx locally not via API), `sodapy` (Socrata client). All require glue.
**Blockers:** No PxWeb/JSON-stat/SDMX — REDATAM returns HTML/XLS; documentation Spanish only; GEIH labour distributions only as PDF bulletins + XLSX annexes; income deciles, working hours, and birth-country detail must be derived from GEIH/CNPV microdata (free but registration-gated); REDATAM unreachable during research; Census reference 2018.
**Feasibility verdict:** **MEDIUM** — all 16 dimensions obtainable from CNPV 2018 + GEIH + DIVIPOLA, but no PxWeb-style API; substituting SCB requires either an HTML-scraping REDATAM client or microdata-download + local-aggregation pipeline (via `open-redatam` / pandas), materially more work than SCB/SSB.

#### Peru
**API name & URL:** Multiple fragmented sources, no unified PxWeb. (a) INEI REDATAM Webserver — `https://censos2017.inei.gob.pe/bininei2/RpWebEngine.exe/Portal?BASE=CPV2017&lang=esp` (CPV 2017 census), mirrored at CEPAL. (b) Plataforma Nacional de Datos Abiertos (CKAN) — `https://www.datosabiertos.gob.pe/api/action/datastore_search`. (c) ENAHO microdata FTP-style — `http://iinei.inei.gob.pe/iinei/srienaho/descarga/SPSS/{ID}-Modulo{N}.zip`.
**Technology stack:** REDATAM+SP Webserver (HTML/JS UI; REST/JSON in newer Redatam7 builds but not publicly documented for INEI). CKAN datastore_search returns JSON. Microdata is raw SPSS/STATA ZIP. No PxWeb, SDMX, JSON-stat.
**Auth/limits:** No API key for any endpoint. INEI iinei host HTTP-only (no HTTPS), no CORS. CKAN portal honors standard CKAN limits. No documented rate limits.
**Coverage:** 5 ✓, 10 partial, 1 ✗. CPV2017 housing tenure (76% own, 16.3% rent), household size, civil status, departamento/provincia/distrito (Ubigeo), urban/rural. Time series ✗ (Census 2017 single-point; ENAHO annual but per-year microdata).
**Classifications:** CIIU Rev. 4 (NACE-equivalent, official since 2010); CINE 2011 (Peruvian ISCED variant) used in MINEDU but census uses domestic categories; UBIGEO codes.
**Example query:** CKAN: `GET https://www.datosabiertos.gob.pe/api/action/datastore_search?resource_id=<RID>&filters={"sexo":"F"}&limit=1000`. No parameterised REST query URL for the REDATAM age × sex cross-tab — REDATAM xPlan is GUI-driven.
**Python wrappers:** `enahodata` (PyPI), `enahopy` (GitHub elpapx) for ENAHO ZIP downloads; `redatamx` (R, CRAN) and `pachadotdev/open-redatam` (C++/R/Python) for parsing REDATAM RXDB/DICX locally; `hpneo/ubigeo` for geo codes. No Python wrapper hits a live INEI tabulation endpoint.
**Blockers:** No PxWeb / JSON-stat / SDMX endpoint (biggest gap vs SCB); REDATAM Webserver is interactive HTML; ENAHO is raw microdata in SPSS/STATA — distributions must be computed from sampled records (with weights); HTTP-only host, no HTTPS/CORS; Spanish-only docs; time series for census dimensions essentially single-shot (2017).
**Feasibility verdict:** **MEDIUM** — All 16 dimensions obtainable from CPV2017 + ENAHO microdata using mature Python wrappers, but no PxWeb-equivalent live API; substituting SCB requires re-architecting from "fetch published distributions" to "download microdata ZIPs and compute weighted distributions locally."

#### Venezuela
**API name & URL:** No formal public PxWeb-style API. INE Venezuela `https://ine.gob.ve/` (formerly ine.gov.ve) publishes XLS/XLSX "tabulados". Legacy ANDA microdata catalog at `http://www.ine.gov.ve/anda4/` (currently refused connection). REDATAM web servers `http://www.redatam.ine.gob.ve/Censo2011/` and `/Censo2001/` (also unreachable). CEPAL/CELADE provides REDATAM access pages at `https://redatam.org/en/online-process/latam/ven`.
**Technology stack:** No JSON-stat / PxWeb. Primary delivery static XLS/XLSX/PDF tabulados. Census microdata wrapped in REDATAM (proprietary CELADE engine); CELADE's REST4Red JSON service not exposed as documented public endpoint for Venezuela. NADA/ANDA catalog (DDI metadata) is the only structured option.
**Auth/limits:** Tabulados anonymous downloads. ANDA microdata typically require user registration + confidentiality agreement. No documented rate limits, no public API key.
**Coverage:** 1 ✓, 13 partial, 2 ✗. 11 estado/municipio in Censo 2011 strong; income deciles ✗ (hyperinflation-era data unreliable); time series ✗ (major gap 2018–2024; UN vital-stats feed stopped 2019).
**Classifications:** CAEV (Clasificación de Actividades Económicas de Venezuela, derived from CIIU/ISIC Rev.4); national education ladder roughly ISCED-mappable; estado/municipio/parroquia codes.
**Example query:** None possible as direct PxWeb-style URL. Closest analog: navigate `https://ine.gob.ve/censos/` → download XLSX. A REDATAM job would be POSTed to a CELADE-hosted `/redbin/RpWebEngine.exe` with custom .spc — not stable, documented interface.
**Python wrappers:** None target Venezuela. `ineware` and `INEbaseR` address Spain's INE, not Venezuela. No PyPI package found; would require custom XLSX scrapers and/or REDATAM job runner.
**Blockers:** No machine-readable API — entire pipeline would be XLSX scraping; backbone reference Censo 2011 (~14 years stale); XV Censo 2024 results just beginning to publish; EHM publication effectively halted ~2017–2018; income series unusable due to hyperinflation; Spanish-only; domains intermittently unreachable (ine.gov.ve refused connection during research; redatam.ine.gob.ve also unreachable); ~7.9M emigration means even fresh data drift sharply.
**Feasibility verdict:** **LOW** — No PxWeb/JSON-stat API exists, freshest comprehensive microdata is the 2011 census with EHM gaps post-2018, and substituting SCB would mean writing bespoke XLSX/REDATAM scrapers against an unstable, partially-offline site.

#### Uruguay
**API name & URL:** INE Uruguay primary portals: `https://www.ine.gub.uy/`, microdata catalog (NADA-based) `https://www4.ine.gub.uy/Anda5/`, open-data portal `https://www4.ine.gub.uy/Anda5/index.php/opendata`, CEPAL-hosted REDATAM webserver for the 2023 Census `https://www.redatam.org/redury/` (redirects to `https://prod.redatam.org/redury/`). National open-data catalog: `https://catalogodatos.gub.uy/organization/ine`.
**Technology stack:** No PxWeb, no JSON-stat, no SDMX. INE itself distributes only bulk-download microdata (CSV / SAV / SPSS / RAR / XLS / PDF) via ANDA NADA, plus a legacy "Google Fusion Tables API" reference (Fusion Tables sunset 2019, dead). Only structured query: REDATAM REST4Red (CGI on Apache, POST `/execute` accepting Redatam SPC programs, returning JSON for FREQUENCY / CROSSTABS / AREALIST / TABLELIST). No documented PxWeb-style URL-parameter querying.
**Auth/limits:** No authentication or registration documented. No published rate limits. Census microdata gated by INE's web interface, not API key.
**Coverage:** 11 ✓, 5 partial, 0 ✗. Censo 2023 + ECH cover all 16 dimensions, with birth-location/birth-country/parental structure and time series partial.
**Classifications:** CIIU Rev. 4 (adapted), CIUO-88 (occupations), CINE/ISCED for education. ISCED/NACE-compatible.
**Example query:** No simple URL-style query. REDATAM REST4Red requires a POST with SPC body, e.g. `POST https://prod.redatam.org/redury/api/execute` body `RUNDEF Job; TABLE T1 AS FREQUENCY OF PERSONA.SEXO BY PERSONA.EDAD;` returning JSON. No `?query=age*sex` shortcut.
**Python wrappers:** No first-class. Adjacent: `open-redatam` (pachadotdev / litalbarkai — converts REDATAM `.dicx` to CSV), `Open_Census` (bsotomayorg, framework for REDATAM extraction), `redatamx` (R), `ech` (R, ECH downloader 2011–2019). Python users typically download bulk SAV/CSV and process with pandas.
**Blockers:** No PxWeb / JSON-stat — would require brand-new fetch layer; REST4Red expects SPC programs, not category filters (major rewrite of `FetchService`); Spanish-only docs; Fusion Tables "API" defunct; Census 2023 microdata via REDATAM not symmetric with ECH bulk downloads (two parallel pipelines); no direct table-by-table catalog like SCB's 15 tables; some dimensions (parental structure, fine-grained birth country) need to be derived rather than fetched.
**Feasibility verdict:** **LOW** — INE Uruguay has rich underlying data (Censo 2023 + ECH cover ~14 of 16) but exposes no PxWeb-equivalent query API; substituting SCB would require rewriting the fetch layer around REST4Red SPC programs or bulk microdata aggregation, not a drop-in client swap.

#### Ecuador
**API name & URL:** INEC. Primary portals: `https://www.ecuadorencifras.gob.ec/`, REDATAM webserver `https://redatam.inec.gob.ec/cgibin/RpWebEngine.exe/PortalAction`, ANDA microdata catalog `https://anda.inec.gob.ec/anda/`, 2022 Census results at `https://www.censoecuador.gob.ec/`. No PxWeb-style API.
**Technology stack:** REDATAM webserver (CGI: `RpWebEngine.exe` / `RpWebStats.exe`) returning HTML; CELADE's REST4Red layer (POST `/execute` with SPC, returning JSON) is the only programmatic interface, NOT publicly exposed on INEC's domain. Bulk microdata as SPSS `.sav`, CSV, TXT (plus REDATAM dictionary/data files). PDF bulletins for ENEMDU. No JSON-stat, SDMX, or PxWeb endpoints anywhere.
**Auth/limits:** No authentication, no published rate limits. REDATAM portal open but session-based and HTML-only; microdata downloads require accepting terms, not registration.
**Coverage:** 0 ✓, 16 partial, 0 ✗. All dimensions reachable in principle via Census 2022 / ENEMDU / ENIGHUR microdata, but only as raw downloads not API queries.
**Classifications:** CIIU Rev. 4.0 (national 7-digit ISIC-aligned), CIUO-08 occupations, CINE/ISCED-2011 education, CPC products. Geographic codes follow INEC DPA (provincia-cantón-parroquia).
**Example query:** No JSON endpoint. Closest: HTML REDATAM crosstab `http://redatam.inec.gob.ec/cgibin/RpWebEngine.exe/EasyCross?BASE=CPV2001&ITEM=EDAD&MAIN=WebServerMain.inl` (HTML, not JSON). To get JSON, would need to host REST4Red against downloaded `.dicx`/`.rxdb` and POST SPC like `RUN; TABLE t1 AS FREQUENCY OF PERSONA.EDAD BY PERSONA.SEXO;` to `/execute`.
**Python wrappers:** No official SDK. Community: `bsotomayorg/Open_Census` (Redatam→SQLite ETL), `discontinuos/redatam-converter` (REDATAM to SPSS/Stata/R). R has `redatamx` and `redatam4r`. None talk to INEC over HTTP.
**Blockers:** No JSON/REST API — REDATAM webserver returns HTML only; bulk microdata SPSS/REDATAM proprietary; ENIGHUR stale (2011-12 last comprehensive); Spanish-only docs; ENEMDU bulletins are PDFs; HTTPS certificate issues on `aplicaciones2.ecuadorencifras.gob.ec` and `censoecuador.gob.ec` observed.
**Feasibility verdict:** **LOW** — INEC offers no PxWeb/JSON-stat-equivalent API; substituting SCB would require either hosting a REST4Red engine over downloaded REDATAM bases or writing an HTML scraper plus an SPSS microdata pipeline.

---

## Part 3 — Synthesis (refreshed after each batch)

**Coverage:** 73 jurisdictions = 20 (batch 1) + 24 (batch 2) + 29 (batch 3). Candidate pool from companion plan now exhausted.

### Feasibility tiers

**Tier 1 — Drop-in PxWeb family (HIGH + PxWeb protocol; lowest porting cost):**
| Country | API | Notes |
|---|---|---|
| Norway | SSB Statbank PxWebApi v2 | **Co-developed with SCB**; pin to v2; 30/min throttle |
| Iceland | Hagstofa PxWeb | Identical PxWeb stack; small-population disclosure caveat |
| Finland | StatFin PxWeb | Same family; 30/10 s throttle; `.px` URL suffix |
| Ireland | CSO PxStat (PxWeb fork) | JSON-stat v2.0 + PxAPIv1 compat shim |
| **Estonia** | Statistikaamet PxWeb v1 | 14 ✓ + 2 partial; 25M cells/call; Estonian variable codes |
| **Latvia** | OSP CSB PxWeb v1 | 13 ✓ + 3 partial; 100 calls/10 s; experimental DEGURBA |
| **Slovenia** | SiStat PxWeb v1 | 13 ✓ + 3 partial; up to 10M values/call; quintile-only income |
| **Switzerland** | BFS STAT-TAB PxWeb | 15 ✓ + 1 partial; 50 calls/15 min — tighter throttle than SCB; 4-language |
| **Croatia** | DZS PxWeb v1 (`web.dzs.hr`) | 10 ✓ + 6 partial; legacy host; chunking required |
| **Philippines** | PSA OpenSTAT PxWeb v1 | 11 ✓ + 4 partial + 1 ✗; JSON-STAT2; no auth; only ~5-yr ages from 2020 CPH |
| **Ghana** | GSS StatsBank PxWeb | 11 ✓ + 3 partial + 3 ✗; PHC 2021 single snapshot; no working hours/parental structure |

For these eleven, the existing `SCBPxWebClient` ports with **only base-URL, table-ID, and language-mapping changes**. Estimated effort: ~1-2 days per country.

**Tier 2 — HIGH feasibility but adapter required (non-PxWeb protocol):**
| Country | API | Format | Wrapper |
|---|---|---|---|
| Denmark | DST StatBank | REST + JSONSTAT | `dstapi` |
| Netherlands | CBS OData v3/v4 | OData JSON | `cbsodata` |
| Germany | Destatis GENESIS-Online | REST POST JSON (auth required) | `pystatis` |
| Spain | INE Tempus3 | REST JSON (proprietary) | `INEapy` |
| France | INSEE Mélodi | REST JSON / SDMX | `pynsee` |
| UK | Nomis + ONS Beta | REST JSON / SDMX | `ukcensusapi` |
| Canada | StatCan WDS | REST JSON (cube+coordinate) | `stats-can` |
| Australia | ABS Data API | SDMX 2.1 / SDMX-JSON | `sdmx1` |
| Japan | e-Stat (key required) | REST + JSON-stat | `jpstat` |
| South Korea | KOSIS (key required) | REST flat JSON | `PublicDataReader` |
| Brazil | IBGE SIDRA + Agregados v3 | REST flat JSON | `sidrapy` |
| **Czechia** | ČSÚ DataStat | REST + JSON-STAT v2 | none (direct `requests` + `pyjstat`) |
| **Luxembourg** | STATEC LUSTAT | SDMX 2.1 (.Stat Suite) | `sdmx1` |
| **Poland** | GUS BDL | REST + JSON | `pygus`, `bdlapi` |
| **Slovakia** | SO SR DATAcube | REST + JSON-stat v2 (URL-path queries) | `pyjstat` |
| **New Zealand** | Stats NZ Aotearoa Data Explorer | SDMX 2.1 (key required) | `sdmx1`, `pysdmx` |
| **Eurostat** | Eurostat dissemination | SDMX 2.1 + JSON-stat 2.0 | `eurostat`, `pandasdmx` |

Full or near-full coverage but a parallel client adapter (~3-5 days each). Tier-2 countries usually need a dedicated parser layer because the schema is not JSON-stat.

**Tier 3 — MEDIUM feasibility (significant work):**
| Country | Reason |
|---|---|
| Italy | 5 req/min hard cap with multi-day IP bans; SDMX DSD-driven queries |
| USA | Fragmented across Census/BLS/HUD/IRS-SOI; ACS sample (not register); no JSON-STAT |
| Mexico | Per-IndicatorId path-based queries; income/birth-country need microdata |
| India | 4 separate APIs to stitch; Census 2021 delayed to 2027; HCES microdata only |
| **Austria** | CSV-over-HTTP only; rich joint distributions behind paid STATcube; no JSON-stat |
| **Belgium** | BeStat "facts" JSON, fixed pre-saved views, no server-side filtering, no Python SDK |
| **Bulgaria** | PHP query-string endpoints (not PxWeb); hand-discovered numeric IDs |
| **Cyprus** | PxWeb v2 but 5-yr ages + census-only housing/family + weak income deciles |
| **Greece** | No native ELSTAT API — Eurostat-only fallback; some dimensions require PDF scraping |
| **Hungary** | HVD API exposes ~13 datasets; rest needs STADAT XLSX/CSV scraping; no JSON-stat |
| **Lithuania** | SDMX REST (not PxWeb); JSON-stat v2 ≠ SDMX-JSON; query layer rewrite needed |
| **Malta** | ~7/16 dimensions have NO dataflow; flows tagged `NonProductionDataflow=true` |
| **Portugal** | Bespoke INE JSON (not PxWeb / not JSON-stat); no maintained Python SDK |
| **Romania** | HTTP-only port 8077; 30k-cell cap; income/birth-country in PDFs only |
| **Albania** | PxWeb portable but ~5 dimensions Census-2023-snapshot-only; no birth-country detail |
| **Serbia** | WCF JSON, no server-side filtering; ~688 indicator codes need scraping; no joint 1-yr age × sex |
| **Indonesia** | BPS WebAPI free + JSON, but key required, multi-step ID lookup chain, bespoke schema |
| **Vietnam** | PxWeb but uptime concerns + sparser cross-tabs; gated microdata |
| **Singapore** | Proprietary row/column JSON; rigid pre-aggregated M-tables; urbanization N/A (drop dimension) |
| **Taiwan** | Bulk XML/PC-Axis (not JSON-stat); ROC SIC↔ISIC bridge; PDF for housing/parental |
| **Malaysia** | 4 req/min ceiling forces Parquet-first; ~7/16 dimensions absent from open API |
| **UAE** | SDMX 2.1 (not PxWeb); 5-yr ages; nationality split dropped post-2020; deciles only as bands |
| **Saudi Arabia** | KAPSARC/RCRC Opendatasoft + data.gov.sa CKAN; no PxWeb cross-tab; deciles ✗; parental structure ✗ |
| **Israel** | Bespoke time-series schema; subject codes not enumerated; Census 2022 has no API; mandatory User-Agent |
| **Turkey** | SDMX 2.1 REST, 13/16 ✓; no SILC decile dataflow; no housing-tenure dataflow; Turkish-only IDs |
| **Argentina** | Three distinct stacks needed (Series API + Redatam SPC + EPH FTP); no PxWeb |
| **Chile** | OECD .Stat (not PxWeb); no documented JSON-stat REST; Redatam SPC for census |
| **Colombia** | DANE REDATAM (HTML/XLS); GEIH bulletins as PDF; microdata gated; no JSON-stat |
| **Peru** | REDATAM HTML + ENAHO microdata ZIPs; no PxWeb; HTTP-only host; Spanish docs |

**Tier 4 — LOW feasibility (not viable today):**
| Country | Reason |
|---|---|
| South Africa | No public REST API; SuperWEB2 interactive; Census 2022 withdrew 4 dimensions Aug 2024 |
| **Ukraine** | No census since 2001; war-disrupted estimates; 6/16 dimensions missing outright (tenure, birth-location group, birth-country detail, parental structure, full DEGURBA, etc.) |
| **China** | Reverse-engineered EasyQuery JSON; foreign-IP geo-blocks; only quintiles (no deciles); working hours, birth-country, joint age×sex×edu unavailable via API |
| **Thailand** | No PxWeb-equivalent; data.go.th CKAN + statbbi PDFs; LFS microdata only at IHSN/ILO |
| **Pakistan** | Zero programmatic API — PDFs, Excel, Stata bundles only; microdata gated by paper Data Request + treasury fee |
| **Bangladesh** | NADA microdata catalog only; HTTP-only and intermittently unreachable; PDF/Excel-only aggregates |
| **Iran** | No machine-readable API; XLSX/PDF only; geo-blocking; sanctions chill third-party tooling; Persian-only labels |
| **Nigeria** | No first-party API; Knoema third-party mirror; 2006 census is the latest (2023 postponed indefinitely) |
| **Kenya** | No first-party API; Knoema/KeNADA fallback; aggregates locked in PDF/Excel |
| **Egypt** | No native CAPMAS API; Knoema gated by App ID/Secret; HIECS public release only 50% sample |
| **Morocco** | data.gov.ma CKAN + HCP XLSX; no cube query API; RGPH 2024 published primarily as Apache Superset dashboards |
| **Ethiopia** | No first-party machine-readable API; latest census 2007 (~19 years); Knoema third-party only |
| **Tanzania** | Knoema mirror in decline (CRAN package removed; datasets vanishing); NADA microdata gated |
| **Venezuela** | INE/REDATAM domains intermittently unreachable; Censo 2011 stale; EHM publication halted ~2018; hyperinflation distorts income series |
| **Uruguay** | No PxWeb / JSON-stat; REST4Red SPC programs only; Fusion Tables "API" defunct |
| **Ecuador** | REDATAM HTML only; SPSS microdata; ENIGHUR stale (2011-12); HTTPS cert issues on multiple INEC subdomains |

### Cross-cutting findings

1. **PxWeb is much broader than Nordic.** Confirmed PxWeb installations now span Sweden, Norway, Iceland, Finland, Ireland (PxStat fork), Estonia, Latvia, Slovenia, Switzerland, Croatia, Cyprus, Albania, **Philippines (PSA OpenSTAT v1), Ghana (GSS StatsBank), Vietnam (GSO PxWeb)** — **15 of 73 jurisdictions surveyed**. SCB's `SCBPxWebClient` should be refactored into a base `PxWebClient` class that all 15 countries can subclass with just a different base URL, table-ID registry, and language map. Cyprus, Albania, and Vietnam get marked MEDIUM only because of coverage/uptime gaps, not protocol — the client itself ports cleanly.

2. **Classification crosswalks are the real porting tax.** SUN2020 → ISCED; SNI2007 → NACE Rev. 2 / NAICS / ANZSIC / KSIC / JSIC / SCIAN / NKD 2007 / KVED / EVRK / NOGA / ÖNACE / TOL / TEÁOR / CNAE / PKD / CAE / KSIC. Build a single `ClassificationMapper` module so each country only needs to declare its native codes; the synthetic-population schema stays stable. The same approach applies to ISCED education, ICSE employment status, and DEGURBA urbanisation crosswalks.

3. **Eurostat is now formally validated as the universal EU/EEA fallback.** SDMX-JSON + JSON-stat 2.0 at `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/` covers 13/16 dimensions fully and 3 partially across all 27+ member states with no auth and a single Python wrapper (`eurostat`). Greece is the clearest case where Eurostat *is* the only viable adapter (ELSTAT has no machine-readable API). Trade-offs: NUTS-3 only at 5-yr age bands (1-yr ages national-only), bilateral country-of-birth incomplete, civil status not regionalised, and demographic data publishes T+14 months vs national T+3.

4. **Adapter-required Tier-2 protocols cluster into 4 patterns (batch 3 expands the SDMX cluster substantially):**
   - **REST + JSON-STAT v2:** Denmark, Czechia, Slovakia, Japan — easiest after PxWeb (`pyjstat` reads responses directly).
   - **SDMX 2.1:** Australia, Italy, Lithuania, Luxembourg, New Zealand, Eurostat, Ukraine, **UAE (`.Stat Suite`), Turkey (NSI Web Service)** — handled by `sdmx1`/`pandasdmx` with a one-time `add_source()` per country.
   - **Country-bespoke JSON:** Spain (Tempus3), Brazil (SIDRA), Portugal (INE), Belgium (BeStat "facts"), Serbia (WCF), Netherlands (OData), **Indonesia (BPS WebAPI), Singapore (Table Builder), Israel (Time Series DataBank), Saudi Arabia (KAPSARC Opendatasoft), Malaysia (data.gov.my JSON + Parquet)** — each needs its own parser.
   - **REDATAM (Latin-American census engine):** Argentina, Colombia, Peru, Uruguay, Ecuador, Chile (Redatam-INE), Venezuela — CGI returning HTML/XLS, with optional REST4Red JSON if a CELADE-hosted layer is reachable; SPC programs (Redatam DSL) replace URL parameters. A shared `RedatamSPCClient` would be reusable across these 7.

5. **Auth-required APIs still HIGH feasibility:** Germany (Destatis registration), Japan (e-Stat appId), South Korea (KOSIS apiKey), New Zealand (ADE subscription key). Batch 3 adds **Indonesia (BPS, key per app)** and **Egypt/Nigeria/Kenya/Ethiopia/Tanzania (Knoema App ID + Secret for the third-party mirror)** — but the latter five drop to LOW because Knoema is a non-authoritative third-party with shrinking dataset coverage. The MD5-hashed file cache pattern in `config/assets/scb_cache/` absorbs the friction for first-party auth-gated APIs.

5b. **Knoema/OpenDataForAfrica is a recurring African fallback that is now unreliable.** Five batch-3 countries (Nigeria, Kenya, Egypt, Ethiopia, Tanzania) have *only* the Knoema mirror as a programmatic surface. The Knoema platform is in maintenance/decline (CRAN R-package removed 2024; Snowflake users report dataset disappearance through 2025), so any pipeline depending on it inherits a deprecation risk. Pre-existing precedent: Mexico's `inegi.gob.mx` historically also relied on a similar bridge.

6. **Sample-survey vs register-based gap.** Sweden, Denmark, Finland, Norway, Estonia, Latvia, Lithuania, Slovenia use register-based statistics (every resident; minimal sampling error). USA, UK, Australia, India, Greece (LFS-derived), Croatia, Cyprus, Albania, Bulgaria, Romania, Serbia rely on sample surveys (ACS/APS/Census-banded/PLFS/EU-SILC/HBS) — the synthetic-population sampler may need an explicit "sample noise" floor on derived distributions for these countries.

7. **Census-vintage dependency now spans 25+ jurisdictions and ranges from 2024 to 2007.** The list grows after batch 3: Albania (2023), Croatia (2021), Cyprus (2021), Romania (2021), Slovakia (2021), Ireland (2022), Australia (2021), New Zealand (2023, last classical census), **plus Saudi Arabia (2022), Indonesia (2020 SP2020), Vietnam (2019), Pakistan (2023), Egypt (2017), Iran (2016), Argentina (2022), Uruguay (2023), Chile (2024), Peru (2017), Ecuador (2022), Tanzania (2022), Ghana (2021), Singapore (2020), Malaysia (2020), Philippines (2020 CPH), Venezuela (2011 — extreme, ~14 years stale), Nigeria (2006 — extreme, ~20 years stale, 2023 census postponed indefinitely), Ethiopia (2007 — extreme, ~19 years stale, 4th census just enumerated April 2026 with no results yet), India (2011 — 2021/2027 still pending)**. The pipeline should expose a `census_vintage_year` per country so personas inherit the correct snapshot date.

8. **Region-resolution skew.** Several smaller jurisdictions are 1 NUTS-2 country (Cyprus, Luxembourg, Malta, **Singapore (100% urban — drop urbanization dimension entirely), UAE (mostly urban)**) or have only a handful of NUTS-3 units (Iceland, Estonia, Latvia, Slovenia 12). The chained sampler's "region" stage may need to skip regional conditioning for these countries, or fall back to municipalities.

9. **Geopolitical exclusions, geo-blocks, and publication disruptions.** Serbia excludes Kosovo since 1999. Ukraine excludes Crimea (2014) and parts of Donetsk/Luhansk/Zaporizhzhia/Kherson (2022). South Africa's Census 2022 withdrew 4 dimensions Aug 2024. India's 2021 Census now scheduled for 2027. **Batch 3 adds five more disruption modes:** (a) China's NBS EasyQuery is widely reported to geo-block foreign IPs ("reverse Great Firewall"); (b) Iran's amar.org.ir is intermittently unreachable from non-Iranian IPs and US sanctions chill third-party tooling; (c) Venezuela's INE/REDATAM domains were unreachable during research, EHM publication halted ~2017–2018, and ~7.9M emigration distorts denominator; (d) Russia is conspicuously absent from the candidate pool given sanctions and the Rosstat geo-blocking pattern (not surveyed); (e) Ethiopia's Tigray region is excluded from ESPS panels post-2020 conflict. The pipeline should record per-country footnotes for these caveats.

10. **The 7-country REDATAM cluster is the dominant Latin-American pattern.** Argentina, Chile, Colombia, Peru, Ecuador, Uruguay, and Venezuela all gate census micro-aggregation behind CELADE's Redatam engine — either via the original CGI HTML interface (`RpWebEngine.exe`) or the newer REST4Red JSON wrapper. Two viable strategies: (a) build a `RedatamSPCClient` that POSTs SPC programs and parses HTML/JSON, or (b) download `.dicx` / `.rxdb` files locally and use `pachadotdev/open-redatam` (C++/R/Python) to run queries offline. Strategy (b) is more reliable but breaks the live-API constraint of the project; strategy (a) preserves the live model but requires more bespoke parsing per country. None of these countries publishes a PxWeb-equivalent.

### Current recommended pilot

**Norway (SSB)** remains the strongest first pilot:
- Identical PxWeb v2 protocol (co-developed with SCB)
- Full coverage of all 16 dimensions
- No auth, well-documented in English
- Mature Python wrappers (`pxweb`, `pyjstat`, official `dapla-statbank-client`)
- Cultural/linguistic proximity to Sweden — clinical/demographic concepts translate directly

This validates the abstraction (does the PxWeb client cleanly accept a different base URL + language map?) before tackling the Tier-2 adapter work.

### Next-up Tier-1 candidates (after Norway proves the abstraction)

If the Norway pilot succeeds, the recommended ordering for the next Tier-1 ports is:

| # | Country | Rationale |
|---|---|---|
| 1 | **Switzerland** | Best PxWeb coverage outside Nordics (15/16 ✓); 4-language (DE/FR/IT/EN); flexes `ClassificationMapper` against NOGA, NUS-3 cantons, DEGURBA grid |
| 2 | **Estonia** | Clean register-based PxWeb v1; 14/16 ✓; smallest population on this list — useful disclosure-thinning test |
| 3 | **Slovenia** | PxWeb v1 with very generous limits (10M values/call); 13/16 ✓; tests Slovenian↔English language map |
| 4 | **Latvia** | PxWeb v1; 13/16 ✓; experimental DEGURBA exposes the urbanisation crosswalk gap |
| 5 | **Croatia** | PxWeb v1 but legacy host (`web.dzs.hr`) — useful stress test for the URL/encoding layer |
| 6 | **Philippines** | PSA OpenSTAT PxWeb v1, JSON-STAT2, no auth, 11/16 ✓; first non-European Tier-1 candidate |
| 7 | **Ghana** | GSS StatsBank PxWeb, no auth, 11/16 ✓; first sub-Saharan-African Tier-1 candidate; PHC 2021 single snapshot |

These seven all reuse the refactored base `PxWebClient` and need only a country-specific table-ID registry + label mapping. Philippines and Ghana extend Tier-1 outside Europe for the first time.

### Future work

The companion plan's candidate pool is now exhausted (73 jurisdictions surveyed across 3 batches). Possible follow-ups, in order of value-vs-effort:

1. **Implement the Norway pilot.** Validates the abstraction. Issue an implementation plan in `pending/`.
2. **Design the `PxWebClient` base class + `ClassificationMapper` module** so all 15 PxWeb countries (and downstream Tier-2 adapters) share infrastructure.
3. **Build the `RedatamSPCClient`** to unlock the 7-country Latin-American REDATAM cluster as a single porting effort.
4. **Decide the Tier-4 policy.** 16 jurisdictions are LOW today; for some (China, Pakistan, Bangladesh, Iran, Venezuela) the gap is structural and unlikely to close. Decide whether the synthetic-population generator should advertise a `country in {…}` allowlist or attempt best-effort PDF/microdata fallbacks.
5. **Decide whether to survey additional jurisdictions** explicitly excluded from the candidate pool (Russia, Belarus, Cuba, North Korea, Myanmar, several smaller Pacific/Caribbean jurisdictions). All look LOW-feasibility a priori but a one-line confirmation per country would close the survey formally.
