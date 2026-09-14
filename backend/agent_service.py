from __future__ import annotations
import json, os, re
try:
    from strands import Agent, tool
    from strands.models import BedrockModel
except ImportError:
    Agent=None
    def tool(fn): return fn

@tool
def classify_dana(need:str)->dict:
    """Classify a support need into Jain forms of dana without judging deservingness."""
    n=need.lower()
    if any(x in n for x in ["dialysis","clinic","medicine","medical","hospital","इलाज","દવા","હોસ્પિટલ"]): return {"primary":"bhaiṣajya-dāna","secondary":"abhaya-dāna"}
    if any(x in n for x in ["study","school","library","education","पढ़","અભ્યાસ"]): return {"primary":"jñāna-dāna","secondary":None}
    if any(x in n for x in ["food","meal","भोजन","खाना","ભોજન"]): return {"primary":"āhāra-dāna","secondary":None}
    return {"primary":"abhaya-dāna","secondary":None}

@tool
def evaluate_safeguards(need:str)->list[str]:
    """Return ethical safeguards relevant to a support plan."""
    return ["preserve the person's meaning (satya)","obtain consent before disclosure (ahiṃsā)","offer without control or publicity (aparigraha)","surface uncertainty and multiple perspectives (anekāntavāda)"]

@tool
def find_capacity(kind:str)->list[dict]:
    """Find verified demo capacity. Never returns recipient identity."""
    return [{"id":"offer_transport_01","type":"transport","verified":True},{"id":"fund_mobility_01","type":"fund","verified":True}] if "bhai" in kind or "abhaya" in kind else []

def local_analysis(need:str,language:str,actor:str="person")->dict:
    dana=classify_dana(need); safeguards=evaluate_safeguards(need)
    labels={"en":"We understood that you need practical support. Please review the timing, access needs and privacy preferences before this is shared.","hi":"हमने आपकी बात से एक निजी सहायता योजना तैयार की है। आगे साझा करने से पहले समय, सुविधा और गोपनीयता की पसंद जाँच लें।","gu":"તમારી વાત પરથી ખાનગી સહાય યોજના તૈયાર કરી છે. આગળ વહેંચતાં પહેલાં સમય, સુવિધા અને ગોપનીયતાની પસંદ તપાસો."}
    return {"mode":"local","dana_type":dana,"private_plan":labels[language],"shareable_constraints":["timing to confirm","access needs to confirm","identity withheld"],"capacity_required":dana["primary"],"safeguards":safeguards,"uncertainty":["No facts have been independently verified yet."]}

def _as_list(value):
    if value is None: return []
    if isinstance(value,list): return value
    return [value]

def analyse_need(need:str,language:str,actor:str="person")->dict:
    if os.getenv("PARASPARA_AI_MODE","local")!="strands" or Agent is None:
        return local_analysis(need,language,actor)
    try:
        model=BedrockModel(
            model_id=os.getenv("PARASPARA_MODEL_ID","global.amazon.nova-2-lite-v1:0"),
            region_name=os.getenv("AWS_REGION",os.getenv("AWS_DEFAULT_REGION","us-east-1")),
            temperature=0.1,
            streaming=False,
        )
        agent=Agent(
            model=model,
            callback_handler=None,
            system_prompt="""You are Paraspara, a dignity-first care coordinator grounded in ahimsa, satya, aparigraha and many-sided reasoning. Never judge deservingness. Never invent facts. Minimise disclosure. Use all supplied tools. Return JSON only with keys: private_plan, dana_type, shareable_constraints, capacity_required, safeguards, uncertainty.""",
            tools=[classify_dana,evaluate_safeguards,find_capacity],
        )
        role_context={"person":"The writer is seeking support. Preserve their voice and prepare a consent-first plan.","supporter":"The writer is offering capacity. Describe their offer accurately; never call them a recipient or imply that they need support.","care_partner":"The writer is verifying delivery or safety. Produce a verification brief, not a recipient plan.","review_lead":"The writer is recording human judgment on an exception. Preserve their authority and explain the decision context.","funder":"The writer is offering institutional capacity. Produce an anonymous capacity brief; never expose or invent a recipient story."}[actor]
        prompt=f"Language: {language}\nActor: {actor}\nInstruction: {role_context}\nActor's own words: {need}\nReturn a concise, role-correct interpretation for their approval."
        raw=str(agent(prompt))
        match=re.search(r"\{.*\}",raw,re.S)
        if not match: raise ValueError("no_structured_result")
        result=json.loads(match.group())
        result["private_plan"]=str(result.get("private_plan") or "").strip()
        if not result["private_plan"]: raise ValueError("empty_private_plan")
        result["shareable_constraints"]=_as_list(result.get("shareable_constraints"))
        result["safeguards"]=_as_list(result.get("safeguards"))
        result["uncertainty"]=_as_list(result.get("uncertainty"))
        if not isinstance(result.get("dana_type"),dict):
            result["dana_type"]=classify_dana(need)
        used=[]
        for message in getattr(agent,"messages",[]):
            for item in message.get("content",[]):
                call=item.get("toolUse") if isinstance(item,dict) else None
                if call and call.get("name") not in used: used.append(call["name"])
        result["agent_trace"]=[{"type":"tool","name":name} for name in used]
        result["model_id"]=os.getenv("PARASPARA_MODEL_ID","global.amazon.nova-2-lite-v1:0")
        result["actor"]=actor
        result["mode"]="strands"
        return result
    except Exception as exc:
        fallback=local_analysis(need,language,actor)
        fallback["mode"]="local_fallback"
        fallback["uncertainty"]=["Live agent was unavailable; a deterministic private draft was prepared."]
        fallback["agent_error_type"]=type(exc).__name__
        return fallback


