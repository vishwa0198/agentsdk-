import requests

BASE = "http://localhost:8000"

# 1. Register
r = requests.post(f"{BASE}/auth/register", json={"username": "vishwa", "password": "agentsdk123"})
print(f"[1] Register:           {r.status_code}  {r.json()}")

# 2. Login
r = requests.post(f"{BASE}/auth/login", data={"username": "vishwa", "password": "agentsdk123"})
print(f"[2] Login:              {r.status_code}")
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# 3. /auth/me
r = requests.get(f"{BASE}/auth/me", headers=H)
print(f"[3] /auth/me:           {r.status_code}  {r.json()}")

# 4. No token → 401
r = requests.get(f"{BASE}/sessions/WebAgent")
print(f"[4] No token:           {r.status_code}  (expect 401)")

# 5. Sessions (empty)
r = requests.get(f"{BASE}/sessions/WebAgent", headers=H)
print(f"[5] Sessions empty:     {r.status_code}  {r.json()}")

# 6. Chat
r = requests.post(f"{BASE}/chat",
    json={"session_id": "ses-001", "message": "What is 5 * 9?", "agent_name": "WebAgent"},
    headers=H)
out = r.json()
print(f"[6] Chat:               {r.status_code}")
print(f"    output:             {out['output']}")

# 7. Sessions after chat
r = requests.get(f"{BASE}/sessions/WebAgent", headers=H)
ids = [s["session_id"] for s in r.json()]
print(f"[7] Sessions after:     {r.status_code}  {ids}")

# 8. Duplicate register → 400
r = requests.post(f"{BASE}/auth/register", json={"username": "vishwa", "password": "agentsdk123"})
print(f"[8] Duplicate user:     {r.status_code}  {r.json()}")

# 9. Wrong password → 401
r = requests.post(f"{BASE}/auth/login", data={"username": "vishwa", "password": "wrongpass"})
print(f"[9] Wrong password:     {r.status_code}  (expect 401)")

# 10. Short password → 422
r = requests.post(f"{BASE}/auth/register", json={"username": "newuser", "password": "abc"})
detail = r.json().get("detail", "")
if isinstance(detail, list):
    detail = detail[0].get("msg", detail)
print(f"[10] Short password:    {r.status_code}  {detail}")

print()
print("=" * 40)
print("ALL TESTS COMPLETE")
