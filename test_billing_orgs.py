"""Integration test for billing + org endpoints."""
import requests

BASE = "http://localhost:8000"

# Login as existing user
r = requests.post(f"{BASE}/auth/login", data={"username": "vishwa", "password": "agentsdk123"})
assert r.status_code == 200, f"Login failed: {r.text}"
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# ── Billing usage ─────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/billing/usage", headers=H)
print(f"[1] GET /billing/usage:     {r.status_code}  plan={r.json()['plan']}  used={r.json()['used_tokens']}  limit={r.json()['limit']}  {r.json()['percent']}%")

# ── Plans list ────────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/billing/plans", headers=H)
plans = r.json()
print(f"[2] GET /billing/plans:     {r.status_code}  {[p['name'] for p in plans]}")

# ── Checkout without Stripe configured (expect 400) ───────────────────────
r = requests.post(f"{BASE}/billing/create-checkout", json={"plan": "pro"}, headers=H)
print(f"[3] POST /billing/create-checkout (no key): {r.status_code}  {r.json()}")

# ── Portal without subscription (expect 400) ─────────────────────────────
r = requests.post(f"{BASE}/billing/portal", headers=H)
print(f"[4] POST /billing/portal (no sub): {r.status_code}  {r.json()}")

# ── Quota check (free plan, 0 tokens used → allowed) ─────────────────────
r = requests.get(f"{BASE}/billing/usage", headers=H)
pct = r.json()["percent"]
print(f"[5] Quota check:            {'OK - within limit' if pct < 100 else 'EXCEEDED'}")

# ── Create org ────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/orgs", json={"name": "Jarvis Labs"}, headers=H)
print(f"[6] POST /orgs:             {r.status_code}  {r.json().get('name')}  owner={r.json().get('owner')}")
org_id = r.json()["org_id"]

# ── List orgs ─────────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/orgs", headers=H)
print(f"[7] GET /orgs:              {r.status_code}  {[o['name'] for o in r.json()]}")

# ── Get org ───────────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/orgs/{org_id}", headers=H)
print(f"[8] GET /orgs/{{id}}:         {r.status_code}  members={r.json()['members']}")

# ── Add member ────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/orgs/{org_id}/members", json={"username": "alice"}, headers=H)
print(f"[9] POST /orgs/members:     {r.status_code}  {r.json()}")

# ── Duplicate member → 400 ────────────────────────────────────────────────
r = requests.post(f"{BASE}/orgs/{org_id}/members", json={"username": "alice"}, headers=H)
print(f"[10] Duplicate member:      {r.status_code}  {r.json()}")

# ── Remove member ─────────────────────────────────────────────────────────
r = requests.delete(f"{BASE}/orgs/{org_id}/members/alice", headers=H)
print(f"[11] DELETE member:         {r.status_code}  {r.json()}")

# ── Owner cannot remove self ──────────────────────────────────────────────
r = requests.delete(f"{BASE}/orgs/{org_id}/members/vishwa", headers=H)
print(f"[12] Owner remove self:     {r.status_code}  {r.json()}")

# ── Delete org ────────────────────────────────────────────────────────────
r = requests.delete(f"{BASE}/orgs/{org_id}", headers=H)
print(f"[13] DELETE /orgs/{{id}}:     {r.status_code}  {r.json()}")

# ── Confirm deleted ───────────────────────────────────────────────────────
r = requests.get(f"{BASE}/orgs", headers=H)
print(f"[14] Orgs after delete:     {r.status_code}  {r.json()}")

print()
print("=" * 45)
print("ALL BILLING + ORG TESTS COMPLETE")
