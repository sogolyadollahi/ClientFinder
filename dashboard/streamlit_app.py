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


def company_discovery_page():
    st.title("Company discovery")
    st.caption("Exa live search. Results are displayed for this session and are not saved to the ClientFinder database.")
    with st.form("company_discovery_form"):
        query = st.text_input("What kind of company should ClientFinder find?", value="Python automation software agencies")
        location = st.text_input("Location / market", value="Germany")
        country = st.text_input("Country code", value="DE", max_chars=2)
        limit = st.slider("Results to fetch", 1, 20, 10)
        submitted = st.form_submit_button("Search with Exa", type="primary")
    if submitted:
        if not query.strip():
            st.warning("Enter a search query.")
        else:
            try:
                result = api_request("POST", "/discovery/companies/search", json={
                    "query": query.strip(), "location": location.strip() or None,
                    "country": country.strip().upper() or None, "limit": limit,
                })
                st.session_state["exa_company_results"] = result["results"]
                st.success(f'Exa returned {result["fetched"]} company-related results.')
            except APIError as error:
                show_api_error(error)
    results = st.session_state.get("exa_company_results", [])
    if not results:
        st.info("Run a search to see company-related results.")
        return
    st.dataframe(pd.DataFrame([{
        "Result title (not verified company name)": item["company_name"],
        "Fit score": item["qualification_score"], "Location context": item["location"],
        "URL": item["source_url"], "Evidence": item["snippet"],
    } for item in results]), use_container_width=True, hide_index=True)
    selected_index = st.selectbox("Inspect result", range(len(results)),
        format_func=lambda i: f'{results[i]["company_name"]} · score {results[i]["qualification_score"]}')
    selected = results[selected_index]
    st.markdown(f'**Source page:** [{selected["source_url"]}]({selected["source_url"]})')
    st.write(selected["snippet"] or "No highlights returned.")
    st.caption("The title may be a page title, not a verified legal company name. Verify the company and official domain manually before adding it as a Lead.")


def company_reviews_page():
    st.title("Company verification")
    st.caption("Confirm the official domain manually before promoting a company to Leads.")
    status = st.selectbox("Review status", ["pending", "verified", "rejected"])
    try:
        reviews = api_request("GET", "/companies/reviews", params={"status": status, "limit": 200})
    except APIError as error:
        show_api_error(error)
        return
    if not reviews:
        st.info("No companies in this review state.")
        return
    options = {
        f'{item["company_name"]} · review #{item["id"]}': item["id"]
        for item in reviews
    }
    selected = st.selectbox("Company", list(options))
    review_id = options[selected]
    review = next(item for item in reviews if item["id"] == review_id)
    st.write(f'**Current website:** {review["official_website"] or "Not verified"}')
    st.write(f'**Notes:** {review["verification_notes"] or "None"}')
    with st.form(f"verify_company_{review_id}"):
        website = st.text_input("Official website", value=review["official_website"] or "")
        next_status = st.selectbox(
            "Verification status", ["pending", "verified", "rejected"],
            index=["pending", "verified", "rejected"].index(review["verification_status"]),
        )
        notes = st.text_area("Verification notes", value=review["verification_notes"])
        submitted = st.form_submit_button("Save verification")
    if submitted:
        payload = {
            "verification_status": next_status,
            "verification_notes": notes,
        }
        if website.strip():
            payload["official_website"] = website.strip()
        try:
            api_request("PATCH", f"/companies/reviews/{review_id}", json=payload)
            st.success("Review updated.")
            st.rerun()
        except APIError as error:
            show_api_error(error)

    if review["verification_status"] == "verified":
        st.divider()
        if st.button("Promote verified company to Leads", type="primary"):
            try:
                promoted = api_request("POST", f"/companies/reviews/{review_id}/promote")
                st.success(f'Lead #{promoted["lead"]["id"]} created.')
            except APIError as error:
                show_api_error(error)


def opportunities_page():
    st.title("Remote job and contract discovery")
    st.caption("Arbeitnow is the active job source. SerpApi is not required for this workflow.")

    with st.expander("Sync jobs from Arbeitnow", expanded=True):
        st.write("Fetch the latest available page from Arbeitnow and save listings locally.")
        page = st.number_input("Arbeitnow page", min_value=1, max_value=100, value=1)
        if st.button("Sync Arbeitnow", type="primary"):
            try:
                result = api_request(
                    "POST", "/sources/arbeitnow/sync", params={"page": int(page)}
                )
                st.success(
                    f'Fetched {result["fetched"]}: {result["created"]} created, '
                    f'{result["updated"]} updated, {result["unchanged"]} unchanged.'
                )
            except APIError as error:
                show_api_error(error)

    st.subheader("Saved opportunities")
    keyword = st.text_input("Filter by role, company, or keyword")
    remote_only = st.checkbox("Remote only", value=True)
    params = {"limit": 200, "source": "arbeitnow"}
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
                    "Tags": ", ".join(item["tags"]), "Listing": item["source_url"],
                } for item in opportunities
            ]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "No matching saved Arbeitnow listings. Sync a page above, or broaden the keyword filter."
        )



def main():
    st.set_page_config(page_title="ClientFinder", page_icon="🎯", layout="wide")
    st.sidebar.title("ClientFinder")
    st.sidebar.caption("API-backed workspace")
    page = st.sidebar.radio("Workspace", ["Overview", "Leads", "Company discovery", "Company verification", "Jobs"])
    if page == "Overview":
        overview_page()
    elif page == "Leads":
        leads_page()
    elif page == "Company discovery":
        company_discovery_page()
    elif page == "Company verification":
        company_reviews_page()
    else:
        opportunities_page()
    st.sidebar.divider()
    st.sidebar.caption(f"API: {API_BASE_URL}")


if __name__ == "__main__":
    main()
