"""Exports compact aggregates of the gold tables for the static showcase page."""
import json, duckdb
g = lambda t: f"'data/lake/gold/{t}.parquet'"
con = duckdb.connect()
def rows(sql):
    cur = con.execute(sql); cols = [d[0] for d in cur.description]
    return [dict(zip(cols, [v.isoformat() if hasattr(v, 'isoformat') else v for v in r])) for r in cur.fetchall()]
out = {}
out["quarters"] = rows(f"select quarter, any_value(is_closed) closed, count(*) participants, round(sum(budget_aud)) budget, round(sum(spend_to_date_aud)) spend, round(sum(forecast_spend_aud)) forecast, round(sum(est_funds_lost_aud)) funds_lost from {g('budget_utilisation')} group by 1 order by 1")
out["budget_status"] = rows(f"select quarter, region, budget_status, count(*) n, round(sum(est_funds_lost_aud)) funds_lost from {g('budget_utilisation')} group by all order by all")
out["budget_points"] = rows(f"select participant_id id, region, classification_level lvl, round(budget_aud,2) budget, round(spend_to_date_aud,2) spend, round(forecast_spend_aud,2) forecast, round(forecast_pct_of_budget,3) fpct, budget_status status, round(est_funds_lost_aud,2) lost from {g('budget_utilisation')} where quarter=(select max(quarter) from {g('budget_utilisation')})")
out["visits_daily"] = rows(f"select service_date d, region, sum(scheduled_visits) sched, sum(delivered_visits) deliv, sum(on_time_visits) ontime, sum(late_visits) late, sum(missed_visits) missed from {g('visit_reliability')} group by all order by all")
out["workers"] = rows(f"select worker_id id, home_region region, employment_type emp, scheduled_visits sched, late_visits late, missed_visits missed, round(avg_late_minutes,1) avg_late, round(late_rate,3) late_rate, round(missed_rate,3) missed_rate, needs_review flag from {g('worker_punctuality')} order by late_rate desc")
out["invoice_types"] = rows(f"select exception_type AS kind, count(*) n, round(sum(amount_at_risk_aud),2) at_risk from {g('invoice_exceptions')} group by 1 order by 3 desc")
out["invoice_providers"] = rows(f"select provider_id id, provider_name AS pname, exception_type AS kind, count(*) n, round(sum(amount_at_risk_aud),2) at_risk from {g('invoice_exceptions')} group by all order by all")
json.dump(out, open("site/assets/data/gold.json", "w"), separators=(",", ":"))
for k, v in out.items(): print(k, len(v), v[:2])
