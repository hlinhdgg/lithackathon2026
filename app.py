"""getthrulaw - Streamlit UI shell.

This first version is intentionally presentation-only. The data and analysis
hooks will be added in the next build steps.
"""

from pathlib import Path
import os
import json

import streamlit as st
from dotenv import load_dotenv

from services.regulation import extract_change
from services.gazette import download_gazette, load_seen, save_seen, scrape_latest_gazettes
from services.relevance_filter import classify_relevance
from services.analyzer import analyze_all
from services.retrieval import retrieve_affected_sections
from services.propagation import load_dependencies, downstream_assets
from services.update_generator import suggest_updates
from services.remediation import load_tasks, record_decision

load_dotenv()


@st.cache_data(show_spinner=False)
def cached_extract(path: str, modified_time: float) -> dict:
    """Avoid repeating a paid extraction on every Streamlit rerun."""
    return extract_change(path)


COMPANY_DOCS = Path(__file__).parent / "data" / "company_docs"
REGULATIONS = Path(__file__).parent / "data" / "regulations"


def current_regulation_path() -> Path | None:
    actual = sorted(REGULATIONS.glob("gazette_*")) if REGULATIONS.exists() else []
    if actual:
        return actual[-1]
    demo = sorted(REGULATIONS.glob("*")) if REGULATIONS.exists() else []
    return demo[0] if demo else None


st.set_page_config(
    page_title="getthrulaw",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { color: #1d4ed8; }
    .status { color: #15803d; font-weight: 600; }
    .muted { color: #64748b; }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.title("⚖️ getthrulaw")
    st.caption("Singapore regulatory change impact management")
    st.divider()
    page = st.radio(
        "Navigate",
        ["Dashboard", "Impacts", "Dependency Map", "Propagation"],
        label_visibility="collapsed",
    )
    st.divider()
    st.subheader("Monitoring")
    st.success("● Monitoring active")
    gazette_url = os.getenv("GAZETTE_SOURCE_URL", "https://www.egazette.gov.sg/")
    st.markdown(f"Primary source: [Singapore Government Gazette]({gazette_url})")
    uploaded_files = st.file_uploader(
        "Upload company documents",
        type=["txt", "md", "pdf", "docx"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        COMPANY_DOCS.mkdir(parents=True, exist_ok=True)
        for uploaded_file in uploaded_files:
            (COMPANY_DOCS / uploaded_file.name).write_bytes(uploaded_file.getvalue())
        st.success(f"Loaded {len(uploaded_files)} document(s).")


def dashboard() -> None:
    st.title("Regulatory Health")
    st.caption("See what may need attention when regulations change.")

    metrics = st.columns(4)
    regulation_count = len(list(REGULATIONS.glob("*"))) if REGULATIONS.exists() else 0
    asset_count = len(list(COMPANY_DOCS.glob("*"))) if COMPANY_DOCS.exists() else 0
    metrics[0].metric("Regulations monitored", regulation_count)
    metrics[1].metric("Internal assets", asset_count)
    metrics[2].metric("Assets at risk", "0")
    metrics[3].metric("Reviews pending", "0")

    st.divider()
    left, right = st.columns([2, 1])
    with left:
        st.subheader("New impact")
        if regulation_count:
            regulation_path = next(REGULATIONS.glob("*"))
            change = cached_extract(str(regulation_path), regulation_path.stat().st_mtime)
            st.info(f"{change['title']} loaded from the demo dataset.")
            st.markdown(f"**Effective:** {change.get('effective_date') or 'Not specified'}")
            st.write(change.get("change_summary", ""))
            with st.expander("Extracted requirement"):
                st.write(change.get("new_requirement", "Not extracted"))
        else:
            st.info("No regulatory updates have been analysed yet.")
        if st.button("Check Gazette listing", use_container_width=True):
            try:
                entries = scrape_latest_gazettes(gazette_url)
                seen_path = Path(__file__).parent / "data" / "seen_updates.json"
                seen = load_seen(seen_path)
                new_entries = [entry for entry in entries if entry["id"] not in seen]
                save_seen(seen_path, seen | {entry["id"] for entry in entries})
                st.success(f"Found {len(entries)} Gazette entries; {len(new_entries)} new.")
                if new_entries:
                    st.dataframe(new_entries, use_container_width=True, hide_index=True)
                st.session_state["gazette_entries"] = entries
            except Exception as exc:
                st.error(f"Gazette listing could not be fetched: {exc}")
        entries = st.session_state.get("gazette_entries", [])
        if entries:
            selected_title = st.selectbox(
                "Select a Gazette item to analyse",
                [entry["title"] for entry in entries],
            )
            selected = next(entry for entry in entries if entry["title"] == selected_title)
            if st.button("Load selected Gazette", use_container_width=True):
                try:
                    downloaded = download_gazette(selected, REGULATIONS)
                    st.success(f"Loaded {downloaded.name} for analysis.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Gazette item could not be downloaded: {exc}")
        st.link_button("Open Singapore Gazette", gazette_url, use_container_width=True)
    with right:
        st.subheader("Quick start")
        st.markdown(
            "1. Add a regulation\n"
            "2. Upload company documents\n"
            "3. Analyse potential impact\n"
            "4. Review proposed updates"
        )


def impacts() -> None:
    st.title("Impact Analysis")
    st.caption("Affected policies, workflows and templates will appear here.")
    regulation_path = current_regulation_path()
    if regulation_path is None:
        st.info("Add a regulation before analysing impact.")
        return
    change = cached_extract(str(regulation_path), regulation_path.stat().st_mtime)
    use_ai = st.checkbox(
        "Use OpenRouter for this analysis (uses credits)",
        value=False,
        help="Leave off to use the free local analyser.",
    )
    sections = retrieve_affected_sections(
        f"{change.get('change_summary', '')} {change.get('new_requirement', '')}",
        str(COMPANY_DOCS),
    )
    if use_ai:
        st.warning("OpenRouter mode is limited to the top result to protect your API budget.")
        sections = sections[:1]
    findings = analyze_all(change, sections, use_ai=use_ai)
    if not findings:
        st.info("No potentially affected sections found.")
        return
    st.metric("Potentially affected assets", len(findings))
    for finding in findings:
        label = (
            f"{finding['severity'].upper()} · {finding['document']} · "
            f"impact {finding['impact_score']}/100 · "
            f"confidence {finding['confidence_score']}/100"
        )
        with st.expander(label):
            st.write(finding["explanation"])
            left, right = st.columns(2)
            with left:
                st.caption("Legal requirement")
                st.info(finding["legal_quote"])
            with right:
                st.caption("Company passage")
                st.warning(finding["company_quote"])
            st.write(f"**Recommended action:** {finding['recommended_action']}")


def dependency_map() -> None:
    st.title("Dependency Map")
    st.caption("Visualise how regulations flow through internal knowledge.")
    dependency_path = Path(__file__).parent / "data" / "dependencies.json"
    dependencies = load_dependencies(dependency_path)
    if not dependencies:
        st.info("No dependencies have been indexed yet.")
        return
    st.markdown("### Proposed MAS SCS Framework")
    dot = ["digraph G {", 'rankdir="TB";', 'node [shape=box, style="rounded,filled", fillcolor="#eff6ff"];']
    for edge in dependencies:
        dot.append(f'"{edge["from"]}" -> "{edge["to"]}" [label="{edge["relationship"]}"];')
    dot.append("}")
    st.graphviz_chart("\n".join(dot), use_container_width=True)
    st.metric("Downstream assets", len(downstream_assets("Proposed MAS SCS Framework", dependencies)))
    st.dataframe(dependencies, use_container_width=True, hide_index=True)


def propagation() -> None:
    st.title("Propagation Review")
    st.caption("Review and approve proposed updates before they reach downstream assets.")
    regulation_path = current_regulation_path()
    if regulation_path is None:
        st.info("Add a regulation before generating proposed updates.")
        return
    change = cached_extract(str(regulation_path), regulation_path.stat().st_mtime)
    sections = retrieve_affected_sections(
        f"{change.get('change_summary', '')} {change.get('new_requirement', '')}",
        str(COMPANY_DOCS),
    )
    findings = analyze_all(change, sections)
    proposals = suggest_updates(change, findings[:3])
    tasks_path = Path(__file__).parent / "data" / "remediation_tasks.json"
    tasks = load_tasks(tasks_path)
    pending = sum(1 for proposal in proposals if not any(
        task.get("document") == proposal.get("document") for task in tasks
    ))
    st.metric("Proposals pending review", pending)
    for index, proposal in enumerate(proposals):
        with st.expander(f"{proposal['document']} · {proposal['confidence']} confidence"):
            left, right = st.columns(2)
            with left:
                st.caption("Current text")
                st.error(proposal["old_text"])
            with right:
                st.caption("Proposed text")
                st.success(proposal["proposed_text"])
            st.caption(f"Reason: {proposal['reason']}")
            approve, reject, escalate = st.columns(3)
            if approve.button("Approve", key=f"approve_{index}"):
                record_decision(tasks_path, proposal, "approved")
                st.success("Proposal approved and recorded.")
            if reject.button("Reject", key=f"reject_{index}"):
                record_decision(tasks_path, proposal, "rejected")
                st.warning("Proposal rejected and recorded.")
            if escalate.button("Escalate", key=f"escalate_{index}"):
                record_decision(tasks_path, proposal, "escalated")
                st.info("Lawyer review task created.")

    tasks = load_tasks(tasks_path)
    if tasks:
        st.divider()
        st.subheader("Remediation tasks")
        st.dataframe(tasks, use_container_width=True, hide_index=True)


if page == "Dashboard":
    dashboard()
elif page == "Impacts":
    impacts()
elif page == "Dependency Map":
    dependency_map()
else:
    propagation()
