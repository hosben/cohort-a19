# piperun-cohort-agent

Agente de análise de cohort do pipeline de vendas. Roda toda segunda-feira,
puxa dados do Piperun, analisa métricas por canal/profissional/etapa via Claude,
e entrega o relatório no Slack — tudo via GitHub Actions, sem plataformas intermediárias.

## Estrutura

```
piperun-cohort-agent/
├── src/
│   ├── piperun/client.py     # Client da API Piperun (com auto-discovery)
│   ├── analysis/cohort.py    # Motor de métricas e cohort
│   ├── agents/insights.py    # Agente Claude com tool use
│   └── delivery/slack.py     # Formatação Block Kit + envio
├── reports/                  # Relatórios gerados (commitados automaticamente)
├── config/                   # Cache do mapa de pipelines (gitignored)
├── .github/workflows/        # Scheduler semanal
├── main.py                   # Ponto de entrada
└── requirements.txt
```

## Setup (primeira vez)

### 1. Clonar e instalar dependências

```bash
git clone https://github.com/SEU_USER/piperun-cohort-agent.git
cd piperun-cohort-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# edite .env com seus tokens
```

Adicione ao `.env`:
```
PIPERUN_API_TOKEN=    # Settings → Integrações → API Token
ANTHROPIC_API_KEY=    # console.anthropic.com
SLACK_WEBHOOK_URL=    # api.slack.com → Apps → Incoming Webhooks
```

Para carregar o .env localmente, use:
```bash
export $(cat .env | xargs)
```

### 3. Testar localmente

```bash
# Descobrir pipelines e testar sem enviar ao Slack
python main.py --dry-run

# Forçar re-descoberta de pipelines (após mudanças no Piperun)
python main.py --discover --dry-run

# Rodar completo
python main.py
```

### 4. Configurar GitHub Actions

No repositório GitHub → **Settings → Secrets and variables → Actions**, criar:

| Secret | Valor |
|--------|-------|
| `PIPERUN_API_TOKEN` | Token da API Piperun |
| `ANTHROPIC_API_KEY` | Chave da Anthropic |
| `SLACK_WEBHOOK_URL` | URL do webhook do Slack |

A partir daí, toda segunda-feira às 08:00 UTC (05:00 Brasília) o agente roda automaticamente.

Para rodar manualmente: **Actions → Weekly Pipeline Report → Run workflow**.

## Como o agente classifica canais

O agente descobre os pipelines automaticamente via API e os classifica pelo nome:

| Canal | Palavras-chave detectadas |
|-------|--------------------------|
| `inbound` | inbound, entrada, marketing, leads, site, web |
| `outbound` | outbound, prospec, ativo, cold, sdrs, hunters |
| `referral` | indicação, indicacao, referral, parceiro, partner, cs |
| `other` | qualquer outro |

Se a classificação automática estiver errada, edite `src/piperun/client.py` → `_classify_channel`.

## O que o relatório contém

1. **Resumo executivo** — headline + 3 bullets + perspectiva
2. **Por canal** — win rate, volume, ciclo médio, ação recomendada
3. **Profissionais** — destaque da semana + quem precisa de atenção
4. **Gargalo de etapa** — onde os deals estão morrendo e por quê

## Forçar re-discovery

Se você criar novos pipelines ou etapas no Piperun:

```bash
python main.py --discover
```

Ou via GitHub Actions: **Run workflow → Force re-discovery: true**.

## Usando com Claude Code

Com o projeto aberto no VS Code:

```bash
claude
```

Claude Code consegue modificar qualquer parte do agente com contexto total do projeto.
Exemplo de prompt: "Adiciona uma métrica de velocidade média por etapa no cohort engine".
