import streamlit as st
import pandas as pd
import pdfplumber
import docx
import re
import plotly.graph_objects as go
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from io import BytesIO
import os
import json
from datetime import datetime
from xml.sax.saxutils import escape
import bcrypt   

st.set_page_config(page_title="PathFinder", layout="wide", page_icon="🧠")


# -------------------------------------
# PERSISTENT STORAGE (JSON FILE)
# -------------------------------------
USERS_FILE = "users.json"


def load_users_file():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            os.rename(USERS_FILE, USERS_FILE + ".bak")
            return {}
    return {}


def save_users_file(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Initialize session state
if "users" not in st.session_state:
    st.session_state.users = load_users_file()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_user" not in st.session_state:
    st.session_state.current_user = None


# -------------------------------------
# AUTHENTICATION (WITH HASHING)
# -------------------------------------
def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def auth_page():
    st.title("🔐 Login / Register")

    tab1, tab2 = st.tabs(["Login", "Register"])

    # LOGIN
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):
            users = st.session_state.users

            if username in users:
                stored_hash = users[username]["password"]

                if verify_password(password, stored_hash):
                    st.session_state.logged_in = True
                    st.session_state.current_user = username
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Incorrect password!")
            else:
                st.error("User not found!")

    # REGISTER
    with tab2:
        new_user = st.text_input("New Username", key="reg_user")
        new_pass = st.text_input("New Password", type="password", key="reg_pass")

        if st.button("Register"):
            if not new_user:
                st.error("Please enter a username")
            elif new_user in st.session_state.users:
                st.error("Username already exists!")
            else:
                hashed_password = hash_password(new_pass)

                st.session_state.users[new_user] = {
                    "password": hashed_password,
                    "history": [],
                    "profile_url": "https://cdn-icons-png.flaticon.com/512/3177/3177440.png"
                }

                save_users_file(st.session_state.users)
                st.success("Account created! You can now login.")


# If not logged in → show auth
if not st.session_state.logged_in:
    auth_page()
    st.stop()


# -------------------------------------
# SIDEBAR PROFILE + HISTORY + LOGOUT
# -------------------------------------
def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.rerun()


with st.sidebar:
    curr_user = st.session_state.current_user
    data = st.session_state.users[curr_user]

    st.markdown("### 👤 Profile")
    st.image(data["profile_url"], width=80)
    st.write(f"**Username:** `{curr_user}`")

    st.markdown("---")
    st.markdown("### 📜 My History")

    history = data.get("history", [])

    if not history:
        st.write("No history yet.")
    else:
        for h in reversed(history[-50:]):
            with st.expander(f"{h['timestamp']} — {h['match']}% match"):
                st.write("**Resume Skills:**", ", ".join(h["resume"]))
                st.write("**Job Skills:**", ", ".join(h["job"]))
                st.write("**Missing:**", ", ".join(h["missing"]))

    st.markdown("---")
    if st.button("Clear My History"):
        st.session_state.users[curr_user]["history"] = []
        save_users_file(st.session_state.users)
        st.success("History cleared.")
        st.rerun()

    st.markdown("---")
    if st.button("Logout"):
        logout()


# -------------------------------------
# PathFinder LOGIC (UNCHANGED)
# -------------------------------------

skill_keywords = [
    'python', 'java', 'c++', 'sql', 'machine learning', 'deep learning',
    'data analysis', 'data visualization', 'excel', 'tableau', 'power bi',
    'communication', 'teamwork', 'leadership', 'cloud', 'aws', 'azure',
    'react', 'javascript', 'node', 'html', 'css', 'nlp', 'statistics'
]


@st.cache_data
def load_courses():
    coursera = pd.read_csv("datasets/coursera.csv")
    udemy = pd.read_csv("datasets/udemy.csv")
    return coursera, udemy


coursera, udemy = load_courses()


def extract_skills(text):
    text = str(text).lower()
    return list({s for s in skill_keywords if re.search(r'\b' + re.escape(s) + r'\b', text)})


def extract_text_from_pdf(file):
    with pdfplumber.open(file) as pdf:
        return " ".join([page.extract_text() or "" for page in pdf.pages])


def extract_text_from_docx(file):
    doc_file = docx.Document(file)
    return " ".join([para.text for para in doc_file.paragraphs])


def suggest_courses(missing_skills):
    suggestions = []

    for skill in missing_skills:
        c = coursera[coursera['course_title'].str.contains(skill, case=False, na=False)]
        u = udemy[udemy['course_title'].str.contains(skill, case=False, na=False)]
        coursera_url = f"https://www.coursera.org/search?query={skill}"
        udemy_url = f"https://www.udemy.com/courses/search/?q={skill}"

        if not c.empty:
            row = c.iloc[0]
            suggestions.append({
                "Skill": skill,
                "Platform": "Coursera",
                "Course": row["course_title"],
                "URL": coursera_url
            })
        elif not u.empty:
            row = u.iloc[0]
            suggestions.append({
                "Skill": skill,
                "Platform": "Udemy",
                "Course": row["course_title"],
                "URL": udemy_url
            })

    return pd.DataFrame(suggestions)


def generate_pdf(resume_skills, job_skills, matched, missing, match_percent, course_df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>PathFinder Report</b>", styles['Title']))
    story.append(Paragraph(f"<b>Match Percentage:</b> {match_percent}%", styles['Heading2']))
    story.append(Paragraph("<b>Resume Skills:</b> " + ", ".join(resume_skills), styles['BodyText']))
    story.append(Paragraph("<b>Job Required Skills:</b> " + ", ".join(job_skills), styles['BodyText']))
    story.append(Paragraph("<b>Matched Skills:</b> " + ", ".join(matched), styles['BodyText']))
    story.append(Paragraph("<b>Missing Skills:</b> " + ", ".join(missing), styles['BodyText']))

    story.append(Paragraph("<br/><b>Recommended Courses:</b>", styles['Heading2']))

    if not course_df.empty:
        for _, row in course_df.iterrows():
            story.append(Paragraph(
                f"<b>{row['Skill']}</b> — {row['Course']} ({row['Platform']})<br/>{escape(row['URL'])}<br/><br/>",
                styles['BodyText'],
            ))

    doc.build(story)
    buffer.seek(0)
    return buffer


# -------------------------------------
# MAIN UI
# -------------------------------------
st.markdown("<h1 style='text-align:center;color:#1f4e79;'>🧠PathFinderr — Resume & Job Match Analyzer</h1>",
            unsafe_allow_html=True)

uploaded_file = st.file_uploader("📄 Upload Resume (PDF or Word)", type=["pdf", "docx"])
job_description = st.text_area("💼 Paste Job Description here", height=160)


if uploaded_file and job_description:

    resume_text = (
        extract_text_from_pdf(uploaded_file)
        if uploaded_file.type == "application/pdf"
        else extract_text_from_docx(uploaded_file)
    )

    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)

    matched_skills = list(set(resume_skills) & set(job_skills))
    missing_skills = list(set(job_skills) - set(resume_skills))

    match_percent = round((len(matched_skills) / len(job_skills) * 100), 2) if job_skills else 0

    st.subheader(f"🎯 Skill Match: {match_percent}%")
    st.progress(match_percent / 100 if job_skills else 0)

    col1, col2 = st.columns(2)

    with col1:
        st.write("### 📄 Resume Skills")
        st.dataframe(pd.DataFrame({"Resume Skills": resume_skills}))

    with col2:
        st.write("### 💼 Job Skills")
        st.dataframe(pd.DataFrame({"Job Skills": job_skills}))

    fig = go.Figure(data=[
        go.Bar(name='Resume', x=['Skills'], y=[len(resume_skills)]),
        go.Bar(name='Job', x=['Skills'], y=[len(job_skills)]),
        go.Bar(name='Matched', x=['Skills'], y=[len(matched_skills)])
    ])
    fig.update_layout(barmode='group')
    st.plotly_chart(fig, use_container_width=True)

    pie = go.Figure(data=[go.Pie(
        labels=["Matched", "Missing"],
        values=[len(matched_skills), len(missing_skills)],
        hole=0.3
    )])
    st.plotly_chart(pie, use_container_width=True)

    course_df = suggest_courses(missing_skills)

    if not course_df.empty:
        st.write("### 📘 Recommended Courses")
        st.dataframe(course_df)
    else:
        st.success("🎉 All required skills matched!")

    pdf_buffer = generate_pdf(
        resume_skills, job_skills, matched_skills, missing_skills, match_percent, course_df
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "timestamp": timestamp,
        "match": match_percent,
        "resume": resume_skills,
        "job": job_skills,
        "missing": missing_skills,
    }

    st.session_state.users[curr_user]["history"].append(entry)
    save_users_file(st.session_state.users)

    st.download_button(
        "📥 Download PDF Report",
        pdf_buffer,
        file_name=f"PathFinder_Report_{curr_user}_{timestamp.replace(':','-').replace(' ','_')}.pdf",
        mime="application/pdf"
    )
