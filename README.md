# SHMAS: Smart Hospital Multi-Agent System

## Inspiration

In the fast-paced world of healthcare, even the smallest delays in hospital operations can have life-or-death consequences. With multiple processes happening simultaneously—patient triage, resource allocation, and doctor scheduling—hospital workflows can quickly become overwhelmed. Our solution to this complex problem? SHMAS (Smart Hospital Multi-Agent System). This innovative system leverages the power of AI and multi-agent coordination to streamline hospital operations, reduce wait times, and ultimately enhance patient care. By automating and optimizing key tasks, SHMAS ensures that hospital staff can focus on providing care, rather than managing logistics. When tasked with building a multi-agent system, we saw an opportunity to not only improve operational efficiency but also save lives by making critical decisions faster and with greater accuracy.

## What it does

*SHMAS (Smart Hospital Multi-Agent System)* is an AI-driven system designed to automate and optimize hospital workflows using multiple autonomous agents. Each agent is responsible for handling a specific part of the hospital's operations, from patient triage to resource allocation and conflict resolution. The system ensures that tasks are completed efficiently, minimizing delays in patient care and optimizing hospital resources. Key features include:

- *Mental Health State Detection*: The system evaluates the urgency of patient cases based on real-time medical data, enabling intelligent prioritization.
- *Agent Collaboration*: Five different agents collaborate to handle specific tasks, share data, and make decisions in real-time.
- *Conflict Resolution*: The system automatically resolves resource conflicts when demand exceeds supply, ensuring optimal resource allocation.
- *Real-Time Dashboarding*: Hospital staff receive live updates on workflow progress, patient statuses, and agent activities.
- *Priority Scoring Formula*: A dynamic scoring system prioritizes patients in waiting queues based on vital signs, age, and symptoms, ensuring critical cases are addressed first.

### The Five Agents:
1. *Mental Health Analyzer Agent*: Analyzes patient data to assess mental health conditions, prioritizing cases based on urgency.
2. *Triage Agent*: Helps prioritize patient cases based on severity, ensuring critical patients are directed to the appropriate department.
3. *Bed Manager Agent*: Manages available hospital beds, allocating them based on patient severity and available resources.
4. *Doctor Scheduler Agent*: Automates the scheduling of doctors based on patient needs and doctor availability.
5. *Conflict Resolver*: Resolves resource allocation conflicts when multiple agents require the same resources.

## How we built it

We built SHMAS using a combination of AI techniques and tools that allowed for the seamless interaction and orchestration of multiple agents. The tech stack and approach included:

- *LangGraph*: This was used to structure and orchestrate the workflows of our five agents, ensuring clear transitions and proper coordination.
- *Groq APIs*: We integrated large language models (LLMs) via Groq to process data and support decision-making.
  - The Groq model is configurable through the `GROQ_MODEL` setting (default: `openai/gpt-oss-120b`).
- *Database Management: We used **PostgreSQL* to store and retrieve hospital data securely, ensuring that multiple agents could work with up-to-date and consistent information.
- *Real-Time Updates*: We built a dynamic dashboard to display live information on patient statuses, agent activities, and workflow progress.
- *Priority Score Formula*: We designed and implemented an algorithm that assigns priority scores to patients based on vital signs, symptom severity, and other factors to ensure the right patients are treated first.

## Challenges we ran into

- *Agent Orchestration*: Managing the interactions between multiple agents with interdependencies posed a challenge. Coordinating these agents in real-time required careful state management.  
  *Solution: We implemented **LangGraph* to ensure smooth coordination and transition between agents, allowing them to collaborate effectively while avoiding conflicts.

- *Conflict Resolution*: High-demand situations led to resource contention, creating edge cases where multiple agents wanted to access the same resources.  
  *Solution: We developed a sophisticated **priority scoring system* that factors in multiple variables like patient vitals, age, and symptom severity to prioritize patients appropriately during peak times.

- *Real-Time Data Handling*: Ensuring real-time data updates while avoiding data inconsistency between multiple agents was a complex issue.  
  *Solution: We utilized **transaction management* and *database triggers* to prevent race conditions and ensure consistent data across agents.

- *LLM Integration*: Integrating LLMs within hospital protocols posed challenges in terms of balancing flexibility and deterministic processes.  
  *Solution: We designed precise prompts and implemented **post-processing validation* to ensure that LLM outputs were accurate and aligned with the needs of hospital operations.

## Accomplishments that we're proud of

- *Mental Health Detection and Prioritization*: We successfully developed a system that evaluates the urgency of patient cases and prioritizes them accordingly.
- *AI Agent Collaboration*: We designed and implemented five autonomous agents that communicate and collaborate effectively to handle various hospital processes.
- *Real-Time Dashboarding*: Our real-time dashboard provides valuable insights into hospital workflows, enhancing operational visibility and decision-making.
- *Innovative Priority Score Formula*: We created an innovative algorithm for prioritizing patients in waiting queues, factoring in various aspects such as vitals, age, and symptom severity.
- *Conflict Resolution System*: We built an automated conflict resolution mechanism that optimizes resource allocation in high-demand scenarios without human intervention.

## What we learned

Throughout this project, we gained insights into several key areas:

- *AI Agents*: How to design and implement multiple AI agents that can operate autonomously while collaborating and resolving conflicts in real-time.
- *Communication Between AI Agents*: We explored how agents can communicate effectively, sharing data and making decisions that align with the hospital’s priorities.
- *LLM Integration: How to call and integrate large language models (LLMs) using APIs like **Groq* for data processing and decision-making.
- *LangGraph*: We learned how LangGraph can help orchestrate and structure agent workflows, ensuring clear state transitions and coordinated agent activities.
- *Hospital Intricacies*: We gained a deep understanding of the challenges hospitals face, such as resource management, patient prioritization, and workflow bottlenecks.

## What's next for SHMAS: Smart Hospital Multi-Agent System

The current implementation demonstrates the core functionality of the multi-agent system, but several enhancements could further improve the system:

- *Machine learning models* to predict patient flow and optimize resource allocation.
- *Integration with electronic health records* for more comprehensive patient history.
- *Real-time notifications and alerts* for critical resource shortages.
- Expanded *dashboard with predictive analytics* for hospital administration.
- *Mobile interface* for staff to monitor and manage patient flow remotely.

---

## Project structure

```text
SHMAS-Smart-Hospital-Multi-Agent-System/
├── shmas/
│   ├── agents.py               # Agents, DB helpers, configuration
│   ├── smart_hospital.py       # LangGraph workflow + run_patient_flow()
│   ├── streamlit_dashboard.py  # Streamlit entrypoint
│   ├── hospitals_db.sql        # Schema: types, tables, functions, trigger
│   └── seed_data.sql           # Synthetic doctors and rooms
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Architecture:

```text
Browser → Streamlit Community Cloud → streamlit_dashboard.py → LangGraph
                                                                ├── Groq API
                                                                └── Supabase PostgreSQL
```

## Configuration

All settings are read from environment variables. Nothing secret lives in the source code.

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection URL (Supabase Session Pooler recommended) |
| `GROQ_API_KEY` | Yes | Groq API key from https://console.groq.com/keys |
| `GROQ_MODEL` | No | Groq model name, defaults to `openai/gpt-oss-120b` |
| `LOG_LEVEL` | No | Python log level, defaults to `INFO` (use `DEBUG` for agent traces) |

Locally these come from a `.env` file in the repository root; on Streamlit Community Cloud they come from the app's Secrets.

## Supabase setup (do this first)

1. Create a project at https://supabase.com and note the database password you choose.
2. In the Supabase dashboard open **SQL Editor → New query**.
3. Paste the contents of `shmas/hospitals_db.sql` and click **Run**.
   - This creates the `room_type` / `comm_type` enums, the `patient_info`, `rooms`, `doctors`, `ongoing_cases` and `queue` tables, the `release_room_and_doctor_status()`, `refresh_data()`, `get_available_doctors()` and `get_available_rooms()` functions, and the `release_case_trigger` trigger.
   - **Warning:** re-running this file drops and recreates all SHMAS tables (all data is lost).
4. Open a new query, paste `shmas/seed_data.sql` and click **Run**. It is safe to re-run; existing rows are skipped. Edit doctor names and room counts there if you like, but keep the specialties (`Cardiology`, `Pediatrics`, `Neurology`, `Dentist`) and room types (`Emergency`, `ICU`, `Ward`, `Normal`) exactly as they are.
5. Click **Connect** (top of the project page) and copy the **Session pooler** connection string. It looks like:
   ```text
   postgresql://postgres.<project-ref>:<YOUR-PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
   Use the Session pooler rather than the Direct connection: the direct host is IPv6-only, which Streamlit Community Cloud cannot reach.
6. Replace `<YOUR-PASSWORD>` with your database password and append `?sslmode=require`:
   ```text
   postgresql://postgres.<project-ref>:<YOUR-PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   If the password contains special characters (`@`, `:`, `/`, `#`, `%`, `?`), URL-encode them (for example `@` → `%40`), or reset the password to one using only letters and digits.
7. Put this URL into `DATABASE_URL` (in `.env` locally, Secrets on Streamlit Cloud).
8. Test locally first (next section) before deploying.

The schema enables Row Level Security on every table without adding policies. This blocks Supabase's public REST API from reading patient data, while the app, which connects as the `postgres` table owner, keeps full access.

## Local development

```bash
git clone <your-repo-url>
cd SHMAS-Smart-Hospital-Multi-Agent-System
python -m venv .venv
```

Activate the virtual environment.

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and create your `.env`:

```bash
pip install -r requirements.txt
```

Windows (PowerShell): `Copy-Item .env.example .env` · macOS/Linux: `cp .env.example .env`

Edit `.env` and fill in the real `DATABASE_URL` and `GROQ_API_KEY`. Then run:

```bash
streamlit run shmas/streamlit_dashboard.py
```

The app opens at http://localhost:8501. If the database is unreachable the dashboard shows an error banner instead of crashing.

## Deploying to Streamlit Community Cloud

1. Make sure `.env` is **not** committed (it is listed in `.gitignore`), then push the project to GitHub.
2. Go to https://share.streamlit.io and click **Create app → Deploy a public app from GitHub**.
3. Select the repository and branch.
4. Set **Main file path** to `shmas/streamlit_dashboard.py`.
5. Open **Advanced settings**, choose Python 3.12 (3.11+ is required), and paste into **Secrets**:
   ```toml
   DATABASE_URL = "postgresql://postgres.<project-ref>:<YOUR-PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
   GROQ_API_KEY = "your_groq_api_key"
   GROQ_MODEL = "openai/gpt-oss-120b"
   ```
   Top-level Streamlit secrets are exposed as environment variables, so the code reads them with `os.getenv(...)` exactly as it does locally. Secrets can later be changed under **App → Settings → Secrets**.
6. Click **Deploy**. Streamlit installs `requirements.txt` from the repository root automatically.

## Notes and limitations

- An email address can be registered only once (`patient_info.email` is `UNIQUE`). Submitting an existing email shows an error instead of overwriting the patient.
- Each database operation opens a short-lived connection and closes it, so sessions never share a cursor. Every connection sets its time zone to `America/New_York` so Python timestamps and PostgreSQL `TIMESTAMP` columns line up (Supabase defaults to UTC).
- Doctors and rooms are claimed with conditional updates (`... WHERE is_busy = FALSE`), so two simultaneous admissions cannot grab the same resource.
- Doctor busy time is `triage_level` minutes, and `refresh_data()` releases doctors once that time has passed (it runs whenever the doctor status panel loads).
