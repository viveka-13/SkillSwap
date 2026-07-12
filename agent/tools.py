from langchain.tools import tool
from agent.memory import skills_collection, profiles_collection, run_query, fetch_query
import math
import os
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@tool
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the distance in KM between two latitude/longitude points."""
    return haversine(lat1, lon1, lat2, lon2)

@tool
def match_skills(skill_name: str, type_needed: str) -> list:
    """Uses ChromaDB semantic search to find similar skills in the database. Returns user_ids."""
    results = skills_collection.query(
        query_texts=[skill_name],
        n_results=10,
        where={"type": type_needed}
    )
    # the metadatas contains user_id
    matches = []
    if results['metadatas'] and len(results['metadatas']) > 0:
        for metadata in results['metadatas'][0]:
            matches.append(metadata.get('user_id'))
    return list(set(matches)) # unique users

@tool
def check_wallet(user_id: str) -> dict:
    """Check user's wallet balance."""
    rows = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (user_id,))
    if rows:
        return {"user_id": user_id, "wallet_balance": rows[0]["wallet_balance"]}
    return {"error": "User not found"}

@tool
def chat_moderation(message: str) -> dict:
    """Uses LLM to moderate chat messages for spam, abuse, or scams."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return {"is_flagged": False, "reason": "No API key"}
    
    llm = ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=groq_api_key)
    prompt = f"Analyze this message for spam, abuse, threats or fake requests. Reply strictly with YES or NO.\n\nMessage: {message}"
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip().upper()
    is_flagged = "YES" in content
    return {"is_flagged": is_flagged, "reason": content}

@tool
def update_trust_score(user_id: str) -> dict:
    """Recalculate trust score based on average ratings."""
    rows = fetch_query("SELECT AVG(rating) as avg_rating, COUNT(*) as cnt FROM Ratings WHERE reviewee_id = ?", (user_id,))
    if rows and rows[0]["avg_rating"] is not None:
        avg = round(rows[0]["avg_rating"], 2)
        run_query("UPDATE Users SET trust_score = ? WHERE id = ?", (avg, user_id))
        return {"user_id": user_id, "new_trust_score": avg, "total_reviews": rows[0]["cnt"]}
    return {"user_id": user_id, "new_trust_score": 0, "total_reviews": 0}
