# Contributing to Gridwarden

Gridwarden is a free, sourced map of US grid capacity and what AI data centers
mean for each state. Help is welcome.

## Ground rules

- **Every number needs a public source** with a link and a date. No estimates without
  saying so.
- **State and regional level only.** Gridwarden does not map individual grid
  infrastructure (lines, substations, fiber routes, specific plant sites) and does not
  analyze weak points. Pull requests that add that kind of detail will be declined.
- **Neutral wording.** Describe, don't judge. Say "reported" or "says" and name the
  source, especially in the watchlist. Frame comparisons between states as possibilities
  to explore, never as rankings of better or worse.

## Easy ways to help

- Report a wrong or stale number with the "Data correction" issue form.
- Add a source: add an entry to `SOURCES` in `index.html` (section 3) with `asOf` and a link.
- Improve wording in the state cards so they read clearly to anyone.

## How data stays current

`data/state_electricity.json` is rebuilt monthly from EIA's free bulk download by
`.github/workflows/update-data.yml`, which opens a pull request for review. You can run
it yourself: `python scripts/update_data.py`.

## Code

Everything is in one file, `index.html`, with no build step. Open it in a browser to
test. Keep it working when the optional map libraries fail to load.
