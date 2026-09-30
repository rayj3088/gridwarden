"""
Refresh data/state_electricity.json from the EIA API (v2).

Pulls, for every state and DC, the most recent year that EIA has published
in full: retail sales (GWh), average retail price (cents/kWh) and net
generation (GWh). Standard library only.

Run:  EIA_API_KEY=... python scripts/update_data.py
Exit codes: 0 = file updated, 3 = nothing new, 1 = error or failed checks.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import date

BASE = os.environ.get("EIA_BASE", "https://api.eia.gov/v2")
KEY = os.environ.get("EIA_API_KEY", "")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "state_electricity.json")
STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
          "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()


def get(route, params):
    q = [("api_key", KEY), ("frequency", "annual"), ("length", "5000"),
         ("sort[0][column]", "period"), ("sort[0][direction]", "desc")] + params
    url = f"{BASE}/{route}/data/?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=60) as r:
        body = json.load(r)
    rows = (body.get("response") or {}).get("data")
    if not isinstance(rows, list):
        raise RuntimeError(f"{route}: unexpected response")
    return rows


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def by_year(rows, state_key, fields):
    out = {}
    for r in rows:
        st, yr = r.get(state_key), str(r.get("period", ""))[:4]
        if st not in STATES or not yr.isdigit():
            continue
        vals = {f: num(r.get(f)) for f in fields}
        if any(v is None for v in vals.values()):
            continue
        out.setdefault(int(yr), {})[st] = vals
    return out


def main():
    if not KEY:
        print("EIA_API_KEY is not set.")
        return 1
    start = str(date.today().year - 4)
    sales = by_year(get("electricity/retail-sales",
                        [("data[0]", "sales"), ("data[1]", "price"), ("facets[sectorid][]", "ALL"), ("start", start)]),
                    "stateid", ["sales", "price"])
    gen = by_year(get("electricity/electric-power-operational-data",
                      [("data[0]", "generation"), ("facets[sectorid][]", "99"), ("facets[fueltypeid][]", "ALL"), ("start", start)]),
                  "location", ["generation"])
    years = [y for y in sorted(set(sales) & set(gen), reverse=True)
             if len(sales[y]) == len(STATES) and len(gen[y]) == len(STATES)]
    if not years:
        print("No year has complete data for all 51 areas yet.")
        return 3
    year = years[0]

    states = {st: {"sales_gwh": round(sales[year][st]["sales"], 1),      # million kWh = GWh
                   "price_cents_kwh": round(sales[year][st]["price"], 2),
                   "generation_gwh": round(gen[year][st]["generation"], 1)}  # thousand MWh = GWh
              for st in STATES}

    # Sanity checks against the current file. Big jumps stop the update so a person looks first.
    problems = []
    try:
        old = json.load(open(OUT))
    except (OSError, ValueError):
        old = {"year": 0, "states": {}}
    if year < old.get("year", 0):
        print(f"API's latest complete year ({year}) is older than the file ({old['year']}). Leaving it.")
        return 3
    for st, v in states.items():
        if not (0 < v["price_cents_kwh"] < 100):
            problems.append(f"{st}: price {v['price_cents_kwh']} out of range")
        if v["sales_gwh"] <= 0 or v["generation_gwh"] <= 0:
            problems.append(f"{st}: zero or negative value")
        o = old["states"].get(st)
        if o:
            for k in ("sales_gwh", "generation_gwh"):
                if o[k] and abs(v[k] / o[k] - 1) > 0.5:
                    problems.append(f"{st}: {k} changed by more than 50% ({o[k]} -> {v[k]})")
    total = sum(v["sales_gwh"] for v in states.values())
    if not (3_000_000 < total < 6_000_000):
        problems.append(f"US retail sales total {total:,.0f} GWh looks wrong")
    if problems:
        print("Checks failed; not writing:\n  " + "\n  ".join(problems))
        return 1

    new = {"schema_version": 1, "year": year, "updated_on": date.today().isoformat(),
           "source": f"U.S. Energy Information Administration, EIA API v2 ({year} data)",
           "source_url": "https://www.eia.gov/electricity/state/", "states": dict(sorted(states.items()))}
    if old.get("year") == year and old.get("states") == new["states"]:
        print(f"No change ({year} data already in the file).")
        return 3
    with open(OUT, "w") as f:
        json.dump(new, f, indent=1)
        f.write("\n")
    print(f"Updated to {year} data. US retail sales {total:,.0f} GWh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
