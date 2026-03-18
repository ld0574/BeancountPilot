"""
Home page
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label


def render():
    """Render home page"""
    tx_count = len(st.session_state.get("transactions", []))
    cls_count = len(st.session_state.get("classifications") or [])
    if st.session_state.get("classify_job_id"):
        job_total = st.session_state.get("classify_job_total")
        job_done = st.session_state.get("classify_job_done")
        if isinstance(job_total, int) and job_total > 0:
            tx_count = job_total
        if isinstance(job_done, int):
            cls_count = job_done
    ratio = (cls_count / tx_count * 100) if tx_count else 0

    st.markdown(
        (
            f'<div class="main-header">'
            f"<h1>{label('home_title')}</h1>"
            f"<p>{t('home_description')}</p>"
            f"</div>"
        ),
        unsafe_allow_html=True,
    )

    steps = [
        ("01", label("home_step1_title"), t("home_step1_desc")),
        ("02", label("home_flow_step2_title"), t("home_flow_step2_desc")),
        ("03", label("home_step2_title"), t("home_step2_desc")),
        ("04", label("home_step3_title"), t("home_step3_desc")),
    ]

    flow_items = []
    for idx, (no, title, desc) in enumerate(steps):
        flow_items.append(
            (
                '<div class="workflow-step">'
                f'<div class="workflow-step-no">{no}</div>'
                f"<h4>{title}</h4>"
                f"<p>{desc}</p>"
                "</div>"
            )
        )
        if idx < len(steps) - 1:
            flow_items.append('<div class="workflow-arrow">→</div>')

    st.markdown(
        (
            '<div class="section-card workflow-wrap">'
            '<div class="workflow-head">'
            f'<h3 class="workflow-title">{label("home_workflow_title")}</h3>'
            f'<div class="workflow-progress-badge">{label("home_pipeline_progress")}: {ratio:.0f}%</div>'
            "</div>"
            f'<p class="workflow-desc">{t("home_workflow_description")}</p>'
            '<div class="workflow-grid">'
            f'{"".join(flow_items)}'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_transactions_loaded")}</div>'
                f'<div class="kpi-value">{tx_count}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_classified")}</div>'
                f'<div class="kpi-value">{cls_count}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    with col3:
        provider_id = st.session_state.get("provider", "deepseek")
        provider = provider_id
        for profile in st.session_state.get("ai_profiles", []):
            if profile.get("id") == provider_id:
                provider = profile.get("name", provider_id)
                break
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_current_provider")}</div>'
                f'<div class="kpi-value" style="font-size:1.2rem;">{provider}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    init_i18n()
    render()
