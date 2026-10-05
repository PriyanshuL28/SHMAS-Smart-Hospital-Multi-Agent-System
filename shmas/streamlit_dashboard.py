import os
import re
import html
import logging
import streamlit as st

logger = logging.getLogger(__name__)


st.set_page_config(
    page_title="SHMAS · Smart Hospital Multi-Agent System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def load_streamlit_secrets_into_env():
    try:
        for key in ("DATABASE_URL", "GROQ_API_KEY", "GROQ_MODEL", "LOG_LEVEL"):
            if not os.getenv(key) and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        # No secrets.toml (e.g. local development using .env)
        pass

load_streamlit_secrets_into_env()

try:
    from smart_hospital import (run_patient_flow, get_doctor_status, get_beds,
                                test_database_connection, SHMASError,
                                GROQ_MODEL, get_current_est_time)
except RuntimeError as e:
    st.error(f"Configuration error: {e}")
    st.stop()

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BED_ORDER = ["ICU", "Emergency", "Ward", "Normal"]
PIPELINE = [
    ("MoodAnalyzer", "Mood analysis"),
    ("EmergencyTriage", "Triage"),
    ("DoctorScheduler", "Doctor scheduling"),
    ("BedManager", "Bed allocation"),
    ("ConflictResolver", "Conflict resolution"),
]
STATUS_TONE = {"Success": "ok", "Queued": "warn", "Failed": "err", "Skipped": "muted", "Pending": "muted"}

@st.cache_data(ttl=60, show_spinner=False)
def database_is_available():
    return test_database_connection()

def esc(value):
    return html.escape("" if value is None else str(value))

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp div[data-baseweb="select"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1440px; }

/* Header */
.shmas-header {
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
    background: linear-gradient(120deg, #0B3B5C 0%, #0E7490 100%);
    color: #fff; border-radius: 16px; padding: 18px 24px; margin-bottom: 18px;
    box-shadow: 0 8px 24px rgba(14, 116, 144, 0.18);
}
.brand { display: flex; align-items: center; gap: 14px; }
.brand-mark {
    width: 44px; height: 44px; border-radius: 12px; background: rgba(255,255,255,0.15);
    position: relative; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.25);
}
.brand-mark::before, .brand-mark::after {
    content: ""; position: absolute; background: #fff; border-radius: 2px;
    left: 50%; top: 50%; transform: translate(-50%, -50%);
}
.brand-mark::before { width: 22px; height: 7px; }
.brand-mark::after { width: 7px; height: 22px; }
.brand-title { font-size: 1.35rem; font-weight: 700; letter-spacing: 0.02em; line-height: 1.2; }
.brand-sub { font-size: 0.85rem; opacity: 0.8; }
.header-meta { display: flex; gap: 8px; flex-wrap: wrap; }
.hpill {
    display: inline-flex; align-items: center; gap: 7px; font-size: 0.78rem; font-weight: 500;
    background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.22);
    padding: 6px 12px; border-radius: 999px; white-space: nowrap;
}
.hpill .dot { width: 8px; height: 8px; border-radius: 50%; background: #4ADE80; box-shadow: 0 0 0 3px rgba(74,222,128,0.25); }
.hpill .dot.off { background: #F87171; box-shadow: 0 0 0 3px rgba(248,113,113,0.25); }

/* KPI cards */
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
@media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.kpi {
    background: #fff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 16px 18px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.kpi-label { font-size: 0.75rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; }
.kpi-value { font-size: 1.7rem; font-weight: 700; color: #0F172A; margin-top: 6px; line-height: 1.1; }
.kpi-value small { font-size: 0.95rem; font-weight: 500; color: #94A3B8; }
.kpi-sub { font-size: 0.8rem; color: #64748B; margin-top: 6px; }
.kpi-bar { height: 5px; background: #EEF2F6; border-radius: 99px; margin-top: 10px; overflow: hidden; }
.kpi-bar > div { height: 100%; border-radius: 99px; }

/* Cards (keyed Streamlit containers) */
[class*="st-key-card_"] {
    background: #fff; border: 1px solid #E2E8F0; border-radius: 16px;
    padding: 20px 22px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}
.card-title { font-size: 1.05rem; font-weight: 650; color: #0F172A; }
.card-sub { font-size: 0.84rem; color: #64748B; margin-top: 2px; margin-bottom: 6px; }
.section-label {
    font-size: 0.72rem; font-weight: 600; color: #0E7490; text-transform: uppercase;
    letter-spacing: 0.08em; margin: 10px 0 2px 0; padding-top: 10px; border-top: 1px solid #F1F5F9;
}
.section-label.first { border-top: none; padding-top: 0; }
.stApp label p { font-weight: 500; color: #334155; font-size: 0.85rem; }

/* Badges */
.badge {
    display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem; font-weight: 600;
    padding: 4px 10px; border-radius: 999px; white-space: nowrap;
}
.badge.ok { background: #DCFCE7; color: #166534; }
.badge.warn { background: #FEF3C7; color: #92400E; }
.badge.err { background: #FEE2E2; color: #991B1B; }
.badge.muted { background: #F1F5F9; color: #475569; }
.badge.info { background: #E0F2FE; color: #075985; }
.tri-1 { background: #DCFCE7; color: #166534; }
.tri-2 { background: #FEF9C3; color: #854D0E; }
.tri-3 { background: #FFEDD5; color: #9A3412; }
.tri-4, .tri-5 { background: #FEE2E2; color: #991B1B; }

/* Result */
.result-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.patient-name { font-size: 1.2rem; font-weight: 700; color: #0F172A; }
.patient-meta { font-size: 0.85rem; color: #64748B; margin-top: 2px; }
.outcome { border-radius: 12px; padding: 12px 14px; font-size: 0.88rem; margin-bottom: 16px; border: 1px solid; }
.outcome.ok { background: #F0FDF4; border-color: #BBF7D0; color: #166534; }
.outcome.warn { background: #FFFBEB; border-color: #FDE68A; color: #92400E; }
.outcome.err { background: #FEF2F2; border-color: #FECACA; color: #991B1B; }
.detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.detail { background: #F8FAFC; border: 1px solid #EEF2F6; border-radius: 12px; padding: 12px 14px; }
.detail-label { font-size: 0.72rem; color: #64748B; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.detail-value { font-size: 1rem; font-weight: 600; color: #0F172A; margin-top: 5px; }

/* Agent pipeline */
.pipeline { display: flex; align-items: flex-start; margin: 6px 0 4px 0; }
.step { flex: 1; text-align: center; position: relative; }
.step:not(:last-child)::after {
    content: ""; position: absolute; top: 15px; left: calc(50% + 20px); right: calc(-50% + 20px);
    height: 2px; background: #E2E8F0;
}
.step-dot {
    width: 32px; height: 32px; border-radius: 50%; margin: 0 auto; display: flex;
    align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700;
    border: 2px solid; background: #fff;
}
.step-dot.ok { border-color: #16A34A; color: #16A34A; background: #F0FDF4; }
.step-dot.warn { border-color: #D97706; color: #D97706; background: #FFFBEB; }
.step-dot.err { border-color: #DC2626; color: #DC2626; background: #FEF2F2; }
.step-dot.muted { border-color: #CBD5E1; color: #94A3B8; }
.step-name { font-size: 0.78rem; font-weight: 600; color: #334155; margin-top: 8px; }
.step-status { font-size: 0.72rem; color: #64748B; margin-top: 2px; }

/* Execution log */
.log { font-size: 0.82rem; }
.log-row { display: grid; grid-template-columns: 92px 190px 1fr; gap: 10px; padding: 8px 4px; border-bottom: 1px solid #F1F5F9; }
.log-row:last-child { border-bottom: none; }
.log-time { font-family: 'JetBrains Mono', Consolas, monospace; color: #94A3B8; font-size: 0.78rem; }
.log-agent { font-weight: 600; color: #0E7490; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.log-row.err .log-agent, .log-row.err .log-msg { color: #B91C1C; }
.log-msg { color: #334155; }

/* Empty state */
.empty { text-align: center; padding: 28px 10px; color: #64748B; }
.empty-icon {
    width: 48px; height: 48px; border-radius: 14px; background: #ECFEFF; margin: 0 auto 12px auto;
    display: flex; align-items: center; justify-content: center; color: #0E7490; font-size: 1.4rem; font-weight: 700;
}
.empty-title { font-weight: 600; color: #0F172A; margin-bottom: 4px; }

/* Doctors */
.dept-head {
    display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; font-weight: 600;
    color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; margin: 14px 0 6px 0;
}
.dept-head:first-child { margin-top: 2px; }
.doc-row {
    display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid #EEF2F6;
    border-radius: 12px; margin-bottom: 6px; background: #fff;
}
.doc-row.busy { background: #FFFBFA; border-color: #FDE2E2; }
.avatar {
    width: 36px; height: 36px; border-radius: 50%; background: #E0F2FE; color: #075985; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 700;
}
.doc-row.busy .avatar { background: #FEE2E2; color: #991B1B; }
.doc-main { flex: 1; min-width: 0; }
.doc-name { font-size: 0.88rem; font-weight: 600; color: #0F172A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.doc-meta { font-size: 0.76rem; color: #64748B; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Beds */
.bed-row { border: 1px solid #EEF2F6; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; }
.bed-top { display: flex; justify-content: space-between; align-items: baseline; }
.bed-name { font-weight: 600; color: #0F172A; font-size: 0.92rem; }
.bed-count { font-size: 0.82rem; color: #64748B; }
.bed-count b { color: #0F172A; font-size: 1rem; }
.bed-bar { height: 8px; background: #EEF2F6; border-radius: 99px; margin: 10px 0 8px 0; overflow: hidden; }
.bed-bar > div { height: 100%; border-radius: 99px; }
.bed-foot { display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748B; }

.app-footer { text-align: center; color: #94A3B8; font-size: 0.75rem; margin-top: 26px; }
</style>
""", unsafe_allow_html=True)


def triage_label(triage_level):
    if triage_level is None: return "Unknown"
    if triage_level >= 4: return "Critical"
    elif triage_level == 3: return "Urgent"
    elif triage_level == 2: return "Semi-urgent"
    return "Routine"

def capacity_color(percent_free):
    if percent_free > 50: return "#16A34A"
    if percent_free > 20: return "#D97706"
    return "#DC2626"

def initials(name):
    words = [w for w in str(name).replace("Dr.", "").split() if w]
    return "".join(w[0] for w in words[:2]).upper() or "DR"

def format_minutes(minutes):
    if minutes is None:
        return ""
    minutes = float(minutes)
    return "<1 min" if minutes < 1 else f"{round(minutes)} min"

def format_clock(value):
    return value.strftime("%I:%M %p").lstrip("0") if value else ""


def render_header(db_online):
    now = get_current_est_time().strftime("%a, %b %d · %I:%M %p ET")
    db_pill = ('<span class="hpill"><span class="dot"></span>Database online</span>' if db_online
               else '<span class="hpill"><span class="dot off"></span>Database offline</span>')
    st.markdown(
        '<div class="shmas-header">'
        '<div class="brand"><div class="brand-mark"></div><div>'
        '<div class="brand-title">SHMAS</div>'
        '<div class="brand-sub">Smart Hospital Multi-Agent System</div>'
        '</div></div>'
        f'<div class="header-meta">{db_pill}'
        f'<span class="hpill">Model · {esc(GROQ_MODEL)}</span>'
        f'<span class="hpill">{esc(now)}</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_kpis(doctors, beds):
    def kpi(label, value, total, sub, percent=None):
        bar = ""
        if percent is not None:
            bar = f'<div class="kpi-bar"><div style="width:{percent:.0f}%;background:{capacity_color(percent)}"></div></div>'
        total_html = f" <small>/ {total}</small>" if total is not None else ""
        return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
                f'<div class="kpi-value">{value}{total_html}</div>'
                f'<div class="kpi-sub">{sub}</div>{bar}</div>')

    cards = []
    if doctors is not None:
        available = sum(1 for d in doctors if d["status"] == "AVAILABLE")
        total = len(doctors)
        pct = available / total * 100 if total else 0
        cards.append(kpi("Doctors available", available, total, f"{total - available} currently with patients", pct))
    else:
        cards.append(kpi("Doctors available", "—", None, "Unavailable"))

    if beds is not None:
        free = sum(v[0] for v in beds.values())
        total = sum(v[0] + v[1] for v in beds.values())
        pct = free / total * 100 if total else 0
        cards.append(kpi("Beds available", free, total, f"{100 - pct:.0f}% occupancy", pct))
        for bed_type in ("ICU", "Emergency"):
            avail, occ = beds.get(bed_type, (0, 0))
            t = avail + occ
            p = avail / t * 100 if t else 0
            cards.append(kpi(f"{bed_type} beds free", avail, t, f"{occ} occupied", p))
    else:
        cards += [kpi(label, "—", None, "Unavailable") for label in ("Beds available", "ICU beds free", "Emergency beds free")]

    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def display_patient_form():
    with st.container(key="card_admission"):
        st.markdown('<div class="card-title">New patient admission</div>'
                    '<div class="card-sub">Submit patient details and vitals. The agents assess mood, triage the case, '
                    'and allocate a doctor and bed.</div>', unsafe_allow_html=True)
        with st.form("patient_form", clear_on_submit=False, border=False):
            st.markdown('<div class="section-label first">Patient details</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Full name", placeholder="e.g. Jane Doe", max_chars=100)
            with col2:
                email = st.text_input("Email", placeholder="name@example.com", max_chars=100)
            col1, col2 = st.columns(2)
            with col1:
                age = st.number_input("Age", 0, 120, 45)
            with col2:
                gender = st.selectbox("Gender", ["Male", "Female", "Other"])

            st.markdown('<div class="section-label">Clinical presentation</div>', unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                symptoms_text = st.text_area("Symptoms (comma separated)",
                                             placeholder="e.g. chest pain, shortness of breath", height=96)
            with col2:
                duration = st.number_input("Duration (hours)", 0, 720, 2)

            st.markdown('<div class="section-label">Vital signs</div>', unsafe_allow_html=True)
            vital_cols = st.columns(3)
            with vital_cols[0]:
                systolic = st.number_input("Systolic BP (mmHg)", 60, 250, 120)
            with vital_cols[1]:
                diastolic = st.number_input("Diastolic BP (mmHg)", 40, 150, 80)
            with vital_cols[2]:
                hr = st.number_input("Heart rate (bpm)", 30, 200, 80)

            submitted = st.form_submit_button("Run triage and admit", type="primary",
                                              icon=":material/emergency:", width="stretch")

        if submitted:
            name = name.strip()
            email = email.strip().lower()
            symptoms = [s.strip() for s in symptoms_text.split(",") if s.strip()]

            validation_errors = []
            if not name:
                validation_errors.append("Patient name is required.")
            if not EMAIL_PATTERN.match(email):
                validation_errors.append("Please enter a valid email address.")
            if not symptoms:
                validation_errors.append("Please enter at least one symptom.")
            if not 0 <= age <= 120:
                validation_errors.append("Age must be between 0 and 120.")
            if not 0 <= duration <= 720:
                validation_errors.append("Symptom duration must be between 0 and 720 hours.")
            if validation_errors:
                st.error("\n".join(f"- {error}" for error in validation_errors))
                return

            vitals = {
                "blood_pressure": {"systolic": systolic, "diastolic": diastolic},
                "heart_rate": hr
            }

            with st.spinner("Agents are processing the admission..."):
                try:
                    result = run_patient_flow(
                        name=name,
                        symptoms=symptoms,
                        vitals=vitals,
                        symptom_duration=duration,
                        age=age,
                        gender=gender,
                        email = email
                    )
                except SHMASError as e:
                    st.error(str(e))
                    return
                except Exception:
                    logger.exception("Unexpected error during admission")
                    st.error("An unexpected error occurred while processing the admission. Please try again.")
                    return

            st.session_state['last_patient'] = result["patient"].to_dict()
            st.session_state['logs'] = result["logs"]
            st.session_state['status'] = dict(result["status"])
            st.session_state['show_results'] = True
            st.rerun()


def render_pipeline(status):
    steps = []
    for idx, (key, label) in enumerate(PIPELINE, start=1):
        state = status.get(key, "Pending")
        tone = STATUS_TONE.get(state, "muted")
        mark = {"ok": "✓", "err": "✕", "warn": "!"}.get(tone, str(idx))
        steps.append(f'<div class="step"><div class="step-dot {tone}">{mark}</div>'
                     f'<div class="step-name">{label}</div><div class="step-status">{esc(state)}</div></div>')
    st.markdown(f'<div class="pipeline">{"".join(steps)}</div>', unsafe_allow_html=True)


def render_logs(logs):
    rows = []
    for log in logs:
        timestamp, message = "", log
        if log.startswith("[") and "]" in log:
            timestamp, message = log[1:].split("]", 1)
        agent, _, text = message.strip().partition(" : ")
        if not text:
            agent, text = "", agent
        tone = "err" if ("error" in text.lower() or "failed" in text.lower()) else ""
        agent_label = re.sub(r"Agent$", "", agent)
        agent_label = re.sub(r"(?<!^)(?=[A-Z])", " ", agent_label)
        rows.append(f'<div class="log-row {tone}"><div class="log-time">{esc(timestamp)}</div>'
                    f'<div class="log-agent">{esc(agent_label)}</div><div class="log-msg">{esc(text)}</div></div>')
    st.markdown(f'<div class="log">{"".join(rows)}</div>', unsafe_allow_html=True)


def display_patient_results():
    with st.container(key="card_result"):
        if not (st.session_state.get('show_results') and st.session_state.get('last_patient')):
            st.markdown('<div class="card-title">Admission result</div>'
                        '<div class="empty"><div class="empty-icon">+</div>'
                        '<div class="empty-title">No admissions in this session yet</div>'
                        'Submit the form to see triage, allocation and the full agent trace.</div>',
                        unsafe_allow_html=True)
            return

        patient = st.session_state['last_patient']
        status = st.session_state.get('status', {})
        outcome_state = status.get("ConflictResolver", "Pending")
        outcome = {
            "Success": ("ok", "Admitted", "A doctor and a bed have been assigned. The case is now active."),
            "Queued": ("warn", "Queued", "Required resources are currently unavailable. The patient was added to the priority waiting queue."),
        }.get(outcome_state, ("err", "Not admitted",
                              "The admission could not be completed. Review the execution log below for details."))
        tone, outcome_label, outcome_text = outcome

        level = patient['triage_level']
        triage_html = (f'<span class="badge tri-{level}">Level {level} · {triage_label(level)}</span>'
                       if level is not None else '<span class="badge muted">Not determined</span>')

        def detail(label, value_html):
            return f'<div class="detail"><div class="detail-label">{label}</div><div class="detail-value">{value_html}</div></div>'

        meta = " · ".join(esc(x) for x in (f"{patient['age']} yrs", patient['gender'], patient['email']) if x)
        st.markdown(
            f'<div class="result-head"><div><div class="card-title" style="margin-bottom:8px">Admission result</div>'
            f'<div class="patient-name">{esc(patient["name"])}</div><div class="patient-meta">{meta}</div></div>'
            f'<span class="badge {tone}">{outcome_label}</span></div>'
            f'<div class="outcome {tone}">{outcome_text}</div>'
            '<div class="detail-grid">'
            + detail("Triage", triage_html)
            + detail("Department", esc(patient['department'] or "—"))
            + detail("Priority score", esc(patient['priority_score']))
            + detail("Assigned doctor", esc(patient['assigned_doctor'] or "—"))
            + detail("Assigned bed", esc(patient['assigned_bed'] or "—"))
            + detail("Detected mood", esc((patient['mood'] or "—").capitalize()))
            + '</div><div class="section-label first">Agent pipeline</div>',
            unsafe_allow_html=True,
        )
        render_pipeline(status)
        with st.expander("Execution log", icon=":material/terminal:"):
            render_logs(st.session_state.get('logs', []))


def render_doctors(doctors):
    if doctors is None:
        st.error("Unable to load doctor status from the database right now.")
        return
    if not doctors:
        st.info("No doctors found. Run `seed_data.sql` to add sample doctors.")
        return

    by_dept = {}
    for doc in doctors:
        by_dept.setdefault(doc['department'] or "Other", []).append(doc)

    parts = []
    for dept, docs in by_dept.items():
        available = sum(1 for d in docs if d['status'] == "AVAILABLE")
        parts.append(f'<div class="dept-head"><span>{esc(dept)}</span><span>{available}/{len(docs)} available</span></div>')
        for doc in docs:
            if doc['status'] == "BUSY":
                meta = f"With {esc(doc['with_patient'] or 'a patient')}"
                if doc['finish_time']:
                    meta += f" · until {esc(format_clock(doc['finish_time']))}"
                left = format_minutes(doc['time_remaining'])
                badge = f'<span class="badge err">Busy{" · " + esc(left) if left else ""}</span>'
                row_cls = "doc-row busy"
            else:
                meta = "Ready for next patient"
                badge = '<span class="badge ok">Available</span>'
                row_cls = "doc-row"
            parts.append(f'<div class="{row_cls}"><div class="avatar">{esc(initials(doc["doctor_name"]))}</div>'
                         f'<div class="doc-main"><div class="doc-name">{esc(doc["doctor_name"])}</div>'
                         f'<div class="doc-meta">{meta}</div></div>{badge}</div>')
    with st.container(height=520, border=False):
        st.markdown("".join(parts), unsafe_allow_html=True)


def render_beds(beds):
    if beds is None:
        st.error("Unable to load bed status from the database right now.")
        return
    if not beds:
        st.info("No rooms found. Run `seed_data.sql` to add sample rooms.")
        return

    parts = []
    ordered = [t for t in BED_ORDER if t in beds] + [t for t in beds if t not in BED_ORDER]
    for bed_type in ordered:
        available_beds, occupied_beds = beds[bed_type][0], beds[bed_type][1]
        total_beds = available_beds + occupied_beds
        availability_percent = (
            available_beds / total_beds * 100
            if total_beds > 0
            else 0
        )
        parts.append(
            f'<div class="bed-row"><div class="bed-top"><span class="bed-name">{esc(str(bed_type).replace("_", " "))}</span>'
            f'<span class="bed-count"><b>{available_beds}</b> of {total_beds} available</span></div>'
            f'<div class="bed-bar"><div style="width:{availability_percent:.0f}%;background:{capacity_color(availability_percent)}"></div></div>'
            f'<div class="bed-foot"><span>{occupied_beds} occupied</span><span>{availability_percent:.0f}% free</span></div></div>'
        )
    st.markdown("".join(parts), unsafe_allow_html=True)


def display_resources(doctors, beds):
    with st.container(key="card_resources"):
        head, action = st.columns([3, 1.3], vertical_alignment="center")
        with head:
            st.markdown('<div class="card-title">Hospital resources</div>'
                        '<div class="card-sub">Live doctor availability and bed capacity</div>', unsafe_allow_html=True)
        with action:
            if st.button("Refresh", icon=":material/refresh:", width="stretch", key="refresh_btn"):
                st.rerun()
        doctors_tab, beds_tab = st.tabs(["Doctors", "Beds"])
        with doctors_tab:
            render_doctors(doctors)
        with beds_tab:
            render_beds(beds)


def load_resources():
    try:
        doctors = get_doctor_status()
    except Exception:
        logger.exception("Unable to load doctor status")
        doctors = None
    try:
        beds = get_beds()
    except Exception:
        logger.exception("Unable to load bed status")
        beds = None
    return doctors, beds


def main():
    for key, default in (("last_patient", None), ("logs", []), ("status", {}), ("show_results", False)):
        if key not in st.session_state:
            st.session_state[key] = default

    db_online = database_is_available()
    render_header(db_online)

    if not db_online:
        database_is_available.clear()
        st.error("The hospital database is currently unreachable. Check the DATABASE_URL setting and that the database is running, then refresh the page.")
        st.stop()

    doctors, beds = load_resources()
    render_kpis(doctors, beds)

    col1, col2 = st.columns([1.55, 1], gap="large")
    with col1:
        display_patient_form()
        st.write("")
        display_patient_results()
    with col2:
        display_resources(doctors, beds)

    st.markdown('<div class="app-footer">SHMAS · LangGraph multi-agent workflow · Groq LLM · PostgreSQL</div>',
                unsafe_allow_html=True)

if __name__ == "__main__":
    main()
