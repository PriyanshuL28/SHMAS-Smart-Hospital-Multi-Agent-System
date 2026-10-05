from typing import TypedDict, List
from contextlib import contextmanager
from langchain_core.messages import HumanMessage
import os, random, json, re
from langchain_groq import ChatGroq
import pytz
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import errors as pg_errors
from dotenv import load_dotenv
import logging
from logging import debug

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from .env locally, Streamlit Secrets / env vars on cloud)
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. Set it in a .env file (local) "
        "or in Streamlit Community Cloud > App > Settings > Secrets."
    )

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not configured. Set it in a .env file (local) "
        "or in Streamlit Community Cloud > App > Settings > Secrets."
    )

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Python timestamps and PostgreSQL TIMESTAMP (without time zone) columns must
# share the same zone, otherwise refresh_data() compares mismatched wall clocks.
APP_TIMEZONE = "America/New_York"

DEPARTMENTS = ["Cardiology", "Pediatrics", "Neurology", "Dentist"]
ROOM_TYPES = ["Emergency", "ICU", "Ward", "Normal"]
MOOD_EMOJI = {"calm": "😌", "frustrated": "😖", "anxious": "😥",
              "stressed": "😧", "confused": "😵‍💫", "panicked": "🫨"}


# ---------------------------------------------------------------------------
# Errors surfaced to the Streamlit UI (never include credentials)
# ---------------------------------------------------------------------------
class SHMASError(Exception):
    """Base class for errors that are safe to show to the user."""


class DatabaseUnavailableError(SHMASError):
    pass


class DuplicatePatientError(SHMASError):
    pass


class PatientRegistrationError(SHMASError):
    pass


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except psycopg2.OperationalError as e:
        logger.warning("Database connection failed: %s", type(e).__name__)
        raise DatabaseUnavailableError(
            "Could not connect to the database. Check DATABASE_URL and that the database is reachable."
        ) from None
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE %s;", (APP_TIMEZONE,))
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        logger.warning("Could not set session time zone to %s: %s", APP_TIMEZONE, type(e).__name__)
    return conn


@contextmanager
def db_transaction():
    """Yield a cursor on a fresh connection; commit on success, rollback on error, always close."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_database_connection():
    try:
        with db_transaction() as cursor:
            cursor.execute("SELECT 1;")
            return True
    except Exception:
        return False


def get_beds():
    query = """
        SELECT DISTINCT type,
                (SELECT COUNT(*) FROM rooms r1 WHERE r1.type = r.type AND is_occupied = FALSE) available,
                (SELECT COUNT(*) FROM rooms r1 WHERE r1.type = r.type AND is_occupied = TRUE) blocked 
        FROM rooms r;
        """
    with db_transaction() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    output = {}
    for data in rows:
        output[data[0]] = data[1:]
    return output

def get_doctor_status():
    debug("Getting doctor status update...")
    query = """
        SELECT
            d.name doctor_name,
            d.specialist department,
            (CASE WHEN d.is_busy=TRUE THEN 'BUSY' ELSE 'AVAILABLE' END) status,
            (CASE WHEN d.is_busy=TRUE THEN p.patient_name ELSE NULL END) with_patient,
            (CASE WHEN d.is_busy=TRUE THEN ROUND(EXTRACT(EPOCH FROM (d.busy_till - CURRENT_TIMESTAMP)) / 60,2) ELSE NULL END) time_remaining,
            (CASE WHEN d.is_busy=TRUE THEN d.busy_till ELSE NULL END) finish_time,
            (CASE WHEN d.is_busy=TRUE THEN d.busy_from ELSE NULL END) start_time
        FROM doctors d
        LEFT JOIN ongoing_cases oc
        ON d.doctor_id = oc.doctor_id
        LEFT JOIN patient_info p
        ON oc.patient_id = p.patient_id
        ORDER BY d.specialist, d.name;
    """
    with db_transaction() as cursor:
        cursor.execute("SELECT refresh_data();")
        cursor.execute(query)
        rows = cursor.fetchall()
    output = []
    cols = ["doctor_name","department","status","with_patient","time_remaining","finish_time","start_time"]
    for i in range(len(rows)):
        temp_dict = {}
        for idx, data in enumerate(rows[i]):
            temp_dict[cols[idx]] = data
        output.append(temp_dict)
    return output


def patient_email_exists(email):
    with db_transaction() as cursor:
        cursor.execute("SELECT 1 FROM patient_info WHERE LOWER(email) = LOWER(%s);", (email,))
        return cursor.fetchone() is not None


def release_doctor(doctor_id):
    with db_transaction() as cursor:
        cursor.execute(
            "UPDATE doctors SET is_busy = FALSE, busy_from = NULL, busy_till = NULL WHERE doctor_id = %s;",
            (doctor_id,),
        )


def release_room(room_number):
    with db_transaction() as cursor:
        cursor.execute("UPDATE rooms SET is_occupied = FALSE WHERE room_number = %s;", (room_number,))


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
def create_llm():
    return ChatGroq(api_key=GROQ_API_KEY, model_name=GROQ_MODEL)


def extract_json_object(text, required_keys):
    """Return the first JSON object in an LLM reply that contains all required keys, else None."""
    if isinstance(text, list):
        text = "".join(part if isinstance(part, str) else str(part.get("text", ""))
                       for part in text if isinstance(part, (str, dict)))
    if not isinstance(text, str):
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and all(k in obj for k in required_keys):
            return obj
    return None


def get_block_duration(triage_level):
    return timedelta(minutes=max(1, triage_level))

def get_current_est_time():
    est = pytz.timezone(APP_TIMEZONE)
    return datetime.now(est)

def get_current_time_with_ms():
    return datetime.now(pytz.timezone(APP_TIMEZONE)).strftime('%H:%M:%S.%f')[:-3]

class Patient:
    def __init__(self, name, vitals, email, gender, age, symptoms, symptom_duration):
        self.name = name
        self.symptoms = symptoms
        self.symptom_duration = symptom_duration
        self.email = email
        self.phone = None
        self.age = age
        self.vitals = vitals
        self.gender = gender
        self.mood = None
        self.triage_level = None
        self.department = None
        self.assigned_doctor = None
        self.assigned_bed = None
        self.bed_priority = None
        self.priority_score = 0.0
        self.entry_time = get_current_est_time()
        self.treatment_completed = False
        self.treatment_end_time = None

    def calculate_priority(self):
        triage_weight = 10
        triage_score = (self.triage_level or 0) * triage_weight
        
        if self.age >= 50:
            age_score = 8
        elif self.age < 15:
            age_score = 5
        else:
            age_score = 0
            
        hr = self.vitals.get("heart_rate", 80)
        bp_sys = self.vitals.get("blood_pressure", {}).get("systolic", 120)
        bp_dia = self.vitals.get("blood_pressure", {}).get("diastolic", 80)
        
        hr_dev = max(hr - 100, 60 - hr, 0)
        bp_sys_dev = abs(bp_sys - 120) if bp_sys > 140 or bp_sys < 90 else 0
        bp_dia_dev = abs(bp_dia - 80) if bp_dia > 90 or bp_dia < 60 else 0
        vital_score = (hr_dev + bp_sys_dev + bp_dia_dev) * 0.7
        
        duration_score = self.symptom_duration * 0.2
        
        self.priority_score = round(triage_score + age_score + vital_score + duration_score, 1)

    def to_dict(self):
        self.calculate_priority()
        return {
            "name": self.name,
            "symptoms": self.symptoms,
            "symptom_duration": self.symptom_duration,
            "contact_number": self.phone,
            "age": self.age,
            "email": self.email,
            "gender": self.gender,
            "mood": self.mood,
            "triage_level": self.triage_level,
            "department": self.department,
            "assigned_doctor": self.assigned_doctor,
            "assigned_bed": self.assigned_bed,
            "priority_score": self.priority_score,
            "treatment_completed": self.treatment_completed,
            "treatment_end_time": self.treatment_end_time.strftime('%H:%M:%S.%f')[:-3] if self.treatment_end_time else None,
            "entry_time": self.entry_time.strftime('%H:%M:%S.%f')[:-3]
        }

class AgentState(TypedDict):
    patient: Patient
    logs: List[str]
    status: dict
    cache: dict

def adjust_mood_based_on_vitals(patient, detected_mood):
    symptoms_str = " ".join(patient.symptoms).lower()
    if patient.vitals["heart_rate"] > 120 or patient.vitals["blood_pressure"].get("diastolic",80) < 80:
        detected_mood = "panicked"
    elif "cardiac arrest" in symptoms_str:
        detected_mood = "panicked"
    elif "mild cough" in symptoms_str and patient.vitals["heart_rate"] < 100:
        detected_mood = "calm"
    return detected_mood

class MentalHealthAnalyzerAgent:
    def __init__(self):
        self._GROQ_API_KEY = GROQ_API_KEY
        self.llm = create_llm()

    def register_patient(self, patient):
        query = """
            INSERT INTO patient_info(patient_name, email, phone, gender, symptoms, symptoms_duration, vitals)
            VALUES (%s, %s, NULL, %s, %s, %s, %s::jsonb)
            RETURNING patient_id;
        """
        try:
            with db_transaction() as cursor:
                cursor.execute(query, (
                    patient.name,
                    patient.email,
                    patient.gender,
                    ", ".join(patient.symptoms),
                    str(patient.symptom_duration),
                    json.dumps(patient.vitals),
                ))
                return cursor.fetchone()[0]
        except pg_errors.UniqueViolation:
            raise DuplicatePatientError(
                f"A patient with the email '{patient.email}' is already registered. "
                "Please use a different email address."
            ) from None
        except psycopg2.Error as e:
            logger.error("Patient registration failed: %s", type(e).__name__)
            raise PatientRegistrationError(
                "The patient could not be registered because of a database error. Please try again."
            ) from None

    def __call__(self, state: AgentState) -> AgentState:
        debug(f"Entering {self.__class__.__name__} call...")
        patient = state["patient"]
        blood_pressure = patient.vitals.get("blood_pressure", {})
        systolic = blood_pressure.get("systolic", 120)
        diastolic = blood_pressure.get("diastolic", 80)

        state["cache"]["patient_id"] = self.register_patient(patient)
        debug("Patient information inserted successfully...")
        prompt = f"""Analyze patient's emotional state based on:
        - Vitals: BP {systolic}/{diastolic}, HR {patient.vitals.get("heart_rate", 80)}
        - Symptoms: {patient.symptoms}
        - Duration: {patient.symptom_duration} hours
        - Age: {patient.age}
        Choose one mood from {list(MOOD_EMOJI)}.
        Return JSON: {{ "mood": "chosen_mood" }}"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            debug("Got mood estimate from LLM...")
            mood_info = extract_json_object(response.content, ["mood"])
            if mood_info is None:
                raise ValueError("LLM response did not contain a valid mood JSON object")
            detected_mood = adjust_mood_based_on_vitals(patient, str(mood_info["mood"]).strip().lower())
            patient.mood = detected_mood
            debug("Successfully completed task. Updating status...")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Detected Mood is {patient.mood} {MOOD_EMOJI.get(patient.mood, '')}")
            state["status"]["MoodAnalyzer"] = "Success"
        except Exception as e:
            debug(f"Error estimating the mood...\n{e}")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Error estimating the mood : {str(e)}")
            state["status"]["MoodAnalyzer"] = "Failed"
        debug(f"Exiting {self.__class__.__name__} call...")
        return state

class EmergencyTriageAgent:
    def __init__(self):
        self._GROQ_API_KEY = GROQ_API_KEY
        self.llm = create_llm()
    
    def __call__(self, state: AgentState) -> AgentState:
        debug(f"Entering {self.__class__.__name__} call...")
        patient = state["patient"]
        bp = patient.vitals.get("blood_pressure", {})
        hr = patient.vitals.get("heart_rate", 80)
        prompt = f"""Assign triage_level (1-5) and department based on:
        - Symptoms: {patient.symptoms}
        - BP: {bp.get('systolic', 120)}/{bp.get('diastolic', 80)}
        - HR: {hr}
        - Mood: {patient.mood}
        - Age: {patient.age}
        - Duration: {patient.symptom_duration}h
        Return JSON: {{"triage_level": number, "department": "string"}}
        return value of department should be in {DEPARTMENTS}"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            debug("Got triage level from the LLM...")
            triage_info = extract_json_object(response.content, ["triage_level", "department"])
            if triage_info is None:
                raise ValueError("LLM response did not contain a valid triage JSON object")

            triage_level = int(float(triage_info["triage_level"]))
            if not 1 <= triage_level <= 5:
                raise ValueError(f"triage_level {triage_level} is outside 1-5")
            department = next((d for d in DEPARTMENTS
                               if d.lower() == str(triage_info["department"]).strip().lower()), None)
            if department is None:
                raise ValueError(f"Unknown department '{triage_info['department']}'")

            patient.triage_level = triage_level
            patient.department = department
            debug(f"triage level : {triage_level}, department : {department}")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Level {patient.triage_level} -> {patient.department}")
            state["status"]["EmergencyTriage"] = "Success"
        except Exception as e:
            debug(f"Error estimating the triage...\n{e}")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Error estimating the triage : {str(e)}")
            state["status"]["EmergencyTriage"] = "Failed"
        debug(f"Exiting {self.__class__.__name__} call...")
        return state

class DoctorSchedulerAgent:
    def __call__(self, state: AgentState) -> AgentState:
        debug(f"Entering {self.__class__.__name__} call...")
        patient = state["patient"]
        dept = patient.department
        if state["status"].get("EmergencyTriage") != "Success" or dept not in DEPARTMENTS:
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Skipped because triage failed.")
            state["status"]["DoctorScheduler"] = "Skipped"
            return state

        now = get_current_est_time()
        blocked_until = now + get_block_duration(patient.triage_level)
        debug(f"Attempting to fetch available {dept} specialist doctors...")
        try:
            with db_transaction() as cursor:
                cursor.execute("SELECT * FROM get_available_doctors(%s);", (dept,))
                available = cursor.fetchall()
                random.shuffle(available)
                assigned_doctor_details = None
                # Conditional update so two concurrent admissions cannot claim the same doctor.
                for candidate in available:
                    cursor.execute("""
                        UPDATE doctors SET is_busy = TRUE, busy_from = %s, busy_till = %s
                        WHERE doctor_id = %s AND is_busy = FALSE
                        RETURNING doctor_id;
                    """, (now, blocked_until, candidate[0]))
                    if cursor.fetchone():
                        assigned_doctor_details = candidate
                        break
        except psycopg2.Error as e:
            logger.error("Doctor allocation failed: %s", type(e).__name__)
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Database error while assigning a doctor.")
            state["status"]["DoctorScheduler"] = "Failed"
            return state

        if assigned_doctor_details:
            patient.assigned_doctor = assigned_doctor_details[1]
            state["cache"]["doctor_assigned"] = assigned_doctor_details
            state["cache"]["doctor_blocked_from"] = now
            state["cache"]["doctor_blocked_until"] = blocked_until
            debug("Successfully alloted doctor...")
            state["status"]["DoctorScheduler"] = "Success"
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Assigned {patient.assigned_doctor} to {patient.name}")
        else:
            debug("No doctors available...")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : No {dept} doctor available.")
            state["status"]["DoctorScheduler"] = "Failed"
        debug(f"Exiting {self.__class__.__name__} call...")
        return state

class BedManagerAgent:
    def __call__(self, state: AgentState) -> AgentState:
        debug(f"Entering {self.__class__.__name__} call...")
        patient = state["patient"]
        level = patient.triage_level
        if state["status"].get("EmergencyTriage") != "Success" or level is None:
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Skipped because triage failed.")
            state["status"]["BedManager"] = "Skipped"
            return state

        if level == 5:
            patient.bed_priority = ["ICU", "Emergency"]
        elif level in [3, 4]:
            patient.bed_priority = ["Ward", "Emergency"]
        else:
            patient.bed_priority = ["Normal", "Ward", "Emergency"]

        try:
            with db_transaction() as cursor:
                for bed_type in patient.bed_priority:
                    debug(f"Checking bed type {bed_type}...")
                    cursor.execute("SELECT * FROM get_available_rooms(%s::room_type);", (bed_type,))
                    available_bed_details = cursor.fetchall()
                    # Conditional update so two concurrent admissions cannot claim the same room.
                    for room in available_bed_details:
                        cursor.execute("""
                            UPDATE rooms SET is_occupied = TRUE
                            WHERE room_number = %s AND is_occupied = FALSE
                            RETURNING room_number;
                        """, (room[0],))
                        if cursor.fetchone():
                            patient.assigned_bed = room[0]
                            state["cache"]["bed_assigned"] = room
                            state["cache"]["bed_type"] = bed_type
                            break
                    if patient.assigned_bed is not None:
                        break
        except psycopg2.Error as e:
            logger.error("Bed allocation failed: %s", type(e).__name__)
            patient.assigned_bed = None
            state["cache"].pop("bed_assigned", None)
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Database error while assigning a bed.")
            state["status"]["BedManager"] = "Failed"
            return state

        if patient.assigned_bed is not None:
            debug("Successfully allocated a bed...")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : {patient.name} assigned to {state['cache']['bed_type']} bed {patient.assigned_bed} (triage {level})")
            state["status"]["BedManager"] = "Success"
        else:
            debug("No beds found...")
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : No beds available for {patient.name}")
            state["status"]["BedManager"] = "Failed"
        debug(f"Exiting {self.__class__.__name__} call...")
        return state
    
class ConflictResolverAgent:
    def _release_resources(self, state, release_doctor_flag, release_bed_flag):
        patient = state["patient"]
        if release_doctor_flag and state["cache"].get("doctor_assigned"):
            release_doctor(state["cache"]["doctor_assigned"][0])
            patient.assigned_doctor = None
            debug("Reverted the allocated doctor...")
        if release_bed_flag and patient.assigned_bed is not None:
            release_room(patient.assigned_bed)
            patient.assigned_bed = None
            debug("Reverted the allocated bed...")

    def _queue_patient(self, state, room_type):
        patient = state["patient"]
        with db_transaction() as cursor:
            cursor.execute("""
                INSERT INTO queue(patient_id, priority_score, type_of_room)
                VALUES (%s, %s, %s::room_type);
            """, (state["cache"]["patient_id"], patient.priority_score, room_type))
        debug("Application queued...")

    def __call__(self, state: AgentState) -> AgentState:
        debug(f"Entering {self.__class__.__name__} call...")
        patient = state["patient"]
        bed_status = state["status"].get("BedManager")
        doctor_status = state["status"].get("DoctorScheduler")
        doctor_allocated = doctor_status == "Success"
        bed_allocated = bed_status == "Success"
        debug("Checking for conflicts in decision making...")
        patient.calculate_priority()
        debug(f"Calculated priority score : {patient.priority_score}")
        state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Calculated priority score : {patient.priority_score}")

        try:
            if state["status"].get("EmergencyTriage") != "Success":
                state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Admission failed because triage could not be determined. Please retry.")
                state["status"]["ConflictResolver"] = "Failed"
            elif doctor_allocated and bed_allocated:
                debug("No conflicts found. Attempting to create a case...")
                with db_transaction() as cursor:
                    cursor.execute("""
                        INSERT INTO ongoing_cases(patient_id, doctor_id, room_number)
                        VALUES (%s, %s, %s);
                    """, (state["cache"]["patient_id"], state["cache"]["doctor_assigned"][0], patient.assigned_bed))
                doctor_allocated = bed_allocated = False
                state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Assigning available doctor and bed to {patient.name}")
                state["status"]["ConflictResolver"] = "Success"
            elif bed_allocated and not doctor_allocated:
                debug("There's a conflict!! Doctor not available at this moment. Queuing the admission form...")
                queue_room_type = state["cache"]["bed_type"]
                self._release_resources(state, release_doctor_flag=False, release_bed_flag=True)
                bed_allocated = False
                self._queue_patient(state, queue_room_type)
                state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : No doctors available at this moment. Queuing the application.")
                state["status"]["ConflictResolver"] = "Queued"
            elif doctor_allocated and not bed_allocated:
                debug("There's a conflict!! Bed not available at this moment. Queuing the admission form...")
                self._release_resources(state, release_doctor_flag=True, release_bed_flag=False)
                doctor_allocated = False
                self._queue_patient(state, patient.bed_priority[0])
                state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : No beds available at this moment. Queuing the application.")
                state["status"]["ConflictResolver"] = "Queued"
            else:
                debug("There's a conflict!! No bed or doctor available at this moment. Please try at nearby hospitals...")
                state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : No beds and doctors available at this moment. Please try at nearby hospitals.")
                state["status"]["ConflictResolver"] = "Failed"
        except Exception as e:
            logger.error("Conflict resolution failed: %s", type(e).__name__)
            try:
                self._release_resources(state, release_doctor_flag=doctor_allocated, release_bed_flag=bed_allocated)
            except Exception as release_error:
                logger.error("Releasing resources failed: %s", type(release_error).__name__)
            state["logs"].append(f"[{get_current_time_with_ms()}] {self.__class__.__name__} : Error finalizing the admission. Allocated resources were released.")
            state["status"]["ConflictResolver"] = "Failed"
        debug(f"Exiting {self.__class__.__name__} call...")
        return state
