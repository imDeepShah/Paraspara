from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from .agent_service import analyse_need

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.getenv("PARASPARA_DB",ROOT/"data"/"paraspara.db"))
DB.parent.mkdir(parents=True,exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat()
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
    with connect() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,need TEXT NOT NULL,language TEXT NOT NULL,status TEXT NOT NULL,private_plan TEXT NOT NULL,analysis TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consents(case_id TEXT PRIMARY KEY,approved INTEGER NOT NULL,preferences TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,kind TEXT NOT NULL,summary TEXT NOT NULL,availability TEXT NOT NULL,verified INTEGER NOT NULL);
""")
        if not c.execute("SELECT 1 FROM offers LIMIT 1").fetchone():
            c.executemany("INSERT INTO offers VALUES(?,?,?,?,?)",[("offer_transport_01","transport","Woman volunteer with accessible car","Friday 08:00–15:00",1),("fund_mobility_01","fund","Medical mobility pool","12 journeys available",1),("partner_clinic_01","verification","Clinic coordination desk","Weekdays",1)])
init_db()

class CaseCreate(BaseModel):
    need:str=Field(min_length=8,max_length=1200)
    language:Literal["en","hi","gu"]="en"
    actor:Literal["person","supporter","care_partner","review_lead","funder"]="person"
    ai_processing_consent:bool=False
class Consent(BaseModel):
    approved:bool
    preferences:dict={}
class Action(BaseModel):
    actor:Literal["person","supporter","care_partner","review_lead","funder"]
    action:Literal["confirm","offer","verify","escalate","resolve","fund","close"]
    detail:str=Field(min_length=2,max_length=500)

app=FastAPI(title="Paraspara API",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:8765","http://localhost:8765"],allow_methods=["*"],allow_headers=["*"])

def event(c,case_id,actor,action,detail):
    c.execute("INSERT INTO events(case_id,actor,action,detail,created_at) VALUES(?,?,?,?,?)",(case_id,actor,action,detail,now()))

@app.get("/api/health")
def health(): return {"status":"ok","database":str(DB),"ai_mode":os.getenv("PARASPARA_AI_MODE","local")}

@app.post("/api/cases",status_code=201)
def create_case(body:CaseCreate):
    if os.getenv("PARASPARA_AI_MODE","local")=="strands" and not body.ai_processing_consent:
        raise HTTPException(400,"Explicit consent is required before text is sent to the AI provider.")
    case_id="case_"+uuid.uuid4().hex[:12]
    analysis=analyse_need(body.need,body.language,body.actor)
    plan=analysis["private_plan"]; t=now()
    with connect() as c:
        c.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",(case_id,body.need,body.language,"awaiting_consent",plan,json.dumps(analysis,ensure_ascii=False),t,t))
        event(c,case_id,"paraspara_ai","interpreted","Drafted a private plan; no identity disclosed.")
    return {"id":case_id,"status":"awaiting_consent","private_plan":plan,"ai":analysis,"human_decision_required":"Approve or edit this interpretation."}

@app.get("/api/cases/{case_id}")
def get_case(case_id:str,persona:Literal["person","supporter","care_partner","review_lead","funder"]="person"):
    with connect() as c:
        row=c.execute("SELECT * FROM cases WHERE id=?",(case_id,)).fetchone()
        if not row: raise HTTPException(404,"Case not found")
        d=dict(row); analysis=json.loads(d.pop("analysis"))
        if persona=="person": return {**d,"analysis":analysis}
        public={"id":d["id"],"status":d["status"],"support_type":analysis["dana_type"],"constraints":analysis["shareable_constraints"],"updated_at":d["updated_at"]}
        if persona=="care_partner": public["safe_plan"]=d["private_plan"]
        if persona=="review_lead": public["ethical_review"]=analysis["safeguards"]
        if persona=="funder": return {"status":d["status"],"support_type":analysis["dana_type"],"capacity_required":analysis["capacity_required"],"recipient_identity":"withheld"}
        return public

@app.post("/api/cases/{case_id}/consent")
def set_consent(case_id:str,body:Consent):
    with connect() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=?",(case_id,)).fetchone(): raise HTTPException(404,"Case not found")
        c.execute("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)",(case_id,int(body.approved),json.dumps(body.preferences,ensure_ascii=False),now()))
        status="matching" if body.approved else "needs_revision"
        c.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?",(status,now(),case_id))
        event(c,case_id,"person","consent_approved" if body.approved else "revision_requested",json.dumps(body.preferences,ensure_ascii=False))
    return {"id":case_id,"status":status,"identity_shared":False}

@app.post("/api/cases/{case_id}/actions")
def act(case_id:str,body:Action):
    next_status={"offer":"capacity_found","verify":"safety_checked","escalate":"human_review","resolve":"ready","fund":"capacity_funded","close":"completed","confirm":"confirmed"}[body.action]
    with connect() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=?",(case_id,)).fetchone(): raise HTTPException(404,"Case not found")
        c.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?",(next_status,now(),case_id)); event(c,case_id,body.actor,body.action,body.detail)
    return {"id":case_id,"status":next_status,"human_actor":body.actor}

@app.get("/api/cases/{case_id}/audit")
def audit(case_id:str):
    with connect() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=?",(case_id,)).fetchone(): raise HTTPException(404,"Case not found")
        return {"case_id":case_id,"events":[dict(x) for x in c.execute("SELECT actor,action,detail,created_at FROM events WHERE case_id=? ORDER BY id",(case_id,))]}

class PersonaInterpret(BaseModel):
    text:str=Field(min_length=2,max_length=1200)
    language:Literal["en","hi","gu"]="en"
    actor:Literal["supporter","care_partner","review_lead","funder"]
    ai_processing_consent:bool=False

@app.post("/api/cases/{case_id}/interpret")
def interpret_for_persona(case_id:str,body:PersonaInterpret):
    if os.getenv("PARASPARA_AI_MODE","local")=="strands" and not body.ai_processing_consent:
        raise HTTPException(400,"Explicit consent is required before text is sent to the AI provider.")
    with connect() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=?",(case_id,)).fetchone():
            raise HTTPException(404,"Start by creating a request as the person seeking support.")
        analysis=analyse_need(body.text,body.language,body.actor)
        event(c,case_id,"paraspara_ai","interpreted_"+body.actor,"Prepared a role-specific interpretation; no new case created.")
    return {"id":case_id,"status":"ready_for_"+body.actor+"_confirmation","private_plan":analysis["private_plan"],"ai":analysis,"human_decision_required":True}

@app.post("/api/cases/{case_id}/confirm/{ui_role}")
def native_confirm(case_id:str,ui_role:Literal["person","giver","steward","lead","funder"]):
    role_action={
        "giver":("supporter","offer","capacity_found"),
        "steward":("care_partner","verify","safety_checked"),
        "lead":("review_lead","resolve","ready"),
        "funder":("funder","fund","capacity_funded"),
    }
    with connect() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=?",(case_id,)).fetchone():
            raise HTTPException(404,"Case not found")
        if ui_role=="person":
            c.execute("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)",(case_id,1,json.dumps({"source":"native_web"}),now()))
            c.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?",("matching",now(),case_id))
            event(c,case_id,"person","consent_approved","Native web confirmation")
        else:
            actor,action_name,status=role_action[ui_role]
            c.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?",(status,now(),case_id))
            event(c,case_id,actor,action_name,"Confirmed through native web form")
    return RedirectResponse(url=f"/?confirmed={ui_role}#roles",status_code=303)
app.mount("/",StaticFiles(directory=ROOT/"dist",html=True),name="site")








