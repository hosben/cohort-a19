"""
piperun-cohort-agent
Main orchestrator: pulls data, runs analysis, generates insights, delivers to Slack.

Usage:
    python main.py                  # Run for current week
    python main.py --discover       # Force re-discovery of pipelines/stages/users
    python main.py --dry-run        # Run without sending to Slack (prints to terminal)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load .env automatically when running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.piperun.client import PiperunClient
from src.analysis.cohort import CohortEngine
from src.agents.insights import generate_insights
from src.delivery.slack import build_slack_payload, send_to_slack, save_markdown_report


REPORTS_DIR = Path("reports")
PREV_METRICS_PATH = Path("reports/prev_metrics.json")


def get_date_range(weeks_ago: int = 0) -> tuple[str, str]:
    """Returns (start, end) date strings for a given week offset."""
    today = datetime.now()
    end = today - timedelta(weeks=weeks_ago)
    start = end - timedelta(days=7)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def load_prev_metrics() -> dict | None:
    if PREV_METRICS_PATH.exists():
        with open(PREV_METRICS_PATH) as f:
            return json.load(f)
    return None


def save_prev_metrics(metrics: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREV_METRICS_PATH, "w") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2, default=str)


def run(dry_run: bool = False, force_discover: bool = False) -> None:
    # ── 1. Validate env vars ────────────────────────────────────────────────
    piperun_token = os.environ.get("PIPERUN_API_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL")

    if not piperun_token:
        sys.exit("ERROR: PIPERUN_API_TOKEN env var is not set.")
    if not anthropic_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY env var is not set.")
    if not slack_webhook and not dry_run:
        sys.exit("ERROR: SLACK_WEBHOOK_URL env var is not set. Use --dry-run to skip Slack.")

    # ── 2. Discover account structure ───────────────────────────────────────
    piperun = PiperunClient(piperun_token)
    account_map = piperun.build_account_map(force=force_discover)
    pipelines = account_map["pipelines"]

    print(f"Loaded {len(pipelines)} pipelines.")
    for pid, p in pipelines.items():
        print(f"  [{p['channel']}] {p['name']} (id={pid}, {len(p['stages'])} stages)")

    # ── 3. Fetch deals for current week ─────────────────────────────────────
    start_date, end_date = get_date_range(weeks_ago=0)
    print(f"\nFetching deals from {start_date} to {end_date}...")

    deals_by_pipeline: dict[int, list[dict]] = {}
    for pid_str, p in pipelines.items():
        pid = int(pid_str)
        deals = piperun.get_all_deals(pid, start_date, end_date)
        deals_by_pipeline[pid] = deals
        print(f"  {p['name']}: {len(deals)} deals")

    total = sum(len(d) for d in deals_by_pipeline.values())
    if total == 0:
        print("No deals found for this period. Exiting.")
        return

    # ── 4. Run cohort analysis ───────────────────────────────────────────────
    print("\nRunning cohort analysis...")
    engine = CohortEngine(account_map)
    metrics = engine.process(deals_by_pipeline, period_label=f"{start_date} → {end_date}")

    prev_metrics = load_prev_metrics()

    # ── 5. Generate AI insights ──────────────────────────────────────────────
    print("Generating insights with Claude...")
    insights = generate_insights(metrics, prev_metrics)

    # ── 6. Save report and persist metrics ──────────────────────────────────
    date_str = datetime.now().strftime("%Y-%m-%d")
    md_path = f"reports/{date_str}-pipeline-report.md"
    save_markdown_report(metrics, insights, md_path)
    save_prev_metrics(metrics)

    # ── 7. Deliver to Slack ──────────────────────────────────────────────────
    payload = build_slack_payload(metrics, insights)

    if dry_run:
        print("\n── DRY RUN: Slack payload ──")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\nInsights: {json.dumps(insights, ensure_ascii=False, indent=2)}")
    else:
        send_to_slack(slack_webhook, payload)

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Piperun Cohort Agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending to Slack",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Force re-discovery of pipelines, stages, and users",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, force_discover=args.discover)
