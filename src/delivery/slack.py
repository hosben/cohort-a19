"""
Slack Delivery
Formats cohort insights as rich Slack Block Kit messages
and sends via webhook.
"""

import httpx
import json
from datetime import datetime


SEVERITY_EMOJI = {
    "ok": ":large_green_circle:",
    "attention": ":large_yellow_circle:",
    "critical": ":red_circle:",
}

CHANNEL_EMOJI = {
    "inbound": ":inbox_tray:",
    "outbound": ":outbox_tray:",
    "referral": ":handshake:",
    "other": ":package:",
}


def _header_block(period: str, summary: dict) -> list:
    date_str = datetime.now().strftime("%d/%m/%Y")
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":bar_chart: Pipeline Report — {date_str}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Deals totais*\n{summary.get('total_deals', 0)}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Win rate*\n{summary.get('win_rate_pct', 0)}%",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Ganhos*\n{summary.get('won', 0)} deals",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Ciclo médio*\n{summary.get('avg_cycle_days', 'N/A')} dias",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Valor ganho*\nR$ {summary.get('total_won_value', 0):,.2f}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Em aberto*\n{summary.get('open', 0)} deals",
                },
            ],
        },
        {"type": "divider"},
    ]


def _executive_summary_block(exec_summary: dict | None) -> list:
    if not exec_summary:
        return []
    bullets = "\n".join(f"• {b}" for b in exec_summary.get("bullets", []))
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":memo: *Resumo Executivo*\n"
                    f"_{exec_summary.get('headline', '')}_\n\n"
                    f"{bullets}\n\n"
                    f":crystal_ball: {exec_summary.get('outlook', '')}"
                ),
            },
        },
        {"type": "divider"},
    ]


def _channel_blocks(channel_insights: list[dict]) -> list:
    if not channel_insights:
        return []

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:funnel: Insights por Canal*"},
        }
    ]

    for ci in channel_insights:
        emoji = CHANNEL_EMOJI.get(ci.get("channel", "other"), ":package:")
        severity_dot = SEVERITY_EMOJI.get(ci.get("severity", "ok"), "")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{severity_dot} {emoji} *{ci['channel'].upper()}*\n"
                        f"{ci.get('insight', '')}\n"
                        f":dart: _{ci.get('recommended_action', '')}_"
                    ),
                },
            }
        )

    blocks.append({"type": "divider"})
    return blocks


def _professional_block(prof_insight: dict | None) -> list:
    if not prof_insight:
        return []
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":busts_in_silhouette: *Profissionais*\n\n"
                    f":trophy: *Destaque:* {prof_insight.get('top_performer', '')}\n"
                    f"_{prof_insight.get('top_performer_reason', '')}_\n\n"
                    f":warning: *Atenção:* {prof_insight.get('needs_attention', '')}\n"
                    f"_{prof_insight.get('needs_attention_reason', '')}_"
                ),
            },
        },
        {"type": "divider"},
    ]


def _stage_block(stage_insight: dict | None) -> list:
    if not stage_insight:
        return []
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":traffic_light: *Gargalo de Etapa*\n\n"
                    f"*Etapa crítica:* {stage_insight.get('bottleneck_stage', '')}"
                    f" ({stage_insight.get('drop_off_pct', 0)}% de drop-off)\n"
                    f":bulb: {stage_insight.get('hypothesis', '')}\n"
                    f":wrench: _{stage_insight.get('tactical_fix', '')}_"
                ),
            },
        },
    ]


def build_slack_payload(metrics: dict, insights: dict) -> dict:
    """Assembles the full Slack Block Kit payload."""
    blocks = []
    blocks += _header_block(metrics.get("period", ""), metrics.get("summary", {}))
    blocks += _executive_summary_block(insights.get("executive_summary"))
    blocks += _channel_blocks(insights.get("channel_insights", []))
    blocks += _professional_block(insights.get("professional_insight"))
    blocks += _stage_block(insights.get("stage_insight"))

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Gerado por piperun-cohort-agent | {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                }
            ],
        }
    )

    return {"blocks": blocks}


def send_to_slack(webhook_url: str, payload: dict) -> bool:
    """Sends the payload to the Slack webhook. Returns True on success."""
    response = httpx.post(
        webhook_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    if response.status_code == 200:
        print("Slack message sent successfully.")
        return True
    else:
        print(f"Slack error: {response.status_code} — {response.text}")
        return False


def save_markdown_report(metrics: dict, insights: dict, output_path: str) -> None:
    """Also saves a markdown version for the GitHub repo."""
    from pathlib import Path

    date_str = datetime.now().strftime("%Y-%m-%d")
    summary = metrics.get("summary", {})
    exec_s = insights.get("executive_summary", {})

    lines = [
        f"# Pipeline Report — {date_str}",
        "",
        "## Resumo",
        f"- **Total de deals:** {summary.get('total_deals', 0)}",
        f"- **Win rate:** {summary.get('win_rate_pct', 0)}%",
        f"- **Valor ganho:** R$ {summary.get('total_won_value', 0):,.2f}",
        f"- **Ciclo médio:** {summary.get('avg_cycle_days', 'N/A')} dias",
        "",
    ]

    if exec_s:
        lines += [
            "## Resumo Executivo",
            f"_{exec_s.get('headline', '')}_",
            "",
        ]
        for b in exec_s.get("bullets", []):
            lines.append(f"- {b}")
        lines += ["", f"**Perspectiva:** {exec_s.get('outlook', '')}", ""]

    for ci in insights.get("channel_insights", []):
        lines += [
            f"## Canal: {ci['channel'].upper()}",
            f"**Status:** {ci.get('severity', '')}",
            ci.get("insight", ""),
            f"**Ação:** {ci.get('recommended_action', '')}",
            "",
        ]

    prof = insights.get("professional_insight")
    if prof:
        lines += [
            "## Profissionais",
            f"**Destaque:** {prof.get('top_performer', '')} — {prof.get('top_performer_reason', '')}",
            f"**Atenção:** {prof.get('needs_attention', '')} — {prof.get('needs_attention_reason', '')}",
            "",
        ]

    stage = insights.get("stage_insight")
    if stage:
        lines += [
            "## Gargalo de Etapa",
            f"**Etapa crítica:** {stage.get('bottleneck_stage', '')} ({stage.get('drop_off_pct', 0)}% drop-off)",
            stage.get("hypothesis", ""),
            f"**Fix:** {stage.get('tactical_fix', '')}",
            "",
        ]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Markdown report saved to {output_path}")
