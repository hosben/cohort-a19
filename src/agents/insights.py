"""
Claude Insights Agent
Uses Anthropic tool use to interpret cohort metrics
and generate structured weekly insights.
"""

import json
import anthropic

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "generate_channel_insight",
        "description": (
            "Generates a strategic insight for a specific channel "
            "(inbound, outbound, referral). Analyzes win rate, conversion, "
            "and volume trends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "insight": {"type": "string", "description": "2-3 sentence insight"},
                "severity": {
                    "type": "string",
                    "enum": ["ok", "attention", "critical"],
                    "description": "Performance status",
                },
                "recommended_action": {
                    "type": "string",
                    "description": "One concrete next action",
                },
            },
            "required": ["channel", "insight", "severity", "recommended_action"],
        },
    },
    {
        "name": "generate_professional_insight",
        "description": (
            "Identifies the top performer and one professional needing attention "
            "based on win rate, volume, and stagnant deals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top_performer": {"type": "string", "description": "Name of top performer"},
                "top_performer_reason": {"type": "string"},
                "needs_attention": {
                    "type": "string",
                    "description": "Name of professional needing coaching",
                },
                "needs_attention_reason": {"type": "string"},
            },
            "required": [
                "top_performer",
                "top_performer_reason",
                "needs_attention",
                "needs_attention_reason",
            ],
        },
    },
    {
        "name": "generate_stage_insight",
        "description": (
            "Identifies the biggest bottleneck stage in the funnel "
            "and suggests a tactical fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bottleneck_stage": {"type": "string"},
                "drop_off_pct": {
                    "type": "number",
                    "description": "Estimated % of deals lost at this stage",
                },
                "hypothesis": {
                    "type": "string",
                    "description": "Why deals are stalling here",
                },
                "tactical_fix": {"type": "string"},
            },
            "required": [
                "bottleneck_stage",
                "drop_off_pct",
                "hypothesis",
                "tactical_fix",
            ],
        },
    },
    {
        "name": "generate_executive_summary",
        "description": (
            "Produces a 3-bullet executive summary of the week's pipeline health."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "One-sentence summary of the week",
                },
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "3 key takeaways",
                },
                "outlook": {
                    "type": "string",
                    "description": "Short forward-looking statement",
                },
            },
            "required": ["headline", "bullets", "outlook"],
        },
    },
]


def _build_prompt(metrics: dict, prev_metrics: dict | None) -> str:
    comparison = ""
    if prev_metrics:
        prev_wr = prev_metrics.get("summary", {}).get("win_rate_pct", "N/A")
        curr_wr = metrics.get("summary", {}).get("win_rate_pct", "N/A")
        comparison = f"\nComparação com semana anterior: win rate {prev_wr}% → {curr_wr}%"

    return f"""Você é um analista de vendas sênior especializado em B2B SaaS industrial.
Analise as métricas de pipeline abaixo e chame TODAS as ferramentas disponíveis
para gerar insights acionáveis.

Seja direto e específico. Use números reais dos dados. Evite generalidades.
Escreva em português brasileiro.{comparison}

MÉTRICAS DA SEMANA:
{json.dumps(metrics, ensure_ascii=False, indent=2, default=str)}
"""


def generate_insights(metrics: dict, prev_metrics: dict | None = None) -> dict:
    """
    Calls Claude with tool use to extract structured insights from metrics.
    Returns a dict with channel, professional, stage, and executive insights.
    """
    prompt = _build_prompt(metrics, prev_metrics)

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )

    insights = {
        "channel_insights": [],
        "professional_insight": None,
        "stage_insight": None,
        "executive_summary": None,
    }

    for block in response.content:
        if block.type != "tool_use":
            continue

        name = block.name
        inp = block.input

        if name == "generate_channel_insight":
            insights["channel_insights"].append(inp)
        elif name == "generate_professional_insight":
            insights["professional_insight"] = inp
        elif name == "generate_stage_insight":
            insights["stage_insight"] = inp
        elif name == "generate_executive_summary":
            insights["executive_summary"] = inp

    return insights
