# -*- coding: utf-8 -*-
"""N: 시험지 인벤토리 v3 → SQLite DB
- 포맷 A: [학교][학년][과목][YY-학기-회차][출판사]
- 포맷 B: [22][고1][1학기중간][수학상][대구여고]
- 포맷 C: 대구여자고등학교_1학년_2019_1학기기말_수학(상)_공통_문제_정답
- 제외는 최소한(명백한 교재/답지/폼지/비수학)만. 나머지는 파싱 성공 여부로 판정.
"""
import re, sys, io, json, sqlite3, collections, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = pathlib.Path(__file__).parent
DB = BASE / "exam_index.db"
rows = [l.split("\t") for l in (BASE / "n_inventory.tsv").read_text(encoding="utf-8-sig").splitlines() if l.strip()]

BRACKET = re.compile(r"\[([^\[\]]+)\]")
# 학기토큰 변형: 25-1-기말 / 2025-1-기말 / 24년-1중간 / 24-1-1기말 / 25-1-기말고사대비
TERM = re.compile(r"^(?:20)?(\d{2})\s*년?\s*[-.]?\s*([12])\s*학?기?\s*[-.]?\s*(?:[12]\s*)?(중간|기말)")
TERM_REV = re.compile(r"^(?:20)?(\d{2})\s*[-.]\s*(중간|기말)\s*[-.]\s*([12])$")   # 25-중간-2
OLD_YEAR = re.compile(r"^(\d{2})$")
OLD_GRADE = re.compile(r"^([중고])([1-3])$")
OLD_TERM = re.compile(r"^([12])학기\s*(중간|기말)$")
# 포맷 C: 학교명_N학년_YYYY_M학기중간_과목_...
UNDER = re.compile(r"^(.+?(?:학교|고|중))_([1-3])학년_(20\d{2})_([12])학기(중간|기말)_([^_]*)")

# 명백한 비시험지만 제외 (워드 폴더 = 완료본이므로 제외하지 않는다)
NOT_EXAM_PATH = re.compile(
    r"교과서|개념마스터|연산교재|RPM|쎈\b|보드게임|악보|웨딩|BGM|타블 카드|내 그림|"
    r"제작 툴|academy-app|Making|수익 프로젝트|4g SD|CAFE|WOW|경복궁|박세미|녹화본")
NOT_EXAM_NAME = re.compile(
    r"교사용|열람용|폼지|대수회|수준별|진도학습|편집자료|편집충돌|개념마스터|"
    r"^\[정답\]|^\[해설\]|모의고사|라이트 본문|교재")

SUBJ_ALIAS = {
    "수학1":"수1","수학I":"수1","수I":"수1","수학2":"수2","수학II":"수2","수II":"수2",
    "수학상":"수상","수학(상)":"수상","수(상)":"수상","수학 상":"수상","고등상":"수상",
    "수학하":"수하","수학(하)":"수하","수(하)":"수하",
    "미적":"미적분","확률과통계":"확통","확률과 통계":"확통",
    "공통수학1":"공수1","공통수학2":"공수2","공수":"공수1","공통수학":"공수1",
    "심화수학1":"심화수학","심수":"심화수학","수힉":"수학",
}
def norm_subj(s):
    if not s: return None
    s = s.strip()
    return SUBJ_ALIAS.get(s, s)

def parse(path: str):
    p = pathlib.Path(path); name = p.stem; parent = str(p.parent)
    rec = dict(path=path, ext=p.suffix.lower(), school=None, grade=None, level=None,
               subject=None, year=None, semester=None, round=None, publisher=None,
               status=None, fmt=None)
    if NOT_EXAM_PATH.search(parent) or NOT_EXAM_NAME.search(name):
        rec["fmt"] = "notexam"; return rec

    st = re.findall(r"\(([^()]*)\)\s*$", name)
    rec["status"] = st[0].strip() if st else None
    toks = [t.strip() for t in BRACKET.findall(name)]

    # 포맷 C (언더바)
    mc = UNDER.match(name)
    if mc and not toks:
        sch = mc.group(1)
        sch = (sch.replace("여자고등학교","여고").replace("고등학교","고")
                  .replace("여자중학교","여중").replace("중학교","중"))
        rec.update(school=sch, grade=int(mc.group(2)), year=int(mc.group(3)),
                   semester=int(mc.group(4)), round=mc.group(5),
                   subject=norm_subj(mc.group(6)), fmt="C")
    elif toks:
        ti = next((i for i, t in enumerate(toks) if TERM.match(t) or TERM_REV.match(t)), None)
        if ti is not None:
            t = toks[ti]
            m = TERM.match(t)
            if m:
                rec.update(year=2000+int(m.group(1)), semester=int(m.group(2)), round=m.group(3))
            else:
                m = TERM_REV.match(t)
                rec.update(year=2000+int(m.group(1)), round=m.group(2), semester=int(m.group(3)))
            rec["school"] = toks[0]
            if len(toks) > 1 and re.fullmatch(r"[1-3]", toks[1]):
                rec["grade"] = int(toks[1])
            if ti >= 1 and not re.fullmatch(r"[1-3]", toks[ti-1]):
                rec["subject"] = norm_subj(toks[ti-1])
            if ti+1 < len(toks):
                rec["publisher"] = toks[ti+1]
            rec["fmt"] = "A"
        else:
            y = g = t2 = school = subj = None; lvl = None
            for tk in toks:
                if OLD_YEAR.match(tk) and y is None: y = 2000+int(tk)
                elif OLD_GRADE.match(tk):
                    mm = OLD_GRADE.match(tk); g = int(mm.group(2)); lvl = mm.group(1)
                elif OLD_TERM.match(tk):
                    mm = OLD_TERM.match(tk); t2 = (int(mm.group(1)), mm.group(2))
                elif re.search(r"(고|중|여고|여중)$", tk) and len(tk) >= 2 and not re.fullmatch(r"[1-3]", tk):
                    school = tk
                elif norm_subj(tk) in {"수1","수2","수상","수하","확통","미적분","공수1",
                                       "공수2","기하","심화수학","수학","경제수학"}:
                    subj = norm_subj(tk)
            if y and g and t2 and school:
                rec.update(year=y, grade=g, school=school, subject=subj, level=lvl,
                           semester=t2[0], round=t2[1], fmt="B")
            else:
                rec["fmt"] = "unparsed"; return rec
    else:
        rec["fmt"] = "nobracket"; return rec

    sch = rec["school"] or ""
    if rec["level"] is None:
        rec["level"] = "중" if re.search(r"(중|여중)$", sch) else ("고" if re.search(r"(고|여고)$", sch) else None)
    if rec["subject"] is None and rec["level"] == "중":
        rec["subject"] = "수학"
    return rec

parsed = [parse(r[0]) for r in rows]
sizes = {r[0]: int(r[1]) for r in rows}
mtimes = {r[0]: r[2] for r in rows}

print("=== 파싱 결과 ===")
for k, v in collections.Counter(r["fmt"] for r in parsed).most_common():
    print(f"  {k}: {v}")

good = [r for r in parsed if r["fmt"] in ("A","B","C")
        and r["school"] and r["grade"] and r["year"] and r["round"] and r["level"]]
recent = [r for r in good if r["year"] >= 2020]
print(f"\n시험지 확정: {len(good)}   2020년 이후: {len(recent)}")

def rank(r):
    s = r["status"] or ""
    base = 0 if "완료" in s else (1 if "원본" in s else (2 if "수정" in s else 3))
    return (base, 0 if r["ext"] == ".pdf" else 1, -sizes.get(r["path"], 0))

def key(r):
    return (r["level"], r["school"], r["grade"], r["subject"] or "?", r["year"], r["semester"], r["round"])

groups = collections.defaultdict(list)
for r in recent: groups[key(r)].append(r)
print(f"고유 시험지: {len(groups)}   (중복 {len(recent)-len(groups)}편 제거)")

# ---- SQLite ----
if DB.exists(): DB.unlink()
con = sqlite3.connect(DB); cur = con.cursor()
cur.executescript("""
CREATE TABLE exams(
  id INTEGER PRIMARY KEY, level TEXT, school TEXT, grade INT, subject TEXT,
  year INT, semester INT, round TEXT, publisher TEXT, status TEXT,
  src_path TEXT, src_ext TEXT, size INT, needs_pdf_convert INT DEFAULT 0,
  variant_count INT, ocr_status TEXT DEFAULT 'pending',
  question_count INT DEFAULT 0, solution_status TEXT DEFAULT 'pending');
CREATE TABLE exam_files(
  id INTEGER PRIMARY KEY, exam_id INT, path TEXT, ext TEXT, size INT,
  status TEXT, is_primary INT, mtime TEXT,
  FOREIGN KEY(exam_id) REFERENCES exams(id));
CREATE TABLE questions(
  id INTEGER PRIMARY KEY, exam_id INT, number INT, qtype TEXT,
  ocr_json TEXT, answer TEXT, solution TEXT, topic TEXT, difficulty TEXT,
  FOREIGN KEY(exam_id) REFERENCES exams(id));
CREATE INDEX ix_exams_meta ON exams(year, level, grade, semester, round, subject);
CREATE INDEX ix_exams_school ON exams(school);
CREATE INDEX ix_q_exam ON questions(exam_id);
""")

for k, g in sorted(groups.items(), key=lambda x: (x[0][4], x[0][0], x[0][2], x[0][1])):
    best = sorted(g, key=rank)[0]
    has_pdf = any(r["ext"] == ".pdf" for r in g)
    cur.execute("""INSERT INTO exams(level,school,grade,subject,year,semester,round,
        publisher,status,src_path,src_ext,size,needs_pdf_convert,variant_count)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (best["level"], best["school"], best["grade"], best["subject"], best["year"],
         best["semester"], best["round"], best["publisher"], best["status"],
         best["path"], best["ext"], sizes.get(best["path"], 0),
         0 if has_pdf else 1, len(g)))
    eid = cur.lastrowid
    for r in g:
        cur.execute("""INSERT INTO exam_files(exam_id,path,ext,size,status,is_primary,mtime)
            VALUES(?,?,?,?,?,?,?)""",
            (eid, r["path"], r["ext"], sizes.get(r["path"],0), r["status"],
             1 if r["path"] == best["path"] else 0, mtimes.get(r["path"], "")))
con.commit()

print(f"\n=== DB: {DB} ===")
for q, label in [
    ("SELECT COUNT(*) FROM exams", "고유 시험지"),
    ("SELECT COUNT(*) FROM exam_files", "원본 파일(변형 포함)"),
    ("SELECT COUNT(*) FROM exams WHERE needs_pdf_convert=1", "HWP뿐(PDF 변환 필요)"),
]:
    print(f"  {label}: {cur.execute(q).fetchone()[0]}")

def show(sql, title):
    print(f"\n--- {title} ---")
    for row in cur.execute(sql):
        print("  " + "  ".join(str(x) for x in row))

show("SELECT year, COUNT(*) FROM exams GROUP BY year ORDER BY year", "연도별")
show("SELECT level, grade, COUNT(*) FROM exams GROUP BY level,grade ORDER BY level,grade", "학교급·학년별")
show("SELECT semester, round, COUNT(*) FROM exams GROUP BY semester,round ORDER BY semester,round", "학기·중간기말별")
show("SELECT subject, COUNT(*) c FROM exams GROUP BY subject ORDER BY c DESC LIMIT 15", "과목별(상위15)")
show("SELECT COUNT(DISTINCT school) FROM exams", "학교 수")
show("SELECT SUM(size)/1024/1024/1024 FROM exams", "1차 대상 총 GB")
con.close()
