from flask import Flask, request, render_template
import os
import re
import PyPDF2
import docx2txt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------- TEXT EXTRACTION ---------------------------- #

def extract_text_pdf(file_path):
    text = ""
    with open(file_path,'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text

def extract_text_docs(file_path):
    try:
        return docx2txt.process(file_path) or ""
    except Exception:
        return ""

def extract_text_txt(file_path):
    try:
        with open(file_path,'r',encoding='utf-8') as file:
            return file.read()
    except Exception:
        return ""

def extract_text(file_path):
    file_path = file_path.lower()
    if file_path.endswith('.pdf'):
        return extract_text_pdf(file_path)
    elif file_path.endswith('.docx'):
        return extract_text_docs(file_path)
    elif file_path.endswith('.txt'):
        return extract_text_txt(file_path)
    else:
        return ""

# ---------------------------- SKILL EXTRACTION (ROBUST) ---------------------------- #

# A mapping from canonical skill -> list of regex patterns that should match it.
SKILL_PATTERNS = {
    "python": [r"\bpython\b"],
    "java": [r"\bjava\b"],
    "c++": [r"\bc\+\+\b"],
    "c#": [r"\bc#\b", r"\bc sharp\b"],
    "sql": [r"\bsql\b", r"\bstructured query language\b"],
    "html": [r"\bhtml\b"],
    "css": [r"\bcss\b"],
    "javascript": [r"\bjavascript\b", r"\bjs\b"],
    "react": [r"\breact\b", r"\breactjs\b", r"\breact.js\b"],
    "node": [r"\bnode\b", r"\bnodejs\b", r"\bnode\.js\b"],
    "flask": [r"\bflask\b"],
    "django": [r"\bdjango\b"],
    "machine learning": [r"\bmachine learning\b", r"\bml\b"],
    "deep learning": [r"\bdeep learning\b", r"\bdl\b"],
    "nlp": [r"\bnlp\b", r"\bnatural language processing\b"],
    "tensorflow": [r"\btensorflow\b"],
    "keras": [r"\bkeras\b"],
    "data analysis": [r"\bdata analysis\b", r"\bdata analyst\b", r"\bdata analytics\b"],
    "power bi": [r"\bpower bi\b", r"\bpowerbi\b"],
    "excel": [r"\bexcel\b"],
    "communication": [r"\bcommunication\b", r"\bcommunicative\b"],
    "leadership": [r"\bleadership\b", r"\bleader\b"],
    "git": [r"\bgit\b"],
    "linux": [r"\blinux\b"],
    "cloud": [r"\bcloud\b"],
    "aws": [r"\baws\b", r"\bamazon web services\b"],
    "azure": [r"\bazure\b", r"\bmicrosoft azure\b"],
    "docker": [r"\bdocker\b"],
    "kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "react native": [r"\breact native\b"],
    "rest api": [r"\brest api\b", r"\brestful\b", r"\bapi\b"],
    "opencv": [r"\bopencv\b"],
    "pandas": [r"\bpandas\b"],
    "numpy": [r"\bnumpy\b"],
    "matplotlib": [r"\bmatplotlib\b"],
    "scikit-learn": [r"\bscikit[- ]?learn\b", r"\bsklearn\b"],
    "excel vba": [r"\bvba\b", r"\bexcel vba\b"]
}

# Compile patterns to regex objects once
_COMPILED_SKILLS = {
    skill: [re.compile(pat, flags=re.IGNORECASE) for pat in pats]
    for skill, pats in SKILL_PATTERNS.items()
}

def normalize_text_for_skills(text: str) -> str:
    if not text:
        return ""
    # Replace common separators with spaces, keep + and # for C++/C#
    text = re.sub(r"[\n\r\t,;/\(\)\[\]\{\}:<>\-]", " ", text)
    # Convert multiple spaces to single
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()

def extract_skills(text: str):
    """
    Return a set of canonical skills found in the text using regex patterns.
    This function is robust to punctuation, capitalization, and short-hands.
    """
    text_norm = normalize_text_for_skills(text)
    found = set()
    for skill, patterns in _COMPILED_SKILLS.items():
        for pat in patterns:
            if pat.search(text_norm):
                found.add(skill)
                break
    return found

# ---------------------------- FLASK APP ---------------------------- #

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

@app.route('/')
def matchresume():
    return render_template("app.html") 

@app.route('/upload', methods=['POST'])
def upload():
    # support both names: 'resumeText' (existing) and 'jobDescription' (safe fallback)
    jd = request.form.get('resumeText') or request.form.get('jobDescription') or ""
    resume_files = request.files.getlist('resumeFile')

    resumes = []
    resume_names = []

    # save and extract text from uploaded resumes
    for resume_file in resume_files:
        # skip empty filenames
        if not resume_file or resume_file.filename == "":
            continue
        safe_name = os.path.basename(resume_file.filename)
        filename = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        # ensure upload folder exists
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        resume_file.save(filename)
        text = extract_text(filename) or ""
        resumes.append(text)
        resume_names.append(safe_name)

    if len(resumes) == 0 or not jd.strip():
        return render_template(
            'app.html',
            message="Please upload at least one resume and enter a job description"
        )

    # TF–IDF vectorizing (JD + resumes)
    vec = TfidfVectorizer().fit_transform([jd] + resumes)
    vectors = vec.toarray()

    jd_vec = vectors[0]
    resume_vecs = vectors[1:]

    sim = cosine_similarity([jd_vec], resume_vecs)[0]

    # Convert to percentage 0-100
    percentage_scores = [round(float(score) * 100, 2) for score in sim]

    # Get top 3 indexes (safe if fewer than 3 resumes)
    n = len(sim)
    top_k = min(3, n)
    top_indexes = sim.argsort()[-top_k:][::-1]

    top_resumes = [resume_names[i] for i in top_indexes]
    top_scores = [percentage_scores[i] for i in top_indexes]

    # Skill Recommendations
    jd_skills = extract_skills(jd)
    resume_skills_list = [extract_skills(r) for r in resumes]

    # Build recommendations aligned to top indexes
    recommendations = []
    for i in top_indexes:
        missing = sorted(list(jd_skills - resume_skills_list[i]))
        extra = sorted(list(resume_skills_list[i] - jd_skills))
        recommendations.append({
            "missing": missing,
            "extra": extra
        })

    return render_template(
        'app.html',
        message="Top matching resumes:",
        top_r=top_resumes,
        similarity_scores=top_scores,
        recommendations=recommendations
    )


if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
