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
    matched_users: List[dict]
    scored_matches: List[dict]
    final_matches: List[dict]

def fetch_user_profile(state: MatchState) -> MatchState:
    user_id = state["user_id"]
    rows = fetch_query("SELECT * FROM Users WHERE id = ?", (user_id,))
    if rows:
        state["lat"] = rows[0]["lat"] or 0.0
        state["lon"] = rows[0]["lon"] or 0.0
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

def compatibility_scoring(state: MatchState) -> MatchState:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        state["scored_matches"] = state["matched_users"]
        return state
        
    llm = ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=groq_api_key)
    
    scored = []
    for u in state["matched_users"]:
        prompt = f"""
        User 1 needs: {state['needed_skill']} and offers {state['offered_skill']}.
        User 2 ({u['name']}) is a potential match. Distance: {u['distance']:.1f}km. Trust Score: {u['trust_score']}.
        
        Calculate a compatibility score (0-100) and provide a 1-sentence reasoning.
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
        except:
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
workflow.add_node("compatibility_scoring", compatibility_scoring)
workflow.add_node("finalize_recommendations", finalize_recommendations)

workflow.set_entry_point("fetch_user_profile")
workflow.add_edge("fetch_user_profile", "semantic_matching")
workflow.add_edge("semantic_matching", "compatibility_scoring")
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
        "matched_users": [],
        "scored_matches": [],
        "final_matches": []
    }
    
    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, match_app.invoke, state)
    return final_state["final_matches"]
