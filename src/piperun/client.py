"""
Piperun API Client
Handles all communication with Piperun REST API.
Auto-discovers pipelines, stages, and users.
"""

import httpx
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_URL = "https://api.pipe.run/v1"
CACHE_PATH = Path("config/piperun_map.json")


class PiperunClient:
    def __init__(self, api_token: str):
        self.token = api_token
        self.headers = {"token": api_token}
        self.client = httpx.Client(timeout=30)

    def _get(self, endpoint: str, params: dict = None) -> dict:
        params = params or {}
        response = self.client.get(f"{BASE_URL}/{endpoint}", params=params, headers={"token": self.token, "Accept": "application/json"})
        response.raise_for_status()
        return response.json()

    def _paginate(self, endpoint: str, params: dict = None) -> list[dict]:
        """Fetches all pages from a paginated endpoint."""
        params = params or {}
        params["show"] = 200
        all_items = []
        page = 1

        while True:
            params["page"] = page
            data = self._get(endpoint, params)

            items = data.get("data", data.get("items", []))
            if not items:
                break

            all_items.extend(items)

            meta = data.get("meta", {})
            total_pages = meta.get("last_page", 1)
            if page >= total_pages:
                break
            page += 1

        return all_items

    def discover_pipelines(self) -> list[dict]:
        """Returns all pipelines (funnels) in the account."""
        return self._paginate("pipelines")

    def discover_stages(self, pipeline_id: int) -> list[dict]:
        """Returns all stages for a given pipeline."""
        return self._paginate("stages", {"pipeline_id": pipeline_id})

    def discover_users(self) -> list[dict]:
        """Returns all users (team members) in the account."""
        return self._paginate("users")

    def get_deals(
        self,
        pipeline_id: int,
        start_date: str,
        end_date: str,
        page: int = 1,
    ) -> dict:
        """Fetch deals for a pipeline within a date range."""
        params = {
            "pipeline_id": pipeline_id,
            "date_start": start_date,
            "date_end": end_date,
            "show": 200,
            "page": page,
        }
        return self._get("deals", params)

    def get_all_deals(
        self, pipeline_id: int, start_date: str, end_date: str
    ) -> list[dict]:
        """Fetches all deals across pages for a pipeline and date range."""
        all_deals = []
        page = 1

        while True:
            data = self.get_deals(pipeline_id, start_date, end_date, page)
            items = data.get("data", data.get("items", []))
            if not items:
                break
            all_deals.extend(items)

            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break
            page += 1

        return all_deals

    def get_deal_history(self, deal_id: int) -> list[dict]:
        """Fetch stage transition history for a specific deal."""
        data = self._get(f"deals/{deal_id}/historic")
        return data.get("data", [])

    def build_account_map(self, force: bool = False) -> dict:
        """
        Builds and caches a full map of pipelines, stages, and users.
        Cached in config/piperun_map.json.
        Only re-fetches if force=True or cache is missing.
        """
        if not force and CACHE_PATH.exists():
            with open(CACHE_PATH) as f:
                return json.load(f)

        print("Discovering Piperun account structure...")

        pipelines = self.discover_pipelines()
        users = self.discover_users()

        pipeline_map = {}
        for p in pipelines:
            pid = p["id"]
            stages = self.discover_stages(pid)
            pipeline_map[pid] = {
                "id": pid,
                "name": p["name"],
                "channel": self._classify_channel(p["name"]),
                "stages": {
                    s["id"]: {
                        "id": s["id"],
                        "name": s["name"],
                        "order": s.get("order", 0),
                        "finish_probability": s.get("finish_probability", 0),
                    }
                    for s in stages
                },
            }

        user_map = {
            u["id"]: {
                "id": u["id"],
                "name": u["name"],
                "email": u.get("email", ""),
            }
            for u in users
        }

        account_map = {
            "pipelines": pipeline_map,
            "users": user_map,
            "updated_at": datetime.now().isoformat(),
        }

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(account_map, f, ensure_ascii=False, indent=2)

        print(
            f"Discovered {len(pipeline_map)} pipelines, "
            f"{sum(len(p['stages']) for p in pipeline_map.values())} stages, "
            f"{len(user_map)} users."
        )
        return account_map

    @staticmethod
    def _classify_channel(pipeline_name: str) -> str:
        """
        Classifies a pipeline into a channel based on its name.
        Keywords are case-insensitive and cover PT/EN variants.
        """
        name = pipeline_name.lower()

        inbound_keywords = ["inbound", "entrada", "marketing", "leads", "site", "web"]
        outbound_keywords = ["outbound", "prospec", "ativo", "cold", "sdrs", "hunters"]
        referral_keywords = [
            "indicação", "indicacao", "referral", "parceiro", "partner", "cs", "sucesso", "parceria"
        ]
        closer_keywords = ["closer", "fechamento", "closing"]
        if any(k in name for k in closer_keywords):
            return "outbound"

        if any(k in name for k in inbound_keywords):
            return "inbound"
        if any(k in name for k in outbound_keywords):
            return "outbound"
        if any(k in name for k in referral_keywords):
            return "referral"

        return "other"
