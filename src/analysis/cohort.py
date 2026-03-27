"""
Cohort Analysis Engine
Processes raw Piperun deals into structured metrics
grouped by channel, professional, and stage.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any


def parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def days_between(d1: datetime | None, d2: datetime | None) -> float | None:
    if d1 and d2:
        return abs((d2 - d1).total_seconds() / 86400)
    return None


class CohortEngine:
    def __init__(self, account_map: dict):
        self.pipelines = account_map["pipelines"]
        self.users = account_map["users"]

    def process(
        self,
        deals_by_pipeline: dict[int, list[dict]],
        period_label: str = "current",
    ) -> dict:
        """
        Main entry point. Receives a dict of {pipeline_id: [deals]}
        and returns a fully structured metrics report.
        """
        by_channel: dict[str, list[dict]] = defaultdict(list)
        by_user: dict[str, list[dict]] = defaultdict(list)
        all_deals = []

        for pid, deals in deals_by_pipeline.items():
            pipeline_info = self.pipelines.get(str(pid), self.pipelines.get(pid, {}))
            channel = pipeline_info.get("channel", "other")
            stages_map = pipeline_info.get("stages", {})

            for deal in deals:
                enriched = self._enrich_deal(deal, channel, pipeline_info, stages_map)
                by_channel[channel].append(enriched)
                user_id = str(deal.get("owner_id", "unknown"))
                user_name = self.users.get(str(user_id), self.users.get(int(user_id) if user_id.isdigit() else user_id, {})).get("name", f"User {user_id}")
                by_user[user_name].append(enriched)
                all_deals.append(enriched)

        return {
            "period": period_label,
            "summary": self._summary_metrics(all_deals),
            "by_channel": {
                ch: self._channel_metrics(ch, deals)
                for ch, deals in by_channel.items()
            },
            "by_professional": {
                name: self._professional_metrics(name, deals)
                for name, deals in by_user.items()
            },
            "stage_funnel": self._stage_funnel(all_deals),
        }

    def _enrich_deal(
        self,
        deal: dict,
        channel: str,
        pipeline_info: dict,
        stages_map: dict,
    ) -> dict:
        created = parse_date(deal.get("created_at"))
        closed = parse_date(deal.get("finish_date") or deal.get("updated_at"))
        status = self._deal_status(deal)
        current_stage_id = str(deal.get("stage_id", ""))
        current_stage = stages_map.get(current_stage_id, {})

        return {
            "id": deal.get("id"),
            "title": deal.get("title", ""),
            "channel": channel,
            "pipeline_name": pipeline_info.get("name", ""),
            "status": status,
            "won": status == "won",
            "lost": status == "lost",
            "open": status == "open",
            "stage_id": current_stage_id,
            "stage_name": current_stage.get("name", "Unknown"),
            "stage_order": current_stage.get("order", 0),
            "user_id": str(deal.get("user_id", "")),
            "value": float(deal.get("value") or 0),
            "created_at": created,
            "closed_at": closed,
            "cycle_days": days_between(created, closed) if status != "open" else None,
            "days_open": days_between(created, datetime.now()) if status == "open" else None,
        }

    @staticmethod
    def _deal_status(deal: dict) -> str:
        # Piperun: status=1 aberto, status=2 ganho, status=3 perdido
        status = deal.get("status")
        if status == 2:
            return "won"
        if status == 3:
            return "lost"
        return "open"

    def _summary_metrics(self, deals: list[dict]) -> dict:
        total = len(deals)
        if total == 0:
            return {"total_deals": 0}

        won = [d for d in deals if d["won"]]
        lost = [d for d in deals if d["lost"]]
        open_deals = [d for d in deals if d["open"]]

        win_rate = len(won) / total * 100 if total else 0
        avg_cycle = self._avg([d["cycle_days"] for d in won if d["cycle_days"]])
        total_value = sum(d["value"] for d in won)

        return {
            "total_deals": total,
            "won": len(won),
            "lost": len(lost),
            "open": len(open_deals),
            "win_rate_pct": round(win_rate, 1),
            "avg_cycle_days": round(avg_cycle, 1) if avg_cycle else None,
            "total_won_value": round(total_value, 2),
        }

    def _channel_metrics(self, channel: str, deals: list[dict]) -> dict:
        metrics = self._summary_metrics(deals)
        metrics["channel"] = channel

        # Stage-level drop-off within this channel
        stage_counts: dict[str, int] = defaultdict(int)
        for d in deals:
            stage_counts[d["stage_name"]] += 1
        metrics["deals_by_stage"] = dict(
            sorted(stage_counts.items(), key=lambda x: -x[1])
        )

        # Average deal value
        won_values = [d["value"] for d in deals if d["won"] and d["value"] > 0]
        metrics["avg_deal_value"] = round(self._avg(won_values), 2) if won_values else 0

        return metrics

    def _professional_metrics(self, name: str, deals: list[dict]) -> dict:
        metrics = self._summary_metrics(deals)
        metrics["name"] = name

        # Stagnant deals: open for more than 14 days without moving
        stagnant = [d for d in deals if d["open"] and (d["days_open"] or 0) > 14]
        metrics["stagnant_deals"] = len(stagnant)
        metrics["stagnant_deal_ids"] = [d["id"] for d in stagnant]

        # Channel distribution for this professional
        ch_counts: dict[str, int] = defaultdict(int)
        for d in deals:
            ch_counts[d["channel"]] += 1
        metrics["deals_by_channel"] = dict(ch_counts)

        return metrics

    def _stage_funnel(self, deals: list[dict]) -> list[dict]:
        """Returns an ordered list of stages with entry counts and drop-off rates."""
        stage_buckets: dict[str, dict] = defaultdict(
            lambda: {"name": "", "order": 0, "total": 0, "won": 0, "lost": 0, "open": 0}
        )

        for d in deals:
            key = d["stage_name"]
            stage_buckets[key]["name"] = d["stage_name"]
            stage_buckets[key]["order"] = d["stage_order"]
            stage_buckets[key]["total"] += 1
            if d["won"]:
                stage_buckets[key]["won"] += 1
            elif d["lost"]:
                stage_buckets[key]["lost"] += 1
            else:
                stage_buckets[key]["open"] += 1

        stages = sorted(stage_buckets.values(), key=lambda x: x["order"])

        # Compute conversion rate relative to first stage
        if stages and stages[0]["total"] > 0:
            first_total = stages[0]["total"]
            for s in stages:
                s["conversion_from_top_pct"] = round(s["total"] / first_total * 100, 1)

        return stages

    @staticmethod
    def _avg(values: list[float | None]) -> float:
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else 0.0
