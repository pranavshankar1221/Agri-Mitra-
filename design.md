# AgriMitra Backend Design

## 1. Purpose

AgriMitra is a backend-first, agentic market intelligence system for farmers.

The backend receives a farmer's query, retrieves current agricultural market data from trusted external sources, retrieves supporting domain knowledge using RAG, performs deterministic market calculations, uses specialized agents for planning and reasoning, and returns an evidence-backed recommendation.

The backend must be completed and tested independently before the React frontend is implemented.

### Primary outcomes

The backend must support:

1. Current commodity price lookup.
2. Nearby market comparison.
3. Historical price and arrival trend analysis.
4. Demand/opportunity analysis.
5. Farmer-specific market recommendations.
6. Evidence-backed RAG responses.
7. Proactive market monitoring and alert generation.
8. Human-readable reasoning with source/timestamp/confidence information.

The system must never treat an LLM-generated value as an authoritative market fact. Current prices, arrivals, distances, and numerical calculations must come from tools/data services.

---

# 2. Core Design Principles

## 2.1 Agents are used for decisions and orchestration

Use an agent when the system needs to decide:

- which tools to call,
- which information is relevant,
- whether more information is required,
- how to combine conflicting signals,
- what recommendation should be produced,
- whether an automated monitoring event requires an action.

## 2.2 Deterministic logic remains normal application code

Do NOT create an agent for:

- arithmetic,
- percentage calculations,
- moving averages,
- distance calculations,
- database CRUD,
- embedding generation,
- schema validation,
- authentication,
- API serialization.

These belong in Python services/functions.

## 2.3 Real-time data and RAG are separate

### Live data

Current prices, arrivals, market metadata, and other time-sensitive values come from external market APIs/data sources and are stored in PostgreSQL.

### RAG

RAG stores and retrieves relatively stable/unstructured knowledge:

- agricultural reports,
- market policies,
- quality standards,
- crop/storage guidance,
- government documents,
- commodity reports.

Do not put rapidly changing market prices into the vector database.

## 2.4 Human approval for high-impact actions

The first version is advisory.

The system may automatically monitor markets and generate alerts, but it must NOT automatically execute a real sale, purchase, financial transaction, or binding supplier action.

---

# 3. Recommended Technology Stack

## Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL

## Agentic layer

- LangGraph for orchestration/stateful workflows
- LangChain for tools, retrievers, prompts and model integration
- LLM provider: configurable through environment variables

## RAG

- pgvector
- Embedding model: configurable
- LangChain retriever

## Analytics

- Pandas / NumPy
- deterministic Python services for calculations

## Background processing

- APScheduler for simple MVP scheduling, OR
- Celery + Redis for a more scalable deployment

Recommendation for the initial backend:
- APScheduler + Redis is enough for the MVP.
- Keep the scheduler interface abstract so it can later be replaced by Celery.

## Cache

- Redis

## Testing

- pytest
- pytest-asyncio
- httpx
- testcontainers or Docker Compose for PostgreSQL/Redis integration tests

## Deployment

- Docker
- Docker Compose for development/integration
- Cloud deployment later

---

# 4. High-Level Architecture

```text
                          ┌─────────────────────┐
                          │      FastAPI        │
                          │       API           │
                          └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │ LangGraph           │
                          │ Orchestrator        │
                          └──────────┬──────────┘
                                     │
             ┌───────────────────────┼────────────────────────┐
             │                       │                        │
             ▼                       ▼                        ▼
      Market Intelligence     Demand & Trend           Farmer Context
           Agent                   Agent                   Service/Agent
             │                       │                        │
             └───────────────────────┼────────────────────────┘
                                     │
                  ┌──────────────────┴───────────────────┐
                  ▼                                      ▼
          Live Market Tools                         RAG Agent
                  │                                      │
                  ▼                                      ▼
        External Market APIs                    pgvector / Documents
                  │
                  ▼
             PostgreSQL
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  Market/Price Data    Historical Data
        │                   │
        └──────────┬────────┘
                   ▼
            Analytics Services
                   │
                   ▼
             Decision Agent
                   │
            ┌──────┴───────┐
            ▼              ▼
     Recommendation    Confidence/Risk
            │              │
            └──────┬───────┘
                   ▼
              Action/Alert
                   │
                   ▼
              Redis/Scheduler
```

---

# 5. Agent Inventory

There are 6 primary agents in the first implementation.

## 5.1 Orchestrator Agent

### Goal

Understand the farmer's request and create the execution plan.

### Input

- user query
- farmer profile/context

### Output

A structured plan such as:

```json
{
  "intent": "SELLING_DECISION",
  "commodity": "tomato",
  "quantity_kg": 2000,
  "location": "Coimbatore",
  "required_capabilities": [
    "CURRENT_PRICES",
    "PRICE_HISTORY",
    "MARKET_ARRIVALS",
    "NEARBY_MARKETS",
    "LOGISTICS",
    "RAG_KNOWLEDGE"
  ]
}
```

### Why this is an agent

The required workflow changes with the query.

Example:

- "What is the current tomato price?" requires current price retrieval.
- "Which market should I sell to?" requires price + markets + logistics.
- "What crops are in demand?" requires trend/demand analysis.
- "Can I store tomatoes?" requires RAG knowledge.

The agent decides which capabilities are needed instead of hard-coding every possible query path.

### Tools

It does not directly perform calculations. It selects downstream tools/agents.

---

# 5.2 Market Intelligence Agent

### Goal

Retrieve and interpret current market conditions.

### Responsibilities

- fetch current commodity prices,
- compare markets,
- fetch arrivals,
- retrieve historical market observations,
- check data freshness,
- reject stale/invalid data.

### Tools

```text
get_current_market_prices()
get_market_arrivals()
get_price_history()
get_nearby_markets()
get_market_metadata()
```

### Why this is an agent

The user request may require multiple market data calls.

For example:

"Best market for tomato near me"

requires:

1. identify candidate markets,
2. obtain current prices,
3. obtain arrivals,
4. identify data freshness,
5. pass candidates to logistics analysis.

The agent chooses the relevant sequence.

### Important constraint

The Market Intelligence Agent must never invent a market price.

If external data is unavailable, return:

```text
market_data_status = UNAVAILABLE
```

rather than generating an estimated current price.

---

# 5.3 Demand & Trend Agent

### Goal

Turn market observations into interpretable market opportunity signals.

### Input

- current prices
- historical prices
- arrivals
- trading volume when available
- optional seasonal information

### Deterministic analytics

Implemented as normal Python code:

```text
price_change_pct()
moving_average()
arrival_change_pct()
volatility()
momentum()
```

The agent consumes these computed metrics.

### Output example

```json
{
  "commodity": "tomato",
  "price_momentum": "positive",
  "price_change_7d_pct": 8.4,
  "arrival_change_7d_pct": -5.2,
  "opportunity_score": 74,
  "interpretation": "Positive market signal with moderate confidence"
}
```

### Why this is an agent

The calculations themselves are NOT agentic.

The agent is useful for:

- selecting which signals are relevant,
- detecting conflicting signals,
- comparing multiple commodities,
- explaining why a signal does or does not indicate opportunity.

Example:

Price increased but arrivals also increased sharply.

A fixed rule may say:

```text
price_up -> demand_high
```

The agent can recognize that the signals conflict and lower confidence.

---

# 5.4 Farmer Context Agent

### Goal

Determine which farmer-specific constraints matter for the current decision.

### Context

- location
- crop
- quantity
- land size
- storage availability
- irrigation
- preferred travel distance
- expected harvest date
- risk preference, if explicitly collected

### Why this is an agent

Different questions need different context.

Example:

"Best market today?"

Needs:
- location
- quantity
- crop

"What should I grow next season?"

May need:
- land area
- soil
- irrigation
- location
- season

The agent selects relevant context and tells the orchestrator what information is missing.

### Safety

If critical data is missing, return a structured clarification requirement rather than silently assuming values.

---

# 5.5 RAG Research Agent

### Goal

Retrieve trustworthy supporting knowledge for the current market question.

### Knowledge base

- government agricultural reports
- crop guidelines
- quality/grade standards
- storage guidance
- market rules
- agricultural policies
- commodity reports
- other approved reference documents

### Pipeline

```text
Document
  ↓
Parse
  ↓
Chunk
  ↓
Embedding
  ↓
pgvector
  ↓
Retriever
```

### Agent workflow

```text
Query
  ↓
Determine required knowledge
  ↓
Retrieve relevant documents
  ↓
Evaluate relevance
  ↓
If insufficient → refine query/retrieve again
  ↓
Return evidence
```

### Why this is an agent

Normal RAG always follows a fixed retrieve-then-answer pattern.

Agentic RAG can decide:

- what knowledge is needed,
- which collection to search,
- whether evidence is sufficient,
- whether a second retrieval is required.

### Important constraint

RAG must not be used as the primary source for current market prices.

For current price:
```text
Live market tool -> authoritative current value
```

For market rules/storage/crop knowledge:
```text
RAG -> supporting knowledge
```

---

# 5.6 Decision Agent

### Goal

Generate the final recommendation using evidence from all upstream components.

### Inputs

- current market data
- historical trends
- arrivals
- farmer context
- logistics cost
- demand/opportunity signals
- RAG evidence
- data freshness
- uncertainty

### Output

```json
{
  "recommendation": "SELL_AT_MARKET_B",
  "reason": [
    "higher current modal price",
    "better estimated net realization",
    "positive recent price momentum"
  ],
  "risk_level": "MEDIUM",
  "confidence": 0.78,
  "supporting_sources": [
    "market_api",
    "agri_report_12"
  ]
}
```

### Why this is an agent

This is a multi-factor reasoning problem.

The system may encounter:

```text
price       ↑
arrivals    ↑↑
transport   ↑
storage     available
```

The decision cannot be reduced to a single rule.

The Decision Agent combines evidence, identifies conflicts, and produces an explanation.

### Constraint

The Decision Agent must not invent missing metrics.

It should explicitly state:

```text
not_available
unknown
insufficient_data
```

when evidence is missing.

---

# 6. Monitoring and Automation

Monitoring is an automated workflow, not necessarily a separate LLM agent.

## 6.1 Market Monitoring Service

A scheduler periodically triggers:

```text
fetch current market data
        ↓
validate
        ↓
store
        ↓
compare against monitoring rules
        ↓
trigger workflow when threshold/event occurs
```

Example monitoring rule:

```json
{
  "commodity": "tomato",
  "market_id": "M001",
  "condition": {
    "price_change_pct": 10
  },
  "action": "GENERATE_MARKET_ALERT"
}
```

## 6.2 When an event occurs

```text
Scheduler
   ↓
Market Monitor
   ↓
Detect event
   ↓
Orchestrator
   ↓
Market Agent
   ↓
Trend Agent
   ↓
Decision Agent
   ↓
Alert Service
```

This is the autonomous loop.

---

# 7. Where Agentic Logic Exists vs Normal Logic

## Normal application logic

Use standard Python for:

```text
CRUD
authentication
validation
database queries
price difference
percentage change
moving averages
distance calculation
transport cost
net realization
data cleaning
freshness checks
threshold checks
schema validation
```

Example:

```python
net_realization = gross_revenue - transport_cost - other_costs
```

No agent is needed.

## Agentic logic

Use agents for:

```text
query interpretation
tool selection
workflow planning
context selection
iterative retrieval
conflicting-signal reasoning
evidence synthesis
recommendation generation
proactive decision workflows
```

---

# 8. Core Backend Services

Create services beneath the agents.

Recommended services:

```text
MarketDataService
PriceHistoryService
MarketAnalyticsService
FarmerService
LogisticsService
RAGService
EmbeddingService
RecommendationService
MonitoringService
AlertService
```

Agents call these services through well-defined tools.

Do not put database queries directly inside every agent node.

---

# 9. Tool Layer

LangGraph agents should use explicit tools.

Example tool list:

```text
get_current_prices
get_price_history
get_arrivals
get_market_metadata
get_nearby_markets
get_farmer_context
calculate_transport_cost
calculate_net_realization
calculate_market_trends
calculate_opportunity_score
search_rag
get_rag_sources
create_monitoring_rule
generate_alert
```

Tools should be:

- typed,
- testable,
- deterministic where possible,
- independently callable,
- free of hidden LLM behavior.

---

# 10. Database Design

## farmers

```text
id UUID PK
name
location
latitude
longitude
land_area
soil_type
irrigation
storage_available
created_at
updated_at
```

## commodities

```text
id UUID PK
name
category
unit
```

## markets

```text
id UUID PK
name
state
district
latitude
longitude
source
```

## market_prices

```text
id UUID PK
commodity_id FK
market_id FK
min_price
modal_price
max_price
arrival_quantity
observed_at
source
created_at
```

## monitoring_rules

```text
id UUID PK
farmer_id FK
commodity_id FK
market_id FK nullable
condition_type
threshold
active
last_triggered_at
created_at
```

## recommendations

```text
id UUID PK
farmer_id FK nullable
commodity_id FK
recommendation_type
recommendation_text
confidence
risk_level
created_at
```

## recommendation_sources

```text
id UUID PK
recommendation_id FK
source_type
source_reference
source_timestamp
```

## documents

```text
id UUID PK
title
source
document_type
published_at
created_at
```

## document_chunks

```text
id UUID PK
document_id FK
chunk_text
embedding VECTOR
metadata JSONB
created_at
```

## agent_runs

```text
id UUID PK
query
workflow_type
status
started_at
completed_at
error
```

## agent_run_steps

```text
id UUID PK
agent_run_id FK
agent_name
step_name
input_summary
output_summary
status
started_at
completed_at
```

This is very useful for debugging and demonstrating agent behavior.

---

# 11. API Design

## Farmer

```http
POST /api/v1/farmers
GET  /api/v1/farmers/{farmer_id}
PATCH /api/v1/farmers/{farmer_id}
```

## Market

```http
GET /api/v1/markets/nearby
GET /api/v1/markets/prices
GET /api/v1/markets/history
GET /api/v1/markets/arrivals
```

## AI

```http
POST /api/v1/agent/query
POST /api/v1/agent/analyze-selling
POST /api/v1/agent/analyze-demand
```

## Monitoring

```http
POST /api/v1/monitoring/rules
GET  /api/v1/monitoring/rules
DELETE /api/v1/monitoring/rules/{rule_id}
```

## Alerts

```http
GET /api/v1/alerts
POST /api/v1/alerts/{alert_id}/acknowledge
```

---

# 12. Main Query Flow

Example query:

> "I have 2 tonnes of tomatoes in Coimbatore. Where should I sell?"

## Step 1

FastAPI validates request.

## Step 2

Orchestrator creates:

```text
SELLING_DECISION
```

## Step 3

Farmer Context Agent obtains:

```text
location = Coimbatore
commodity = Tomato
quantity = 2000 kg
```

## Step 4

Market Agent:

```text
get_current_prices()
get_price_history()
get_arrivals()
get_nearby_markets()
```

## Step 5

Logistics service:

```text
calculate_distance()
calculate_transport_cost()
calculate_net_realization()
```

## Step 6

Demand & Trend Agent:

```text
calculate_price_change()
calculate_arrival_change()
calculate_opportunity_score()
```

## Step 7

RAG Research Agent retrieves relevant supporting documents.

## Step 8

Decision Agent combines:

```text
Current market
+
Historical trend
+
Arrivals
+
Farmer context
+
Logistics
+
RAG evidence
```

## Step 9

Decision Agent generates recommendation.

## Step 10

FastAPI returns structured response.

---

# 13. Response Contract

Do not return only a natural-language paragraph.

Return structured JSON:

```json
{
  "query": "I have 2 tonnes of tomatoes in Coimbatore. Where should I sell?",
  "commodity": "tomato",
  "quantity_kg": 2000,
  "market_comparison": [
    {
      "market": "Market A",
      "modal_price": 28,
      "estimated_transport_cost": 1000,
      "estimated_net_realization": 55000,
      "observed_at": "2026-08-21T10:00:00Z"
    }
  ],
  "trend": {
    "price_change_7d_pct": 8.4,
    "arrival_change_7d_pct": -5.2,
    "opportunity_score": 74
  },
  "recommendation": {
    "type": "SELL_AT_MARKET_B",
    "confidence": 0.78,
    "risk_level": "MEDIUM",
    "reasoning": [
      "Higher observed modal price",
      "Better estimated net realization",
      "Positive recent price momentum"
    ]
  },
  "sources": [
    {
      "type": "market_api",
      "name": "official_market_source",
      "observed_at": "2026-08-21T10:00:00Z"
    },
    {
      "type": "rag_document",
      "document_id": "doc_123"
    }
  ]
}
```

The frontend can later consume this directly.

---

# 14. Confidence and Risk

Do not let the LLM freely choose a confidence score.

Build a deterministic confidence service.

Example factors:

```text
data freshness
source reliability
number of supporting observations
agreement between signals
missing data
```

Then compute:

```text
confidence = deterministic confidence calculation
```

The Decision Agent receives the computed confidence and explains it.

This avoids arbitrary LLM confidence claims.

---

# 15. Data Freshness

Every live market record must have:

```text
observed_at
source
```

The system should distinguish:

```text
FRESH
STALE
EXPIRED
UNAVAILABLE
```

Example:

```text
if current_time - observed_at > allowed_age:
    status = STALE
```

If market data is stale, the system must clearly say so.

---

# 16. RAG Source Attribution

Every RAG result should maintain:

```text
document_id
title
source
chunk_id
retrieval_score
```

The final response should expose source references.

This makes the recommendation explainable.

---

# 17. Error Handling

The backend must handle:

### Market API unavailable

Return:

```text
LIVE_DATA_UNAVAILABLE
```

Do not hallucinate.

### RAG unavailable

The market-data functionality can continue if the question does not require documents.

### Missing farmer information

Return:

```text
REQUIRED_CONTEXT_MISSING
```

### LLM unavailable

Deterministic market endpoints must still work.

### Invalid external data

Reject and log the observation.

---

# 18. Project Structure

Recommended:

```text
agrimitra-backend/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── farmers.py
│   │       ├── markets.py
│   │       ├── agent.py
│   │       ├── monitoring.py
│   │       └── alerts.py
│   │
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── market_agent.py
│   │   ├── demand_agent.py
│   │   ├── farmer_context_agent.py
│   │   ├── rag_agent.py
│   │   └── decision_agent.py
│   │
│   ├── graph/
│   │   ├── state.py
│   │   ├── workflow.py
│   │   └── nodes.py
│   │
│   ├── tools/
│   │   ├── market_tools.py
│   │   ├── farmer_tools.py
│   │   ├── logistics_tools.py
│   │   ├── analytics_tools.py
│   │   └── rag_tools.py
│   │
│   ├── services/
│   │   ├── market_data_service.py
│   │   ├── analytics_service.py
│   │   ├── logistics_service.py
│   │   ├── rag_service.py
│   │   ├── recommendation_service.py
│   │   ├── monitoring_service.py
│   │   └── alert_service.py
│   │
│   ├── models/
│   │   ├── farmer.py
│   │   ├── commodity.py
│   │   ├── market.py
│   │   ├── market_price.py
│   │   ├── monitoring_rule.py
│   │   ├── recommendation.py
│   │   └── agent_run.py
│   │
│   ├── schemas/
│   │   ├── farmer.py
│   │   ├── market.py
│   │   ├── agent.py
│   │   └── recommendation.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   └── migrations/
│   │
│   ├── integrations/
│   │   ├── market_api.py
│   │   ├── weather_api.py
│   │   └── maps_api.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   │
│   └── workers/
│       └── market_monitor.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── agent/
│
├── scripts/
│   ├── ingest_market_data.py
│   └── ingest_documents.py
│
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
└── README.md
```

---

# 19. Testing Strategy

Complete backend testing before frontend development.

## Unit tests

Test:

```text
price calculations
trend calculations
opportunity score
transport calculations
net realization
data freshness
Pydantic validation
```

## Integration tests

Test:

```text
FastAPI → PostgreSQL
FastAPI → Redis
Market API → ingestion → PostgreSQL
RAG ingestion → pgvector → retrieval
```

## Agent tests

Mock external tools and verify:

```text
query
→ correct plan
→ correct tools
→ correct downstream agents
→ correct final structure
```

Example:

```text
"I want today's tomato price"
```

Expected:
```text
Market Agent called
No unnecessary RAG call
```

Example:

```text
"Where should I sell my tomatoes?"
```

Expected:
```text
Market Agent
Trend Agent
Logistics
Decision Agent
```

Example:

```text
"Can I store tomatoes for 10 days?"
```

Expected:
```text
RAG Agent
Farmer Context Agent if needed
Decision Agent
```

---

# 20. MVP Implementation Order

Do NOT implement all agents at once.

### Phase 1 — Data foundation

```text
FastAPI
PostgreSQL
SQLAlchemy
Alembic
Market schema
Farmer schema
```

### Phase 2 — Market ingestion

```text
External market source
↓
Validation
↓
PostgreSQL
```

### Phase 3 — Deterministic analytics

```text
price history
trend
arrival changes
net realization
market comparison
```

### Phase 4 — RAG

```text
documents
↓
chunking
↓
embeddings
↓
pgvector
↓
retrieval
```

### Phase 5 — LangGraph

Implement:

```text
Orchestrator
→ Market Agent
→ Trend Agent
→ RAG Agent
→ Decision Agent
```

### Phase 6 — Farmer personalization

Add Farmer Context Agent.

### Phase 7 — Monitoring

```text
scheduler
→ market monitor
→ event detection
→ agent workflow
→ alert
```

### Phase 8 — Backend testing

All backend flows must work through APIs before frontend begins.

---

# 21. First Definition of Done

The backend is considered MVP-complete only when this works end-to-end:

### Query

```text
"I have 2 tonnes of tomatoes in Coimbatore. Where should I sell?"
```

### Backend

```text
FastAPI
  ↓
LangGraph
  ↓
Orchestrator
  ↓
Market Agent
  ↓
Current + historical market data
  ↓
Trend Agent
  ↓
Farmer Context
  ↓
Logistics calculations
  ↓
RAG Agent
  ↓
Decision Agent
  ↓
Structured JSON response
```

### And independently:

```text
POST /monitoring/rules

        ↓

Scheduler

        ↓

Market price changes

        ↓

Automatic detection

        ↓

Agent workflow

        ↓

Alert stored in database
```

Only after these backend flows are reliable should the React frontend be built.

---

# 22. Final Architecture Rule

The most important design rule for the entire project is:

```text
                 AGENT
                   │
        Decides / reasons / plans
                   │
                   ▼
                 TOOLS
                   │
        Fetch / calculate / retrieve
                   │
                   ▼
               SERVICES
                   │
        Database / APIs / analytics
```

Do not reverse this.

The LLM/agent should **not** directly perform business-critical calculations or act as the database.

The backend services provide trustworthy facts.

The agents decide how to use those facts.

That separation will keep AgriMitra easier to test, explain, debug, and eventually scale.
