# Web app

The designer's main interface. Run the engine and open the app:

```
spongepark serve          # then open http://127.0.0.1:8765
```

The engine serves the built app (`web/dist`) and its API from the same address. The app never
computes anything: every number comes from the engine (SWMM; the 2D model is labelled indicative).

## Pages, in working order

| Page | For |
|---|---|
| Home | Open a `.sponge` project (browse the computer, or recent ones) or create one |
| Overview | Project status and the six steps, with the next one highlighted |
| Survey | Read a DXF/DWG, assign each layer a role in a table (suggestions pre-filled, unclear layers flagged), import, quality check |
| Targets & parameters | Area budget, sizing storm, drawdown limit, least-area target; soil zones; every parameter with its source, editable, confirmable |
| Existing site | Analyse (delineation + SWMM for every storm), drainage map, where the rain goes, results table |
| Options | Generate a layout (choose component types, budget) or optimise; each option: layout, comparison, component schedule, Rhino export and import of edits |
| Storm viewer | 3D ground and 2D-model water, existing beside proposed, play/scrub, tour, litres kept (SWMM) |
| Deliverables | Report (HTML/PDF) and drawings, web viewer bundle, calibration |

Links: `http://127.0.0.1:8765/?open=D:\path\park.sponge#/storm/13` opens a project at hour 13 of the
storm viewer.

## Design system: Organic / Natural

Warm, tactile and calm: rice-paper background with a fixed grain overlay (4 %, multiply), moss and
terracotta, Fraunces (soft axis) for headings and Nunito for text, pill controls, asymmetric rounded
cards, tinted shadows, slow eased motion.

- **Tokens** live in one place, `web/src/styles/tokens.css` (colours as RGB channels, shadows,
  blob shapes, easing). `tailwind.config.js` reads them; components never use raw colour values.
  Terracotta text uses a deepened `clay-ink` token so small text keeps 4.5:1 contrast.
- **Components** (`web/src/components/ui`): `Button` (primary, clay, outline, ghost, danger; pill;
  lifts on hover, presses on click), `Card` (six asymmetric shapes cycled by index, optional lift,
  paper/stone/sand/moss tones), `Field`/`Input`/`Select`/`Chip`/`Segmented`, and `Bits`
  (badges, source badges, notices, stats, icon boxes, blobs, page header, data table, job status).
- **Accessibility:** labelled controls, focus rings in moss, 48 px targets, `aria` roles on
  segmented controls and chips, reduced-motion respected, charts with text equivalents.

## Developing

```
cd web
npm install
npm run dev        # http://localhost:5173, API proxied to the engine on 8765
npm run build      # writes web/dist, which the engine serves
```
