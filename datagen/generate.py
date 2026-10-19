"""
Synthetic data generator for the Care Insights POC.

Simulates four source systems of a Support at Home provider, landing files in the
shape and format each system would actually send:

  reference/   CRM extracts (participants, workers, providers, service catalogue)  CSV
  scheduling/  rostering system bookings, one file per month                     CSV
  mobile/      worker app check-in/check-out events, one folder per day          JSON Lines
  finance/     third-party provider invoices, one file per month (AU dates)       CSV

Known problems are injected on purpose so the pipeline has something to find:
  - participants who under-spend or over-spend their quarterly budget
  - missed visits (no check-in) and late visits, plus a few chronically late workers
  - duplicate app events (mobile retry), missing check-outs
  - duplicate invoices, invoices above the price cap, invoices for unknown participants

All people are fictitious IDs - no names or personal details.
Stdlib only. Deterministic for a given --seed.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# Illustrative annual funding per Support at Home classification (AUD).
# Close to published 2025-26 figures, but treat as sample values only.
ANNUAL_BUDGET = {1: 10731, 2: 16034, 3: 21925, 4: 29673, 5: 39793, 6: 48252, 7: 58164, 8: 78106}

# code, name, category, delivered_by, unit, price cap (AUD per unit) - illustrative
SERVICES = [
    ("PC",  "Personal care",            "Independence",   "internal", "hour", 85.0),
    ("DA",  "Domestic assistance",      "Everyday living","internal", "hour", 80.0),
    ("NUR", "Nursing care",             "Clinical",       "internal", "hour", 120.0),
    ("SOC", "Social support",           "Independence",   "internal", "hour", 78.0),
    ("AH",  "Allied health - physio",   "Clinical",       "provider", "hour", 190.0),
    ("TR",  "Transport",                "Independence",   "provider", "trip", 60.0),
    ("GM",  "Gardening & home maint.",  "Everyday living","provider", "hour", 85.0),
]
INTERNAL = [s for s in SERVICES if s[3] == "internal"]
EXTERNAL = [s for s in SERVICES if s[3] == "provider"]
CAP = {s[0]: s[5] for s in SERVICES}

REGIONS = ["Sydney Metro", "Hunter", "Illawarra", "Brisbane Metro", "Gold Coast",
           "Melbourne Metro", "Geelong", "Adelaide Metro", "Perth Metro"]


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "raw"))
    ap.add_argument("--participants", type=int, default=400)
    ap.add_argument("--workers", type=int, default=60)
    ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--as-of", default="2026-10-18", help="last day with actuals; later bookings are future")
    ap.add_argument("--end", default="2026-12-31", help="last scheduled booking")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    out = Path(a.out)
    start, as_of, end = (date.fromisoformat(x) for x in (a.start, a.as_of, a.end))
    uid = lambda: str(uuid.UUID(int=rnd.getrandbits(128)))

    # ---------------- reference data ----------------
    services = [dict(service_code=c, service_name=n, category=cat, delivered_by=by,
                     unit=u, price_cap_aud=f"{cap:.2f}") for c, n, cat, by, u, cap in SERVICES]

    providers = [dict(provider_id=f"PRV{i:03d}", provider_name=f"Provider {i:03d} Pty Ltd",
                      abn=f"{rnd.randint(10, 99)} {rnd.randint(100, 999)} {rnd.randint(100, 999)} {rnd.randint(100, 999)}",
                      service_code=rnd.choice(EXTERNAL)[0])
                 for i in range(1, 16)]
    # one provider that habitually charges above cap
    sloppy_provider = providers[3]["provider_id"]

    workers = []
    for i in range(1, a.workers + 1):
        workers.append(dict(worker_id=f"W{i:04d}", region=rnd.choice(REGIONS),
                            employment_type=rnd.choice(["full_time", "part_time", "casual"]),
                            start_date=(start - timedelta(days=rnd.randint(60, 2000))).isoformat()))
    chronic_late = {w["worker_id"] for w in rnd.sample(workers, 4)}
    workers_by_region: dict[str, list[str]] = {}
    for w in workers:
        workers_by_region.setdefault(w["region"], []).append(w["worker_id"])

    participants = []
    for i in range(1, a.participants + 1):
        level = rnd.choices(range(1, 9), weights=[10, 14, 16, 16, 14, 12, 10, 8])[0]
        r = rnd.random()
        # spending behaviour: who under- or over-uses their budget
        propensity = rnd.uniform(0.25, 0.6) if r < 0.15 else rnd.uniform(1.12, 1.4) if r > 0.87 else rnd.uniform(0.82, 1.0)
        participants.append(dict(
            participant_id=f"P{i:05d}",
            classification_level=level,
            region=rnd.choice(REGIONS),
            funding_start_date=(start - timedelta(days=rnd.randint(0, 900))).isoformat(),
            quarterly_budget_aud=f"{ANNUAL_BUDGET[level] / 4:.2f}",
            _propensity=propensity,
        ))

    # ---------------- bookings + mobile events ----------------
    bookings, events, invoices = [], [], []
    weeks = (end - start).days / 7
    for p in participants:
        qb = float(p["quarterly_budget_aud"]) * p["_propensity"]
        internal_target = qb * 0.75          # per quarter
        external_target = qb * 0.25
        # services this participant receives (higher levels get more clinical care)
        mix = ["PC", "DA", "SOC"] + (["NUR"] if p["classification_level"] >= 4 else [])
        avg_visit_cost = sum(CAP[c] for c in mix) / len(mix) * 1.5  # ~90 min average
        visits_per_week = max(1, round(internal_target / 13 / avg_visit_cost))
        region_workers = workers_by_region.get(p["region"]) or [w["worker_id"] for w in workers]
        regular = rnd.sample(region_workers, k=min(2, len(region_workers)))

        n_visits = int(visits_per_week * weeks)
        for _ in range(n_visits):
            d = start + timedelta(days=rnd.randint(0, (end - start).days))
            sched = datetime(d.year, d.month, d.day, rnd.choice([7, 8, 9, 10, 11, 13, 14, 15]), rnd.choice([0, 15, 30, 45]))
            minutes = rnd.choice([60, 90, 90, 120])
            worker = rnd.choice(regular) if rnd.random() < 0.85 else rnd.choice(region_workers)
            b_id = uid()
            bookings.append(dict(booking_id=b_id, participant_id=p["participant_id"], worker_id=worker,
                                 service_code=rnd.choice(mix), scheduled_start=sched.strftime("%Y-%m-%d %H:%M:%S"),
                                 scheduled_minutes=minutes,
                                 status="scheduled", created_at=(sched - timedelta(days=rnd.randint(3, 40))).strftime("%Y-%m-%d %H:%M:%S")))
            if d > as_of:
                continue  # future visit - no actuals yet
            if rnd.random() < 0.04:
                continue  # missed visit: worker never checked in
            late_p = 0.35 if worker in chronic_late else 0.07
            delay = rnd.randint(16, 75) if rnd.random() < late_p else max(-10, int(rnd.gauss(2, 5)))
            check_in = sched + timedelta(minutes=delay, seconds=rnd.randint(0, 59))
            check_out = check_in + timedelta(minutes=int(minutes * rnd.uniform(0.85, 1.05)))
            ev_in = dict(event_id=uid(), booking_id=b_id, worker_id=worker, event_type="check_in",
                         event_ts=check_in.isoformat(), gps_verified=rnd.random() < 0.97, app_version="4.2.1")
            events.append(ev_in)
            if rnd.random() < 0.01:
                events.append(dict(ev_in))  # mobile retry: same event_id sent twice
            if rnd.random() > 0.02:  # 2% of visits never get a check-out
                events.append(dict(event_id=uid(), booking_id=b_id, worker_id=worker, event_type="check_out",
                                   event_ts=check_out.isoformat(), gps_verified=rnd.random() < 0.97, app_version="4.2.1"))

        # ---------------- third-party invoices (only up to as_of) ----------------
        ext_daily = external_target / 91
        d = start
        while d <= as_of:
            d += timedelta(days=rnd.randint(7, 21))
            if d > as_of:
                break
            svc = rnd.choice(EXTERNAL)
            prov = rnd.choice([pv for pv in providers if pv["service_code"] == svc[0]] or providers)
            target = ext_daily * rnd.uniform(10, 18)
            units = max(1.0, round(target / svc[5] * 2) / 2)  # half-unit steps
            rate = svc[5] if rnd.random() < 0.7 else round(svc[5] * rnd.uniform(0.85, 1.0), 2)
            if prov["provider_id"] == sloppy_provider and rnd.random() < 0.5 or rnd.random() < 0.02:
                rate = round(svc[5] * rnd.uniform(1.08, 1.35), 2)  # above price cap
            received = d + timedelta(days=rnd.randint(2, 20))
            inv = dict(invoice_number=f"INV-{rnd.randint(100000, 999999)}", provider_id=prov["provider_id"],
                       participant_id=p["participant_id"], service_code=svc[0],
                       service_date=d.strftime("%d/%m/%Y"),  # AU format, as providers send it
                       units=f"{units:.1f}", unit_rate=f"{rate:.2f}", amount_aud=f"{units * rate:.2f}",
                       received_date=min(received, as_of).strftime("%d/%m/%Y"))
            invoices.append(inv)
            if rnd.random() < 0.015:  # provider resubmits the same invoice
                dup = dict(inv, invoice_number=f"INV-{rnd.randint(100000, 999999)}",
                           received_date=min(received + timedelta(days=rnd.randint(5, 25)), as_of).strftime("%d/%m/%Y"))
                invoices.append(dup)

    # invoices for participants we don't know about
    for _ in range(6):
        svc = rnd.choice(EXTERNAL)
        d = start + timedelta(days=rnd.randint(0, (as_of - start).days))
        invoices.append(dict(invoice_number=f"INV-{rnd.randint(100000, 999999)}", provider_id=rnd.choice(providers)["provider_id"],
                             participant_id=f"P{rnd.randint(90000, 99999)}", service_code=svc[0],
                             service_date=d.strftime("%d/%m/%Y"), units="2.0", unit_rate=f"{svc[5]:.2f}",
                             amount_aud=f"{2 * svc[5]:.2f}", received_date=d.strftime("%d/%m/%Y")))

    # ---------------- write files ----------------
    for p in participants:
        p.pop("_propensity")
    write_csv(out / "reference" / "participants.csv", participants)
    write_csv(out / "reference" / "workers.csv", workers)
    write_csv(out / "reference" / "providers.csv", providers)
    write_csv(out / "reference" / "service_types.csv", services)

    by_month: dict[str, list] = {}
    for b in sorted(bookings, key=lambda x: x["scheduled_start"]):
        by_month.setdefault(b["scheduled_start"][:7].replace("-", ""), []).append(b)
    for m, rows in by_month.items():
        write_csv(out / "scheduling" / "bookings" / f"bookings_{m}.csv", rows)

    by_day: dict[str, list] = {}
    for e in events:
        by_day.setdefault(e["event_ts"][:10], []).append(e)
    for dstr, rows in sorted(by_day.items()):
        y, mth, dd = dstr.split("-")
        pth = out / "mobile" / "visit_events" / y / mth / dd / "events.jsonl"
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    inv_by_month: dict[str, list] = {}
    for inv in invoices:
        dd, mm, yy = inv["received_date"].split("/")
        inv_by_month.setdefault(f"{yy}{mm}", []).append(inv)
    for m, rows in sorted(inv_by_month.items()):
        write_csv(out / "finance" / "invoices" / f"invoices_{m}.csv", rows)

    print(f"participants={len(participants)} workers={len(workers)} bookings={len(bookings)} "
          f"events={len(events)} invoices={len(invoices)} -> {out}")
    print(f"chronically late workers (ground truth): {sorted(chronic_late)}; over-cap provider: {sloppy_provider}")


if __name__ == "__main__":
    main()
