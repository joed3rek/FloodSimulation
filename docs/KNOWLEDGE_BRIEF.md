# TASK: NBS KNOWLEDGE BASE AND INTERVENTION INTELLIGENCE

(Brief given by the project owner on 2026-10-20. Governs `knowledge/`, `spongepark/engine/knowledge/` and
`spongepark/engine/intel/`. Read with `docs/BRIEF.md`.)

## Goal
Build two connected modules in the spongepark engine:

A. Knowledge acquisition: download the open reference documents and datasets listed
   below, extract design rules and parameters with full provenance, and store them as
   a reviewed, versioned rule base.
B. Intervention intelligence: learn WHICH nature-based solution to use, WHERE on a
   site, WHEN (under which conditions and storms, and in what order in a treatment
   train) and HOW (sizing, geometry, outlets, media, planting, maintenance), using
   the rule base as hard limits and learned models to rank and propose.

Scope: urban settings worldwide. Not tied to any one country. Regional rule packs
(for example India) are optional add-ons.

## Non-negotiable principles
1. Copyright and terms. Download only documents and datasets that are openly
   published by their owner. Never bypass paywalls, logins or robots.txt. Paid or
   restricted documents are listed as "user-supplied": the engine asks the user for a
   local copy. Raw downloads are stored in a git-ignored folder and never committed
   or redistributed. Only extracted facts (numbers, ranges, rules) with citations are
   committed.
2. Provenance on every rule. Each extracted value records: document id, edition,
   page or section, a short verbatim snippet (under 15 words) for verification,
   extraction method, date, and review status.
3. Human review. Extracted rules start as "unreviewed". Only "approved" rules drive
   design checks. Provide a review screen in the app and a CLI command.
4. Conflicts are kept, not averaged. When sources disagree, store each value with
   its source and climate context; the engine shows the range and which source
   applies.
5. Rules constrain, learning ranks. Learned models never override an approved rule
   (safety depth, setback, drawdown, groundwater separation). They only rank and
   propose options that already satisfy the rules.
6. Explainability. Every recommendation states: the rules that allowed it, the
   evidence (simulation, monitoring data, precedent) behind its ranking, and the
   model's confidence.
7. SWMM remains the source of truth for performance numbers.
8. Climate transfer. Geometry, safety and maintenance rules transfer between
   climates; sizing always uses the project's own design storms. Every rule records
   the climate context of its source.

## Part A: Knowledge acquisition

### A1. Source registry
Create `knowledge/sources.yaml`. Each entry: id, title, publisher, edition/year,
url, kind (manual, standard, dataset, catalogue, paper), access (open,
user-supplied, metadata-only), licence note, climate context, elements covered,
priority. Start with the entries below. Before downloading, open each landing page,
confirm the document is openly offered by its owner, and record the licence or terms
text. If a URL has moved, search the owner's own site for the current location and
record the new URL. Never use third-party mirrors for documents whose owner does not
offer them openly.

Design manuals (open, verify on download):
- pub_abc_waters: PUB Singapore, ABC Waters Design Guidelines and Engineering
  Procedures (2018), plus design calculation templates for vegetated swales,
  bioretention swales and bioretention basins.
  https://pub.gov.sg/Professionals/Working-on-ABC-Waterways/ABC-Waters-Design-Guidelines
  https://info.pub.gov.sg/Documents/Condensed_Booklet_of_Engin_Procedures.pdf
  https://info.pub.gov.sg/Documents/Details_of_ABC_Waters_Certification_Criteria.pdf
- phila_gsi: Philadelphia Water, GSI Planning and Design Manual v3.1 (Dec 2024)
  https://water.phila.gov/pool/files/gsi-planning-and-design-manual.pdf
- phila_smgm: Philadelphia Water, Stormwater Management Guidance Manual v3.3
  https://water.phila.gov/pool/files/stormwater-management-guidance-manual.pdf
  https://water.phila.gov/development/manual
- mn_manual: Minnesota Stormwater Manual (web pages per practice)
  https://stormwater.pca.state.mn.us/
- trca_lid: TRCA / CVC Low Impact Development Planning and Design Wiki
  https://wiki.sustainabletechnologies.ca
- nacto_ussg: NACTO Urban Street Stormwater Guide (web)
  https://nacto.org/publication/urban-street-stormwater-guide/
- seq_wsud: Water Sensitive Urban Design Technical Design Guidelines (South East
  Queensland councils, based on Brisbane and Melbourne Water)
  https://www.redland.qld.gov.au/download/downloads/id/1406/wsud_technical_design_guidelines.pdf
- townsville_wsud: WSUD guidelines for the coastal dry tropics (Townsville)
  https://www.townsville.qld.gov.au/__data/assets/pdf_file/0009/12222/GUIDELINES_1_Introduction_FINAL.pdf
- cgwb_recharge: Central Ground Water Board (India), Manual on Artificial Recharge
  of Ground Water (regional pack, recharge structures)
  https://www.cgwb.gov.in/cgwbpnm/publication-detail/330

Design manuals (user-supplied; do not download):
- ciria_c753: CIRIA, The SuDS Manual C753 (2015) and C768 construction guide.
- melbourne_wsud: Melbourne Water / CSIRO, WSUD Engineering Procedures: Stormwater
  (2005). Published book; ask the user for a copy unless the owner offers it openly.
- msma2 / ms2526: Malaysia MSMA 2nd Edition and MS 2526 parts (detention ponds,
  on-site detention, bioretention, infiltration).
- mohurd_sponge: China MOHURD Technical Guide for Sponge City Construction (2014)
  and GB/T 51345-2018.

Model references (open):
- swmm_ref: US EPA SWMM 5 Reference Manual Vol I (Hydrology), Vol II (Hydraulics),
  Vol III (Water Quality and LID, Chapter 6), and the SWMM 5 User's Manual. Download
  from epa.gov only.
- tr55: NRCS TR-55 (already in the engine; register it).

Performance evidence (open):
- bmp_db_2020: International Stormwater BMP Database, 2020 Summary Statistics
  (Water Research Foundation)
  https://www.waterrf.org/serve-file/resource/DRPT-4968.pdf
  Also the BMP Database itself where its terms allow download.

Catalogues and frameworks (open):
- wb_nbs_catalogue: World Bank, A Catalogue of Nature-based Solutions for Urban
  Resilience (2021)
  https://openknowledge.worldbank.org/entities/publication/c33e226c-2fbb-5e11-8c21-7b711ecbc725
- iucn_standard: IUCN Global Standard for NbS (2020), 8 criteria, 28 indicators
  https://iucn.org/node/31866
- una: Urban Nature Atlas (https://una.city): metadata-only. Do not scrape; the
  full database is available on request from its owners. Store case references the
  user adds manually.

Built-project datasets (open data; record each licence):
- nyc_dep_gi: NYC DEP Green Infrastructure (practices: location, program, status,
  type), monthly updates. GeoJSON exports, for example:
  https://data.cityofnewyork.us/api/v3/views/fm4z-qud6/query.geojson?accessType=DOWNLOAD
  https://data.cityofnewyork.us/api/v3/views/drep-uzs7/query.geojson?accessType=DOWNLOAD
  and the main dataset https://data.cityofnewyork.us/d/spjh-pz7h
- nyc_greenstreets: NYC Parks Greenstreets https://data.cityofnewyork.us/d/mk9u-qu7i
- phila_gsi_public: Green Stormwater Infrastructure Public Projects (catalog.data.gov)
- phila_gsi_private: GSI Private Projects, regulation and retrofit (CSV/GeoJSON)
  https://opendataphilly.org/datasets/green-stormwater-infrastructure-private-projects
- phila_gsi_parcels: GSI Planning Parcels (impervious cover by surface type)
  https://opendataphilly.org/datasets/green-stormwater-infrastructure-gsi-planning-parcels
Context layers for these cities (DEM, land cover, soils, imperviousness) must also
come from official open sources; find and register them, with licences.

Methods literature (metadata-only unless open access; for design of Part B):
- IDEAS_GI: SWMM + noisy genetic algorithm + neural network surrogate + decision
  trees for GI coverage (Heidari Haratmeh, Illinois; EGU23-10670)
- Dong, Subramanyam, Wu (2025): deep learning UNet surrogates for spatially explicit
  GI optimisation
- Tebyanian et al. (2023): Rhodium-SWMM, open-source GI placement under deep
  uncertainty (Environ. Model. Softw.) - inspect its code if openly licensed
- MLP surrogate for LID facility area optimisation (Water Resources Management, 2023)

### A2. Downloader
- `spongepark knowledge fetch [--source id] [--all]`
- Polite fetching: identify the client, rate-limit, respect robots.txt, retry with
  backoff, resume partial downloads.
- Store raw files in `knowledge/raw/<source_id>/` (git-ignored) with a
  `fetch.json` (url, final url, date, http status, sha256, size, licence text).
- Web manuals (Minnesota, TRCA, NACTO): save the relevant pages per practice as
  HTML snapshots, not whole sites.
- `spongepark knowledge add --source id --file path` registers a user-supplied copy.
- `spongepark knowledge status` lists each source: fetched, missing, user-supplied
  needed, failed (with reason).
- On failure, do not try alternative hosts for restricted documents; report it.

### A3. Extraction
- Text and layout: PyMuPDF; tables: pdfplumber or camelot; HTML: BeautifulSoup.
- Build a page-indexed text store per document for search.
- Extract per element, into a staging file `knowledge/staging/<source>.jsonl`:
  parameter, value or range, unit, condition (when it applies), element type,
  page/section, snippet, climate context, confidence.
- Parameters to target for every element (see A5 schema): siting limits (slope,
  setbacks, depth to groundwater/rock, contributing area, soil infiltration range),
  geometry (depths, widths, side slopes, lengths), media (depth, mix, infiltration
  rate), storage and drawdown, inlets, pretreatment, outlets and overflow, planting,
  safety (ponding limits, fencing, edge benching), construction, maintenance
  (tasks, frequency), performance (volume, peak, pollutants), costs.
- Use your own reading of the document for extraction where tables are irregular,
  but every value must point to a page and snippet a human can verify.
- Unit normalisation to SI with the original value kept.

### A4. Review and versioned rule base
- `knowledge/rules/<element>.json`: approved rules only, committed to git.
- Review flow: CLI `spongepark knowledge review` and an app screen showing each
  staged rule beside its source snippet and page; Approve, Edit, Reject.
- Conflicts: same parameter from different sources is stored as separate entries;
  a `preferred` flag per project or region chooses which applies.
- Versioning: each approved rule has an id and version; project files record which
  rule-base version they used.
- The existing `guidelines.json` is migrated into this structure without loss.

### A5. Element schema
One schema per element type, shared by rules, simulation and learning:
rain_garden / bioretention_basin, bioswale / bioretention_swale, vegetated_swale,
filter_strip, tree_pit / tree_trench, infiltration_trench, soakaway /
recharge_well, permeable_pavement, green_roof, rainwater_harvesting,
detention_basin (dry), retention_pond (wet), constructed_wetland, check_dam,
depave (impervious removal).
Each schema lists: functions (volume, peak, quality, recharge, conveyance,
amenity, biodiversity, cooling), siting constraints, design parameters, SWMM
representation (LID type or storage node) and its parameter mapping (EPA SWMM
Vol III Ch. 6), maintenance profile, cost fields, co-benefit fields.

## Part B: Intervention intelligence (which, where, when, how)

### B1. Definitions
- WHICH: the set and mix of element types suited to a site and objective.
- WHERE: cells or zones on the site where each type is suitable, ranked.
- WHEN: the conditions under which each type is used: storm regime (frequent small
  storms versus rare large ones), position in the treatment train (source, conveyance,
  site, regional), and dependencies (pretreatment before infiltration, detention after
  bioretention for peaks).
- HOW: sizing, geometry, outlet and overflow, media, planting palette fields,
  maintenance plan.

### B2. Site and context features (input to every model)
Per cell and per site: slope, flow accumulation, contributing area and its
imperviousness, soil infiltration rate and group, depth to groundwater and rock,
land use and ownership, available open space, distance to buildings and utilities,
existing trees and paths, public access and safety class, design-storm depths and
intensities, objective weights (volume, peak, quality, recharge, amenity,
biodiversity, cost), maintenance capacity.

### B3. Expert rule layer (first, deterministic)
- A decision matrix built from approved rules: for each element, the feasible
  ranges of B2 features, its functions, and train position.
- Output per site: feasible element types per cell, with reasons for exclusions.
- This layer alone must produce a sensible proposal. Learned layers improve it.

### B4. Learned layers
1. Performance surrogate (exists; extend): trained on SWMM runs; predicts volume
   retained, peak reduction, drawdown and overflow for any layout. Now trained across
   many sites, not one.
2. Synthetic site generator: procedurally generate thousands of urban sites varying
   slope, soils, imperviousness, building and street layout, groundwater depth,
   rainfall regime (temperate, tropical, monsoon; use published IDF shapes) and
   space limits. Run the rule layer, the optimiser and SWMM on each. Store site
   features, chosen layouts, Pareto fronts and outcomes in `knowledge/train/`.
3. Selection model (WHICH and WHEN): learns from the optimiser's best layouts on
   synthetic sites to map site features and objectives to an element mix and train
   order. Start with gradient boosting and a decision tree export for
   explainability; report feature importance.
4. Siting model (WHERE): learns cell-level suitability.
   - From synthetic optimal layouts (labels = cells chosen by the optimiser).
   - From built-project inventories (NYC, Philadelphia): positive examples of where
     real designers placed each type. Treat as positive-unlabelled data (absence is
     not a negative). These teach practice patterns, never performance.
   - Optional later: a UNet-style spatial model on raster features.
5. Sizing model (HOW): predicts initial sizes and geometry within rule ranges from
   contributing area, storm and soil; always followed by rule checks and SWMM.
6. Designer feedback: accepted, edited and rejected proposals from edit logs become
   training signals with weights; never allowed to relax a safety rule.

### B5. Recommendation output
For each proposal: element types and counts, locations, sizes, train order, the
storms it is designed for and beyond which it overflows, the rules satisfied (with
citations), predicted performance (surrogate, then SWMM-verified), confidence, cost
and co-benefits, maintenance summary, and two alternatives with trade-offs.

### B6. Evaluation
- Hold out whole sites and whole cities (never random cells) for testing.
- Compare learned proposals against the rule-only proposal and the optimiser on
  SWMM-verified metrics.
- Precedent check: siting model scored on held-out built-project locations.
- Sanity tests: no recommendation violates an approved rule; every recommendation
  has at least one citation; surrogate error reported per metric.
- Report bias: which climates and site types the training data under-represents.

## Repository additions
```
knowledge/
  sources.yaml
  raw/            (git-ignored)
  staging/
  rules/
  train/          (git-ignored if large; manifest committed)
  reports/
spongepark/engine/knowledge/   fetch, extract, review, rules API
spongepark/engine/intel/       features, rule layer, site generator, models, recommender
```

## Phases and acceptance
| Phase | Scope | Accept when |
|---|---|---|
| K1 | Source registry, downloader, status report | All open sources fetched or reported with reason; user-supplied list shown; nothing restricted downloaded |
| K2 | Extraction to staging for 5 core elements (rain garden, bioswale, detention, retention, recharge well) | Every staged value has page and snippet; units normalised |
| K3 | Review tool, rule base, migration of guidelines.json | Approved rules drive the existing design checks |
| K4 | Remaining elements and the schema for all of them | All element schemas complete with SWMM mapping |
| I1 | Feature extraction and expert rule layer | Rule-only proposals on the pilot parks with explanations |
| I2 | Synthetic site generator and training data | At least 2,000 sites simulated; dataset manifest and coverage report |
| I3 | Selection, siting and sizing models | Beat the rule-only proposal on held-out sites; no rule violations |
| I4 | Built-project inventories in the siting model | Precedent score reported on held-out city |
| I5 | Recommender in the app with explanations and alternatives | Designer sees which, where, when, how, with citations |

Start with K1. Before fetching anything, show the registry with each source's
access status and licence note, and wait for the owner's go-ahead.
