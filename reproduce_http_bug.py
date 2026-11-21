import os
import sys
os.chdir(r'c:\Users\Renta\OneDrive\Documents\projects\skillswap')
sys.path.insert(0, r'c:\Users\Renta\OneDrive\Documents\projects\skillswap')

import requests
import json
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv

load_dotenv(r'c:\Users\Renta\OneDrive\Documents\projects\skillswap\.env')
SECRET_KEY = os.getenv("SECRET_KEY", "skillswap-secret-key-12345")

BASE_URL = "http://localhost:8000"

def run_reproduction():
    user_id = '89e25df5-6d77-4e00-8328-166a9f195ba1' # Nishanth
    token = jwt.encode({"sub": user_id, "exp": datetime.utcnow() + timedelta(days=1)}, SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Token generated for Nishanth ({user_id})")
    
    # 1. Exact call for recommended:
    print("\n[REQUEST 1] GET /api/events/recommended")
    r1 = requests.get(f"{BASE_URL}/api/events/recommended", headers=headers)
    print(f"Status Code: {r1.status_code}")
    print(f"Response: {r1.text}")
    
    # 2. Exact call on initial page load:
    print("\n[REQUEST 2] GET /api/events?sort=starts_at&limit=40")
    r2 = requests.get(f"{BASE_URL}/api/events?sort=starts_at&limit=40", headers=headers)
    print(f"Status Code: {r2.status_code}")
    print(f"Response: {r2.text}")
    
    # 3. Filter call with empty query params:
    print("\n[REQUEST 3] GET /api/events?city=&category=&skill=&mode=&max_km=&sort=starts_at&limit=40")
    r3 = requests.get(f"{BASE_URL}/api/events?city=&category=&skill=&mode=&max_km=&sort=starts_at&limit=40", headers=headers)
    print(f"Status Code: {r3.status_code}")
    print(f"Response: {r3.text}")

if __name__ == "__main__":
    run_reproduction()
