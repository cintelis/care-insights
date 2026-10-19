"""
Care Insights dashboard - Streamlit + DuckDB, no Power BI.

Reads the gold tables straight from the lake:
  CARE_SOURCE=local  -> data/lake/gold/*.parquet (output of transform/run_local.py)
  CARE_SOURCE=adls   -> Delta tables at abfss://lake@<account>.dfs.core.windows.net/gold/<table>
                        written by the Fabric notebook; auth = your `az login` (Entra, no keys)

  streamlit run app/dashboard.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
GOLD_TABLES = ["budget_utilisation", "visit_reliability", "worker_punctuality", "invoice_exceptions"]

# Status palette (fixed meaning, always paired with a text label) and categorical slots.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
BUDGET_COLORS = {"On track": STATUS["good"], "Under-used": STATUS["warning"], "Over budget": STATUS["critical"]}
VISIT_COLORS = {"On time": STATUS["good"], "Late": STATUS["warning"], "Missed": STATUS["critical"]}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
MUTED = "#898781"

st.set_page_config(page_title="Care Insights", page_icon="📊", layout="wide")


# ---------------------------------------------------------------- data
def source_config() -> tuple[str, str | None]:
    src = os.getenv("CARE_SOURCE")
    acct = os.getenv("CARE_STORAGE_ACCOUNT")
    state = ROOT / ".poc-state.json"
    if not acct and state.exists():
        acct = json.loads(state.read_text(encoding="utf-8-sig")).get("storageAccountName")
    if not src:
        src = "local" if (ROOT / "data/lake/gold/budget_utilisation.parquet").exists() else "adls"
    return src, acct


@st.cache_data(ttl=600, show_spinner="Reading gold tables from the lake...")
def load(src: str, acct: str | None) -> dict[str, pd.DataFrame]:
    con = duckdb.connect()
    if src == "adls":
        con.execute("INSTALL azure; LOAD azure; INSTALL delta; LOAD delta;")
        con.execute(f"CREATE SECRET lake (TYPE azure, PROVIDER credential_chain, CHAIN 'cli', ACCOUNT_NAME '{acct}')")
        rel = lambda t: f"delta_scan('abfss://lake@{acct}.dfs.core.windows.net/gold/{t}')"
    else:
        rel = lambda t: f"read_parquet('{(ROOT / 'data/lake/gold' / f'{t}.parquet').as_posix()}')"
    return {t: con.execute(f"SELECT * FROM {rel(t)}").df() for t in GOLD_TABLES}


src, acct = source_config()
try:
    d = load(src, acct)
except Exception as e:  # noqa: BLE001
    st.error(f"Could not read gold tables ({src}). Run `python transform/run_local.py` or the Fabric notebook first.\n\n{e}")
    st.stop()

budget, visits, workers, invoices = (d[t] for t in GOLD_TABLES)
visits["service_date"] = pd.to_datetime(visits["service_date"])
as_of = visits["service_date"].max()


def style(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=44, b=8), bargap=0.25,
                      font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif"),
                      legend=dict(orientation="h", y=-0.14, yanchor="top", x=0, title=None),
                      hoverlabel=dict(font_size=13))
    fig.update_xaxes(showgrid=False, title=None)
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.18)", zeroline=False, title=None)
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    return fig


def aud(x: float) -> str:
    return f"${x:,.0f}"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Care Insights")
    st.caption("Support at Home · budget, visit and invoice monitoring")
    quarters = sorted(budget["quarter"].unique(), reverse=True)
    quarter = st.selectbox("Quarter", quarters, index=0)
    regions = sorted(budget["region"].dropna().unique())
    sel_regions = st.multiselect("Region", regions, placeholder="All regions")
    st.divider()
    st.caption(f"Actuals to **{as_of:%d %b %Y}**")
    st.caption(f"Source: `{'ADLS Gen2 · ' + acct if src == 'adls' else 'local lake (DuckDB test run)'}`")
    st.caption("Synthetic data - no real participants.")

rf = (lambda df, col="region": df[df[col].isin(sel_regions)] if sel_regions else df)
b = rf(budget[budget["quarter"] == quarter])
v = rf(visits)
inv = invoices if not sel_regions else invoices[invoices["participant_id"].isin(rf(budget)["participant_id"])]
last30 = v[v["service_date"] > as_of - pd.Timedelta(days=30)]
is_open = not bool(b["is_closed"].iloc[0]) if len(b) else False

# ---------------------------------------------------------------- headline
st.markdown(f"## {quarter} {'· in progress' if is_open else '· closed'}")
k = st.columns(5)
under = b[b["budget_status"] == "Under-used"]
over = b[b["budget_status"] == "Over budget"]
k[0].metric("Participants on track", f"{(b['budget_status'] == 'On track').mean():.0%}", help="Forecast spend between 70% and 100% of quarterly budget")
k[1].metric("Funds at risk of being lost", aud(b["est_funds_lost_aud"].sum()),
            f"{len(under)} under-used participants", delta_color="off", delta_arrow="off",
            help="Forecast unspent budget above the carry-over limit (greater of $1,000 or 10%) - illustrative rule")
k[2].metric("Forecast overspend", aud((over["forecast_spend_aud"] - over["budget_aud"]).sum()),
            f"{len(over)} participants over budget", delta_color="off", delta_arrow="off")
on_time = last30["on_time_visits"].sum() / max(last30["scheduled_visits"].sum(), 1)
k[3].metric("On-time visits · 30 days", f"{on_time:.1%}",
            f"{int(last30['missed_visits'].sum())} missed", delta_color="off", delta_arrow="off")
k[4].metric("Invoice $ at risk", aud(inv["amount_at_risk_aud"].sum()), f"{len(inv)} exceptions", delta_color="off", delta_arrow="off")

tab_budget, tab_visits, tab_workers, tab_inv = st.tabs(["Budgets", "Visits", "Workers", "Invoices"])

# ---------------------------------------------------------------- budgets
with tab_budget:
    c1, c2 = st.columns([3, 2])
    with c1:
        h = b.assign(pct=(b["forecast_pct_of_budget"] * 100).clip(upper=160))
        fig = px.histogram(h, x="pct", color="budget_status", nbins=40, color_discrete_map=BUDGET_COLORS,
                           category_orders={"budget_status": list(BUDGET_COLORS)},
                           labels={"pct": "Forecast spend, % of budget", "budget_status": "Status"},
                           title="Where participants will land this quarter")
        for x, label in ((70, "70% under-use line"), (100, "Budget")):
            fig.add_vline(x=x, line_width=1, line_dash="dot", line_color=MUTED,
                          annotation_text=label, annotation_font_color=MUTED, annotation_position="top")
        fig.update_traces(hovertemplate="%{x:.0f}% of budget<br>%{y} participants<extra>%{fullData.name}</extra>")
        st.plotly_chart(style(fig), width="stretch")
    with c2:
        by_region = (b.groupby("region", as_index=False)["est_funds_lost_aud"].sum()
                       .sort_values("est_funds_lost_aud"))
        fig = px.bar(by_region, x="est_funds_lost_aud", y="region", orientation="h",
                     title="Funds at risk by region", color_discrete_sequence=[SERIES[0]])
        fig.update_traces(hovertemplate="%{y}<br>%{x:$,.0f} at risk<extra></extra>",
                          texttemplate="%{x:$,.0f}", textposition="outside", cliponaxis=False)
        fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, by_region["est_funds_lost_aud"].max() * 1.25])
        st.plotly_chart(style(fig), width="stretch")

    st.markdown("#### Action list")
    st.caption("Under-used: call to review the care plan before funds are lost. Over budget: review bookings before the quarter ends.")
    act = b[b["budget_status"] != "On track"].copy()
    act["priority_aud"] = act["est_funds_lost_aud"] + (act["forecast_spend_aud"] - act["budget_aud"]).clip(lower=0)
    st.dataframe(
        act.sort_values("priority_aud", ascending=False)[
            ["participant_id", "budget_status", "region", "classification_level", "budget_aud",
             "spend_to_date_aud", "booked_aud", "forecast_spend_aud", "forecast_pct_of_budget", "est_funds_lost_aud"]],
        hide_index=True, width="stretch", height=360,
        column_config={
            "participant_id": "Participant", "budget_status": "Status", "region": "Region",
            "classification_level": st.column_config.NumberColumn("Level", format="%d"),
            "budget_aud": st.column_config.NumberColumn("Budget", format="$%.0f"),
            "spend_to_date_aud": st.column_config.NumberColumn("Spent", format="$%.0f"),
            "booked_aud": st.column_config.NumberColumn("Booked", format="$%.0f"),
            "forecast_spend_aud": st.column_config.NumberColumn("Forecast", format="$%.0f"),
            "forecast_pct_of_budget": st.column_config.ProgressColumn("Forecast % of budget", format="percent", min_value=0, max_value=1.5),
            "est_funds_lost_aud": st.column_config.NumberColumn("Funds at risk", format="$%.0f"),
        })

# ---------------------------------------------------------------- visits
with tab_visits:
    wk = (v.assign(week=v["service_date"].dt.to_period("W-SUN").dt.start_time)
            .groupby("week", as_index=False)[["on_time_visits", "late_visits", "missed_visits", "scheduled_visits"]].sum())
    wk = wk[wk["week"] + pd.Timedelta(days=6) <= as_of]  # complete weeks only
    long = wk.melt("week", ["on_time_visits", "late_visits", "missed_visits"], var_name="status", value_name="visits")
    long["status"] = long["status"].map({"on_time_visits": "On time", "late_visits": "Late", "missed_visits": "Missed"})
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(long, x="week", y="visits", color="status", color_discrete_map=VISIT_COLORS,
                     category_orders={"status": list(VISIT_COLORS)}, title="Visits per week")
        fig.update_traces(hovertemplate="Week of %{x|%d %b}<br>%{y:,} visits<extra>%{fullData.name}</extra>",
                          marker_line_width=2, marker_line_color="rgba(0,0,0,0)")
        st.plotly_chart(style(fig), width="stretch")
    with c2:
        reg = v.groupby("region", as_index=False)[["missed_visits", "late_visits", "scheduled_visits"]].sum()
        reg["Missed"] = reg["missed_visits"] / reg["scheduled_visits"]
        reg["Late"] = reg["late_visits"] / reg["scheduled_visits"]
        reg = reg.sort_values("Missed")
        fig = px.bar(reg, y="region", x=["Missed", "Late"], orientation="h", barmode="group",
                     color_discrete_map=VISIT_COLORS, title="Missed and late rate by region")
        fig.update_traces(hovertemplate="%{y}<br>%{x:.1%}<extra>%{fullData.name}</extra>")
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(style(fig), width="stretch")

    svc = v.groupby("service_name", as_index=False)[["scheduled_visits", "on_time_visits", "late_visits", "missed_visits", "missing_check_outs", "delivered_value_aud"]].sum()
    svc["on_time_rate"] = svc["on_time_visits"] / svc["scheduled_visits"]
    st.dataframe(svc.sort_values("scheduled_visits", ascending=False), hide_index=True, width="stretch",
                 column_config={"service_name": "Service", "scheduled_visits": "Scheduled", "on_time_visits": "On time",
                                "late_visits": "Late", "missed_visits": "Missed", "missing_check_outs": "No check-out",
                                "delivered_value_aud": st.column_config.NumberColumn("Delivered value", format="$%.0f"),
                                "on_time_rate": st.column_config.ProgressColumn("On-time rate", format="percent", min_value=0, max_value=1)})

# ---------------------------------------------------------------- workers
with tab_workers:
    w = rf(workers, "home_region")
    st.caption("Workers late to more than 20% of 30+ visits. Often a roster problem (not enough travel time) rather than a people problem.")
    fig = px.scatter(w, x="scheduled_visits", y="late_rate", color="needs_review",
                     color_discrete_map={True: STATUS["critical"], False: SERIES[0]},
                     hover_data={"worker_id": True, "home_region": True, "avg_late_minutes": True, "needs_review": False},
                     labels={"scheduled_visits": "Visits scheduled", "late_rate": "Late rate", "needs_review": "Needs review"},
                     title="Late rate vs workload")
    fig.update_traces(marker=dict(size=10, line=dict(width=2, color="rgba(252,252,251,0.9)")))
    fig.add_hline(y=0.2, line_width=1, line_dash="dot", line_color=MUTED, annotation_text="20% review line",
                  annotation_font_color=MUTED)
    fig.update_yaxes(tickformat=".0%")
    for tr in fig.data:
        tr.name = "Needs review" if tr.name == "True" else "OK"
    st.plotly_chart(style(fig, 320), width="stretch")
    st.dataframe(w[w["needs_review"]].sort_values("late_rate", ascending=False), hide_index=True, width="stretch",
                 column_config={"late_rate": st.column_config.ProgressColumn("Late rate", format="percent", min_value=0, max_value=1),
                                "missed_rate": st.column_config.NumberColumn("Missed rate", format="percent")})

# ---------------------------------------------------------------- invoices
with tab_inv:
    by_prov = inv.groupby(["provider_name", "exception_type"], as_index=False)["amount_at_risk_aud"].sum()
    order = by_prov.groupby("provider_name")["amount_at_risk_aud"].sum().sort_values().index.tolist()
    types = sorted(inv["exception_type"].unique())
    fig = px.bar(by_prov, y="provider_name", x="amount_at_risk_aud", color="exception_type", orientation="h",
                 category_orders={"provider_name": order, "exception_type": types},
                 color_discrete_sequence=SERIES, title="Dollars at risk by provider")
    fig.update_traces(hovertemplate="%{y}<br>%{x:$,.0f}<extra>%{fullData.name}</extra>",
                      marker_line_width=2, marker_line_color="rgba(0,0,0,0)")
    fig.update_xaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(style(fig, 420), width="stretch")
    st.dataframe(inv.sort_values("amount_at_risk_aud", ascending=False), hide_index=True, width="stretch", height=360,
                 column_config={c: st.column_config.NumberColumn(format="$%.2f")
                                for c in ["unit_rate", "price_cap_aud", "amount_aud", "amount_at_risk_aud"]})
