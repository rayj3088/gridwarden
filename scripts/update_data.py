"""
Refresh data/state_electricity.json from EIA's free bulk download (no key needed).

Uses monthly state data to build a trailing 12-month picture for every state
and DC: retail sales (GWh), average retail price (cents/kWh, weighted by
sales) and net generation (GWh). Standard library only.

Source: https://www.eia.gov/opendata/bulk/ELEC.zip (series ELEC.SALES.<ST>-ALL.M,
ELEC.PRICE.<ST>-ALL.M, ELEC.GEN.ALL-<ST>-99.M).

Run:  python scripts/update_data.py
Exit codes: 0 = file updated, 3 = nothing new, 1 = error or failed checks.
"""
import io, json, os, sys, tempfile, urllib.request, zipfile
from datetime import date

URL = os.environ.get("EIA_BULK_URL", "https://www.eia.gov/opendata/bulk/ELEC.zip")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "state_electricity.json")
STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
          "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
MONTHS = "January February March April May June July August September October November December".split()


def wanted():
    w = {}
    for st in STATES:
        w[f"ELEC.SALES.{st}-ALL.M"] = (st, "sales")
        w[f"ELEC.PRICE.{st}-ALL.M"] = (st, "price")
        w[f"ELEC.GEN.ALL-{st}-99.M"] = (st, "gen")
    return w


def load_series():
    want, found = wanted(), {}
    with tempfile.TemporaryFile() as tmp:
        with urllib.request.urlopen(URL, timeout=300) as r:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                tmp.write(chunk)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
            with z.open(name) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8"):
                    if '"series_id"' not in line:
                        continue
                    sid_at = line.find('"series_id"')
                    sid = line[sid_at:sid_at + 80].split('"')[3]
                    if sid not in want:
                        continue
                    rec = json.loads(line)
                    vals = {}
                    for period, v in rec.get("data") or []:
                        try:
                            vals[str(period)] = float(v)
                        except (TypeError, ValueError):
                            pass
                    found[want[sid]] = vals
    return found


def month_list(end, n=12):
    y, m = int(end[:4]), int(end[4:])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def main():
    try:
        s = load_series()
    except Exception as e:  # network, zip or format problem
        print(f"Could not read the EIA bulk file: {e}")
        return 1
    missing = [f"{st} {k}" for st in STATES for k in ("sales", "price", "gen") if (st, k) not in s]
    if missing:
        print(f"Series missing from the bulk file ({len(missing)}), e.g. {missing[:5]}. EIA may have renamed them.")
        return 1

    # Latest month for which all 51 areas have 12 full months of all three series.
    candidates = sorted(set(s[("VA", "sales")]), reverse=True)
    end = None
    for cand in candidates[:24]:
        ms = month_list(cand)
        if all(m in s[(st, k)] for st in STATES for k in ("sales", "price", "gen") for m in ms):
            end = cand
            break
    if not end:
        print("No recent 12-month window has complete data for all 51 areas.")
        return 3
    ms = month_list(end)

    states = {}
    for st in STATES:
        sales = sum(s[(st, "sales")][m] for m in ms)                       # million kWh = GWh
        price = sum(s[(st, "price")][m] * s[(st, "sales")][m] for m in ms) / sales
        gen = sum(s[(st, "gen")][m] for m in ms)                             # thousand MWh = GWh
        states[st] = {"sales_gwh": round(sales, 1), "price_cents_kwh": round(price, 2), "generation_gwh": round(gen, 1)}

    start = ms[-1]
    label = f"12 months through {MONTHS[int(end[4:]) - 1]} {end[:4]}"
    problems = []
    try:
        old = json.load(open(OUT))
    except (OSError, ValueError):
        old = {"states": {}}
    if old.get("period_end", "") >= end:
        print(f"Already current ({old.get('period_label')}).")
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

    new = {"schema_version": 2, "year": int(end[:4]), "period_start": start, "period_end": end, "period_label": label,
           "updated_on": date.today().isoformat(),
           "source": f"U.S. Energy Information Administration, monthly state data ({label})",
           "source_url": "https://www.eia.gov/electricity/data/browser/", "states": dict(sorted(states.items()))}
    with open(OUT, "w") as f:
        json.dump(new, f, indent=1)
        f.write("\n")
    print(f"Updated to {label}. US retail sales {total:,.0f} GWh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
