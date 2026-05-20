"""webui/backend/orgs.py — Organisation workspace management."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ORGS_FILE = Path(".agentsdk") / "orgs.json"


class OrgStore:
    def _load(self) -> dict[str, dict]:
        if not ORGS_FILE.exists():
            return {}
        try:
            return json.loads(ORGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        ORGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ORGS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def create_org(self, name: str, owner: str) -> dict:
        data = self._load()
        org = {
            "org_id": str(uuid.uuid4()),
            "name": name,
            "owner": owner,
            "members": [owner],
            "plan": "free",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data[org["org_id"]] = org
        self._save(data)
        return org

    def get_org(self, org_id: str) -> Optional[dict]:
        return self._load().get(org_id)

    def get_user_orgs(self, username: str) -> list[dict]:
        return [org for org in self._load().values() if username in org.get("members", [])]

    def add_member(self, org_id: str, username: str) -> None:
        data = self._load()
        org = data.get(org_id)
        if org is None:
            raise KeyError(f"Org {org_id!r} not found.")
        if username in org["members"]:
            raise ValueError(f"{username!r} is already a member.")
        org["members"].append(username)
        self._save(data)

    def remove_member(self, org_id: str, username: str) -> None:
        data = self._load()
        org = data.get(org_id)
        if org is None:
            raise KeyError(f"Org {org_id!r} not found.")
        if username == org["owner"]:
            raise ValueError("Owner cannot remove themselves from the org.")
        if username not in org["members"]:
            raise ValueError(f"{username!r} is not a member.")
        org["members"].remove(username)
        self._save(data)

    def delete_org(self, org_id: str, requester: str) -> None:
        data = self._load()
        org = data.get(org_id)
        if org is None:
            raise KeyError(f"Org {org_id!r} not found.")
        if org["owner"] != requester:
            raise PermissionError("Only the org owner can delete it.")
        del data[org_id]
        self._save(data)


org_store = OrgStore()
