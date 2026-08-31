import os
import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from agent.tools import match_skills, calculate_distance, check_wallet
from agent.memory import fetch_query, run_query

class MatchState(TypedDict):
    user_id: str
    needed_skill: str
    offered_skill: str
    lat: float
    lon: float
    user_skills_offered: List[str]
    user_skills_needed: List[str]
    matched_users: List[dict]
    scored_matches: List[dict]
    final_matches: List[dict]

def fetch_user_profile(state: MatchState) -> MatchState:
    user_id = state["user_id"]
    rows = fetch_query("SELECT * FROM Users WHERE id = ?", (user_id,))
    if rows:
        state["lat"] = rows[0]["lat"] or 0.0
        state["lon"] = rows[0]["lon"] or 0.0
        
    offered_rows = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'offered'", (user_id,))
    needed_rows = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'needed'", (user_id,))
    
    state["user_skills_offered"] = [r["skill_name"].strip().lower() for r in offered_rows]
    if state["offered_skill"]:
        state["user_skills_offered"].append(state["offered_skill"].strip().lower())
        
    state["user_skills_needed"] = [r["skill_name"].strip().lower() for r in needed_rows]
    if state["needed_skill"]:
        state["user_skills_needed"].append(state["needed_skill"].strip().lower())
        
    return state

def semantic_matching(state: MatchState) -> MatchState:
    # Find users who OFFER the skill the current user NEEDS
    offered_matches = match_skills.invoke({"skill_name": state["needed_skill"], "type_needed": "offered"})
    
    # We should fetch their profiles
    matched_users = []
    for uid in offered_matches:
        if uid == state["user_id"]: continue
        rows = fetch_query("SELECT id, name, city, lat, lon, trust_score FROM Users WHERE id = ?", (uid,))
        if rows:
            u = rows[0]
            dist = calculate_distance.invoke({"lat1": state["lat"], "lon1": state["lon"], "lat2": u["lat"], "lon2": u["lon"]})
            u["distance"] = dist
            matched_users.append(u)
    
    state["matched_users"] = matched_users
    return state

def mutual_exchange_validation(state: MatchState) -> MatchState:
    validated_users = []
    my_offered_set = set(state["user_skills_offered"])
    my_needed_set = set(state["user_skills_needed"])
    
    def is_match(skill, skill_set):
        skill_lower = skill.strip().lower()
        if skill_lower in skill_set: return True
        for s in skill_set:
            if skill_lower in s or s in skill_lower: return True
        return False
        
    for u in state["matched_users"]:
        uid = u["id"]
        
        their_offered_rows = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'offered'", (uid,))
        their_offered = [r["skill_name"] for r in their_offered_rows]
        
        their_needed_rows = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'needed'", (uid,))
        their_needed = [r["skill_name"] for r in their_needed_rows]
        
        they_can_teach = []
        for skill in their_offered:
            if is_match(skill, my_needed_set):
                they_can_teach.append(skill)
                
        i_can_help = []
        for skill in their_needed:
            if is_match(skill, my_offered_set):
                i_can_help.append(skill)
                
        u["skills_they_can_teach"] = list(set(they_can_teach))
        u["skills_you_can_help_them_with"] = list(set(i_can_help))
        
        if u["skills_they_can_teach"] and u["skills_you_can_help_them_with"]:
            u["valid_exchange"] = True
        else:
            u["valid_exchange"] = False
            
        validated_users.append(u)
        
    state["matched_users"] = validated_users
    return state

def compatibility_scoring(state: MatchState) -> MatchState:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        state["scored_matches"] = state["matched_users"]
        return state
        
    llm = ChatGroq(model_name="openai/gpt-oss-120b", groq_api_key=groq_api_key)
    
    scored = []
    for u in state["matched_users"]:
        if not u.get("valid_exchange"):
            u["compatibility_score"] = 5
            u["ai_reasoning"] = "No mutual skill exchange found between users."
            scored.append(u)
            continue
            
        they_teach_str = ", ".join(u["skills_they_can_teach"])
        i_help_str = ", ".join(u["skills_you_can_help_them_with"])
        
        prompt = f"""
        User 1 needs: {they_teach_str} and offers {i_help_str}.
        User 2 ({u['name']}) is a potential match who can teach User 1: {they_teach_str} and needs help with: {i_help_str}.
        Distance: {u['distance']:.1f}km. Trust Score: {u['trust_score']}.
        
        Calculate a compatibility score (0-100) and provide a 1-sentence reasoning. Phrase the reasoning as a direct, second-person, headline-style insight (e.g., "You'd learn backend Python from someone who also wants your UI design skills — a strong two-way fit.").
        Format strictly as:
        Score: 95
        Reason: ...
        """
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content
            score = 50
            reason = "AI evaluation pending."
            lines = content.strip().split('\n')
            for line in lines:
                if line.startswith("Score:"):
                    score = int(line.split(":")[1].strip())
                elif line.startswith("Reason:"):
                    reason = line.split(":", 1)[1].strip()
            
            u["compatibility_score"] = score
            u["ai_reasoning"] = reason
        except Exception as e:
            import traceback
            traceback.print_exc()
            u["compatibility_score"] = 50
            u["ai_reasoning"] = "Fallback scoring." 
            
        scored.append(u)
        
    # Sort by compatibility
    scored.sort(key=lambda x: x["compatibility_score"], reverse=True)
    state["scored_matches"] = scored
    return state

def finalize_recommendations(state: MatchState) -> MatchState:
    # Take top 5
    state["final_matches"] = state["scored_matches"][:5]
    return state

# Build graph
workflow = StateGraph(MatchState)
workflow.add_node("fetch_user_profile", fetch_user_profile)
workflow.add_node("semantic_matching", semantic_matching)
workflow.add_node("mutual_exchange_validation", mutual_exchange_validation)
workflow.add_node("compatibility_scoring", compatibility_scoring)
workflow.add_node("finalize_recommendations", finalize_recommendations)

workflow.set_entry_point("fetch_user_profile")
workflow.add_edge("fetch_user_profile", "semantic_matching")
workflow.add_edge("semantic_matching", "mutual_exchange_validation")
workflow.add_edge("mutual_exchange_validation", "compatibility_scoring")
workflow.add_edge("compatibility_scoring", "finalize_recommendations")
workflow.add_edge("finalize_recommendations", END)

match_app = workflow.compile()

async def run_matchmaking(user_id: str, needed_skill: str, offered_skill: str):
    state = {
        "user_id": user_id,
        "needed_skill": needed_skill,
        "offered_skill": offered_skill,
        "lat": 0.0,
        "lon": 0.0,
        "user_skills_offered": [],
        "user_skills_needed": [],
        "matched_users": [],
        "scored_matches": [],
        "final_matches": []
    }
    
    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, match_app.invoke, state)
    return final_state["final_matches"]
