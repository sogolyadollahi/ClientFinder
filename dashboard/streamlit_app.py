"""Streamlit dashboard for the ClientFinder FastAPI backend."""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("CLIENTFINDER_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20
PIPELINE_STATUSES = ["new", "contacted", "replied", "call", "proposal", "won", "lost"]


class APIError(RuntimeError):
    pass


def api_request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_BASE_URL}{path}", timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise APIError(
            f"Cannot reach the API at {API_BASE_URL}. Start FastAPI and check the URL."
        ) from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise APIError(f"API returned {response.status_code}: {detail}")

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def show_api_error(error: Exception) -> None:
    st.error(str(error))


def load_leads(status: str, min_score: int, limit: int):
    params = {"min_score": min_score, "limit": limit}
    if status != "all":
        params["status"] = status
    return api_request("GET", "/leads", params=params)


def overview_page():
    st.title("ClientFinder")
    st.caption("Lead discovery, qualification and outreach pipeline")
    try:
        summary = api_request("GET", "/analytics/pipeline")
        leads = load_leads("all", 0, 200)
        opportunities = api_request("GET", "/opportunities", params={"limit": 200})
    except APIError as error:
        show_api_error(error)
        st.info("Start the API with: uvicorn app.main:app --reload")
        return

    won = summary["by_status"].get("won", 0)
    lost = summary["by_status"].get("lost", 0)
    closed = won + lost
    win_rate = won / closed * 100 if closed else 0

    metrics = st.columns(4)
    metrics[0].metric("Total leads", summary["total_leads"])
    metrics[1].metric(
        "Open pipeline",
        sum(summary["by_status"].get(s, 0) for s in ["new", "contacted", "replied", "call", "proposal"]),
    )
    metrics[2].metric("Interactions", summary["total_interactions"])
    metrics[3].metric("Win rate", f"{win_rate:.1f}%")

    left, right = st.columns(2)
    with left:
        st.subheader("Pipeline")
        rows = [{"Stage": s.title(), "Leads": summary["by_status"].get(s, 0)} for s in PIPELINE_STATUSES]
        st.bar_chart(pd.DataFrame(rows).set_index("Stage"))
    with right:
        st.subheader("Lead scores")
        if leads:
            frame = pd.DataFrame(
                [{"Lead": lead["company_name"], "Score": lead["score"]} for lead in leads]
            ).sort_values("Score", ascending=False)
            st.bar_chart(frame.set_index("Lead"))
        else:
            st.info("No leads yet.")

    st.subheader("Source data")
    cols = st.columns(2)
    cols[0].metric("Saved opportunities", len(opportunities))
    cols[1].metric("Saved outreach drafts", summary["total_drafts"])


def leads_page():
    st.title("Lead management")
    with st.sidebar:
        st.subheader("Lead filters")
        status_filter = st.selectbox("Pipeline stage", ["all"] + PIPELINE_STATUSES)
        minimum_score = st.slider("Minimum score", 0, 100, 0)
        limit = st.selectbox("Maximum results", [25, 50, 100, 200], index=1)

    try:
        leads = load_leads(status_filter, minimum_score, limit)
    except APIError as error:
        show_api_error(error)
        return

    if not leads:
        st.info("No leads match these filters.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "ID": lead["id"], "Company": lead["company_name"], "Score": lead["score"],
                "Stage": lead["status"], "Region": lead["region"], "Website": lead["website"],
            }
            for lead in leads
        ]),
        use_container_width=True,
        hide_index=True,
    )

    options = {
        f'{lead["company_name"]} · #{lead["id"]} · score {lead["score"]}': lead["id"]
        for lead in leads
    }
    selected = st.selectbox("Open lead", list(options))
    lead_id = options[selected]

    try:
        lead = api_request("GET", f"/leads/{lead_id}")
        interactions = api_request("GET", f"/leads/{lead_id}/interactions")
        drafts = api_request("GET", f"/leads/{lead_id}/outreach-drafts")
    except APIError as error:
        show_api_error(error)
        return

    st.divider()
    st.subheader(lead["company_name"])
    st.markdown(f'**Website:** [{lead["website"]}]({lead["website"]})')
    st.write(f'**Score:** {lead["score"]} · **Stage:** {lead["status"]}')
    st.write(f'**Region:** {lead["region"]} · **Company size:** {lead["company_size"]}')
    st.write(f'**Services / skills:** {lead["services_text"] or "Not recorded"}')
    with st.expander("Research evidence and score reasons"):
        st.write(lead["evidence_text"] or "No evidence recorded.")
        st.caption(lead["score_reasons"] or "No score reasons recorded.")

    interaction_tab, draft_tab, history_tab = st.tabs(
        ["Log interaction", "Create outreach draft", "History and drafts"]
    )
    with interaction_tab:
        with st.form("interaction_form"):
            stage = st.selectbox(
                "New pipeline stage",
                ["contacted", "replied", "call", "proposal", "won", "lost"],
            )
            notes = st.text_area("Interaction notes")
            next_action = st.text_input(
                "Next action (ISO timestamp, optional)", placeholder="2026-11-05T10:00:00Z"
            )
            submitted = st.form_submit_button("Save interaction")
        if submitted:
            payload = {"interaction_type": stage, "notes": notes}
            if next_action.strip():
                payload["next_action_at"] = next_action.strip()
            try:
                api_request("POST", f"/leads/{lead_id}/interactions", json=payload)
                st.success("Interaction saved.")
                st.rerun()
            except APIError as error:
                show_api_error(error)

    with draft_tab:
        with st.form("draft_form"):
            channel = st.selectbox("Channel", ["email", "linkedin", "other"])
            tone = st.selectbox("Tone", ["professional", "concise"])
            context = st.text_area(
                "Additional context",
                help="Only add facts you have verified. This text is included in the draft.",
            )
            submitted_draft = st.form_submit_button("Generate draft")
        if submitted_draft:
            try:
                api_request(
                    "POST",
                    f"/leads/{lead_id}/outreach-drafts",
                    json={"channel": channel, "tone": tone, "context": context},
                )
                st.success("Draft saved. It has not been sent.")
                st.rerun()
            except APIError as error:
                show_api_error(error)

    with history_tab:
        st.markdown("**Interaction history**")
        if interactions:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Date": item["occurred_at"], "Type": item["interaction_type"],
                        "Notes": item["notes"], "Next action": item["next_action_at"],
                    }
                    for item in interactions
                ]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No interactions recorded.")

        st.markdown("**Outreach drafts**")
        if drafts:
            for draft in drafts:
                with st.expander(f'{draft["channel"].title()} draft · {draft["created_at"]}'):
                    if draft["subject"]:
                        st.text_input("Subject", draft["subject"], key=f'subject_{draft["id"]}')
                    st.text_area("Message", draft["body"], height=240, key=f'body_{draft["id"]}')
                    st.caption("Draft only — not sent.")
        else:
            st.caption("No drafts saved.")


def opportunities_page():
    st.title("Opportunity feed")
    st.caption("Job listings are research signals, not proof of agency demand.")
    col1, col2 = st.columns([1, 3])
    page = col1.number_input("Arbeitnow page", min_value=1, max_value=100, value=1)
    if col2.button("Sync Arbeitnow page", type="primary"):
        try:
            result = api_request("POST", "/sources/arbeitnow/sync", params={"page": int(page)})
            st.success(
                f'Fetched {result["fetched"]}: {result["created"]} created, '
                f'{result["updated"]} updated, {result["unchanged"]} unchanged.'
            )
        except APIError as error:
            show_api_error(error)

    keyword = st.text_input("Search company, role or description")
    remote_only = st.checkbox("Remote only")
    params = {"limit": 200}
    if keyword.strip():
        params["keyword"] = keyword.strip()
    if remote_only:
        params["remote"] = True
    try:
        opportunities = api_request("GET", "/opportunities", params=params)
    except APIError as error:
        show_api_error(error)
        return

    if opportunities:
        st.dataframe(
            pd.DataFrame([
                {
                    "Company": item["company_name"], "Role": item["title"],
                    "Location": item["location"], "Remote": item["remote"],
                    "Tags": ", ".join(item["tags"]), "Source": item["source_url"],
                }
                for item in opportunities
            ]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No opportunities found. Try syncing a source page.")


def main():
    st.set_page_config(page_title="ClientFinder", page_icon="🎯", layout="wide")
    st.sidebar.title("ClientFinder")
    st.sidebar.caption("API-backed workspace")
    page = st.sidebar.radio("Workspace", ["Overview", "Leads", "Opportunities"])
    if page == "Overview":
        overview_page()
    elif page == "Leads":
        leads_page()
    else:
        opportunities_page()
    st.sidebar.divider()
    st.sidebar.caption(f"API: {API_BASE_URL}")


if __name__ == "__main__":
    main()
