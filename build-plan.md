# DataForge AI — Backend Build Plan

> Production-grade AI-native DataOps platform built on Azure Databricks with autonomous multi-agent orchestration, operational RAG, observability, and self-healing workflows.

---

# 1. Product Vision

## One-Sentence Pitch

DataForge AI is an AI-native operational intelligence platform for data engineering teams that automatically monitors, explains, optimizes, and remediates big-data pipelines running on Azure Databricks.

---

# 2. Core Principles

This project MUST prioritize:

- production realism,
- reliability,
- observability,
- deterministic orchestration,
- scalable architecture,
- infrastructure-first thinking,
- strict CI/CD discipline,
- testability,
- modularity,
- operational intelligence.

This project MUST NOT become:
- a toy chatbot,
- feature soup,
- a generic RAG wrapper,
- an overengineered microservice mess.

---

# 3. High-Level Architecture

## Core Platform Components

### A. Data Ingestion Layer
Responsible for:
- streaming ingestion,
- metadata ingestion,
- Spark log ingestion,
- schema capture,
- lineage extraction.

Technologies:
- Kafka / Azure Event Hubs
- Databricks Auto Loader
- Delta Live Tables
- Structured Streaming

---

### B. Lakehouse Layer
Implement Medallion architecture:
- Bronze
- Silver
- Gold

Requirements:
- Delta Lake
- schema evolution
- checkpointing
- partitioning
- Z-order optimization
- CDC support
- idempotent processing

---

### C. Metadata Intelligence Layer
Stores:
- schemas
- lineage
- Spark plans
- dbt manifests
- incidents
- logs
- DAG metadata
- runbooks
- code embeddings
- operational memory

Technologies:
- PostgreSQL
- Neo4j (optional)
- pgvector / Qdrant

---

### D. Operational RAG Layer
Purpose:
- contextual debugging
- incident retrieval
- root-cause reasoning
- infra-aware conversational assistant

Indexes:
- Spark logs
- pipeline failures
- historical incidents
- documentation
- code repositories
- execution plans
- architecture notes

Requirements:
- chunking strategy
- semantic retrieval
- hybrid search
- metadata filtering
- evaluation pipeline

---

### E. Multi-Agent Orchestration Layer

Agents:
1. Observability Agent
2. Root Cause Analysis Agent
3. Optimization Agent
4. Governance Agent
5. Remediation Agent
6. Deployment Agent

Requirements:
- deterministic execution
- state persistence
- retries
- confidence scoring
- fallback chains
- human approval checkpoints
- rollback support

Technologies:
- LangGraph
- Temporal
- Redis
- FastAPI

---

### F. ML Intelligence Layer

Models:
- failure prediction
- anomaly detection
- cost forecasting
- SLA risk prediction

Requirements:
- MLflow tracking
- feature store integration
- offline evaluation
- batch + streaming inference

---

### G. Observability Layer

Requirements:
- distributed tracing
- metrics
- structured logging
- health monitoring
- audit logs
- incident tracking

Technologies:
- OpenTelemetry
- Prometheus
- Grafana

---

# 4. Backend Service Architecture

## Services

### 1. ingestion-service
Responsibilities:
- consume Kafka/Event Hub streams
- ingest Spark logs
- normalize metadata
- push to Bronze layer

---

### 2. metadata-service
Responsibilities:
- lineage extraction
- schema registry
- DAG mapping
- operational graph management

---

### 3. rag-service
Responsibilities:
- embedding generation
- vector indexing
- retrieval orchestration
- reranking
- conversational context assembly

---

### 4. orchestration-service
Responsibilities:
- multi-agent execution
- workflow management
- retries
- circuit breakers
- approval gates

---

### 5. observability-service
Responsibilities:
- anomaly detection
- metrics aggregation
- incident generation
- health scoring

---

### 6. remediation-service
Responsibilities:
- Spark failure analysis
- fix recommendation generation
- patch proposal generation
- safe rerun orchestration

---

### 7. gateway-api
Responsibilities:
- authentication
- routing
- rate limiting
- API aggregation

---

# 5. Monorepo Structure

```txt
dataforge-ai/
│
├── apps/
│   ├── gateway-api/
│   ├── orchestration-service/
│   ├── rag-service/
│   ├── metadata-service/
│   ├── observability-service/
│   ├── remediation-service/
│   └── ingestion-service/
│
├── agents/
│   ├── observability-agent/
│   ├── optimization-agent/
│   ├── root-cause-agent/
│   ├── remediation-agent/
│   └── governance-agent/
│
├── infra/
│   ├── terraform/
│   ├── kubernetes/
│   ├── helm/
│   └── github-actions/
│
├── platform/
│   ├── shared/
│   ├── contracts/
│   ├── sdk/
│   └── event-schemas/
│
├── data/
│   ├── bronze/
│   ├── silver/
│   └── gold/
│
├── notebooks/
├── docs/
├── tests/
└── scripts/
```

---

# 6. Strict Engineering Standards

## Mandatory Rules

### Rule 1 — PR Before Every Merge
NO direct pushes to main.

Every change MUST:
- originate from a feature branch,
- open a pull request,
- pass CI,
- pass linting,
- pass tests,
- receive approval,
- squash merge into main.

---

### Rule 2 — Trunk-Based Development
Branches:
- short-lived,
- feature-scoped,
- continuously rebased.

Avoid:
- long-running branches.

---

### Rule 3 — CI/CD Is Mandatory
Every PR triggers:
- formatting
- linting
- type checking
- unit tests
- integration tests
- security scans
- container builds
- infrastructure validation

Merge blocked if ANY fail.

---

### Rule 4 — Infrastructure as Code ONLY
No manual cloud configuration.

Everything must be:
- Terraform-managed,
- version-controlled,
- reproducible.

---

### Rule 5 — Contracts First
All inter-service communication:
- typed,
- schema-validated,
- versioned.

Use:
- Pydantic
- OpenAPI
- protobufs if needed

---

### Rule 6 — Observability First
Every service MUST expose:
- metrics
- tracing
- structured logs
- health checks

before production deployment.

---

### Rule 7 — Reliability Over Features
Prefer:
- fewer stable workflows

over:
- many fragile workflows.

---

# 7. CI/CD Pipeline Requirements

## GitHub Actions Workflow

Every PR MUST run:

### Backend Validation
- Ruff
- Black
- MyPy
- PyTest
- coverage checks

---

### Security
- Trivy
- Bandit
- dependency scanning
- secret scanning

---

### Infrastructure Validation
- Terraform fmt
- Terraform validate
- Terraform plan

---

### Container Validation
- Docker build
- vulnerability scan

---

### Integration Tests
- Kafka integration
- Redis integration
- PostgreSQL integration
- Vector DB integration

---

### Deployment Gates
Deploy only if:
- all checks pass,
- approval received,
- staging smoke tests pass.

---

# 8. Deployment Architecture

## Cloud Stack

Primary Platform:
- Azure Databricks
- Azure Kubernetes Service
- Azure Blob Storage / ADLS
- Azure Event Hubs

---

## Deployment Model

### Environments
- local
- dev
- staging
- production

Each environment:
- isolated
- reproducible
- fully IaC-managed

---

# 9. Backend Prompt For Claude Code

Copy this prompt into Claude Code as the primary system build instruction.

---

# MASTER BACKEND BUILD PROMPT

You are acting as a Principal Staff Engineer designing and implementing a production-grade AI-native DataOps platform called “DataForge AI”.

Your responsibilities are:
- architect scalable backend systems,
- implement reliable distributed workflows,
- prioritize production realism,
- enforce strict engineering discipline,
- prevent overengineering,
- maintain architectural coherence.

The platform is an AI-native operational intelligence system for Azure Databricks data pipelines.

Core capabilities:
- metadata ingestion,
- Spark log analysis,
- operational RAG,
- multi-agent orchestration,
- anomaly detection,
- root cause analysis,
- remediation generation,
- self-healing workflows,
- observability,
- infrastructure intelligence.

Tech Stack:
- Python
- FastAPI
- LangGraph
- Temporal
- Azure Databricks
- Delta Lake
- Kafka
- PostgreSQL
- Redis
- pgvector/Qdrant
- MLflow
- OpenTelemetry
- Prometheus
- Grafana
- Docker
- Kubernetes
- Terraform
- GitHub Actions

STRICT ENGINEERING REQUIREMENTS:

1. NO toy architecture.
2. NO fake abstractions.
3. NO placeholder logic unless explicitly marked.
4. NO direct pushes to main.
5. EVERY change must be PR-driven.
6. ALL code must be typed.
7. ALL services must include:
   - structured logging,
   - tracing,
   - metrics,
   - health checks.
8. ALL workflows must be deterministic and retry-safe.
9. ALL APIs must use schema validation.
10. ALL infrastructure must be Infrastructure-as-Code.
11. ALL changes must include tests.
12. Reliability is more important than feature count.
13. Avoid premature microservice fragmentation.
14. Prefer modular monolith patterns where reasonable.
15. Build for operational clarity and maintainability.

MANDATORY CI/CD RULES:

- Every PR must pass:
  - linting,
  - formatting,
  - type checks,
  - unit tests,
  - integration tests,
  - security scans,
  - container validation,
  - Terraform validation.

- CI failure blocks merge.
- Use GitHub Actions.
- Use semantic commit messages.
- Enforce branch protections.

REQUIRED DEVELOPMENT APPROACH:

When implementing features:
1. First define architecture.
2. Then define contracts.
3. Then define schemas/models.
4. Then implement business logic.
5. Then add observability.
6. Then add tests.
7. Then update documentation.

PRIORITY ORDER:
1. Reliability
2. Observability
3. Scalability
4. Maintainability
5. Security
6. Developer Experience
7. Feature Velocity

The codebase should feel like:
- a real startup platform,
- senior-engineered infrastructure,
- enterprise-grade backend systems.

Always explain:
- architectural decisions,
- tradeoffs,
- scaling implications,
- failure scenarios,
- reliability considerations.

Reject weak patterns and anti-patterns.

Build incrementally with production-quality standards.

---

# 10. Initial MVP Scope

## MVP Goal

Build one exceptional workflow:

“Self-healing observability platform for Databricks pipelines.”

---

## MVP User Flow

1. User connects Databricks workspace.
2. Platform ingests Spark logs + metadata.
3. Platform builds lineage graph.
4. Observability agent detects anomaly.
5. Root-cause agent explains issue.
6. RAG retrieves similar incidents.
7. Remediation agent generates fix.
8. Human approves fix.
9. Platform reruns workflow safely.

---

# 11. MVP Success Criteria

The MVP is successful if:
- a realistic Databricks pipeline can be monitored,
- failures can be detected,
- root causes can be explained,
- historical incidents can be retrieved,
- fix recommendations can be generated,
- workflows remain deterministic and observable.

NOT required for MVP:
- enterprise billing,
- advanced RBAC,
- multi-cloud support,
- massive frontend polish,
- dozens of agents.

---

# 12. Final Guiding Philosophy

This platform should feel like:
- infrastructure intelligence,
- operational AI,
- autonomous DataOps.

NOT:
- a chatbot wrapper,
- a dashboard project,
- a collection of disconnected AI features.

Focus on:
- believable engineering,
- production depth,
- reliability,
- operational realism,
- architectural excellence.


---

# 13. MCP Tooling & AI Engineering Workflow

This section defines HOW and WHEN MCP tools must be connected during development.

The goal is NOT maximum tool count.

The goal is:
- engineering acceleration,
- architectural consistency,
- deterministic workflows,
- production reliability,
- operational visibility.

---

# MCP Philosophy

MCP tools are treated as:
- engineering copilots,
- operational assistants,
- architecture-aware tooling.

They are NOT:
- autonomous uncontrolled agents,
- black-box code generators.

Every MCP integration must:
- improve engineering quality,
- reduce context-switching,
- strengthen reliability,
- improve developer velocity.

---

# 14. MCP Stack Overview

## Mandatory MCP Stack

| MCP Tool | Purpose | Phase |
|---|---|---|
| Claude Code | architecture + implementation | Day 1 |
| Context7 MCP | live framework/docs retrieval | Day 1 |
| Filesystem MCP | monorepo reasoning | Day 1 |
| GitHub MCP | PR + CI/CD workflows | Day 1 |
| Sequential Thinking MCP | orchestration reasoning | Week 2 |
| Postgres MCP | metadata graph reasoning | Week 3 |
| Docker MCP | local infra orchestration | Week 3 |
| Kubernetes MCP | infra debugging | Week 6+ |
| LangSmith | agent tracing/evals | Week 3 |
| Sentry | production monitoring | Week 4 |

---

# 15. MCP Integration Timeline

## Phase 1 — Foundation Setup (Day 1–3)

### Connect Immediately

#### A. Claude Code
Purpose:
- primary engineering copilot,
- repo-wide reasoning,
- backend scaffolding,
- architecture planning.

Usage:
- service creation,
- orchestration workflows,
- CI/CD setup,
- infrastructure scaffolding.

Mandatory Rules:
- all prompts architecture-aware,
- no blind code generation,
- always explain tradeoffs.

---

#### B. Context7 MCP
Purpose:
- real-time framework documentation,
- API understanding,
- implementation references.

Critical for:
- Databricks SDK
- LangGraph
- Temporal
- OpenTelemetry
- MLflow
- Kafka
- FastAPI
- Delta Lake

Why Early?
This massively reduces:
- hallucinations,
- outdated implementations,
- incorrect APIs.

---

#### C. Filesystem MCP
Purpose:
- monorepo awareness,
- service dependency reasoning,
- architecture consistency.

Required For:
- cross-service refactors,
- contract synchronization,
- shared models.

Must Be Connected Before:
- service scaffolding begins.

---

#### D. GitHub MCP
Purpose:
- PR automation,
- CI visibility,
- branch workflow enforcement.

MANDATORY REQUIREMENTS:
- every feature uses feature branch,
- no direct pushes to main,
- PR created before merge,
- CI must pass before merge.

GitHub MCP should:
- summarize architecture changes,
- generate PR descriptions,
- verify CI results,
- track issues/tasks.

---

# 16. Strict Git Workflow

## Branch Naming Convention

```txt
feature/<feature-name>
fix/<bug-name>
infra/<infra-change>
agent/<agent-name>
refactor/<scope>
```

---

## Mandatory Workflow

1. Create feature branch.
2. Implement feature.
3. Run local tests.
4. Run lint/type checks.
5. Open PR.
6. CI validation runs automatically.
7. Review architecture impact.
8. Squash merge only after approval.

---

## NEVER ALLOWED

- direct push to main,
- bypassing CI,
- untyped code,
- skipping tests,
- force pushes to protected branches.

---

# 17. CI/CD Pipeline Design

## CI Stages

### Stage 1 — Formatting
Tools:
- Ruff
- Black

---

### Stage 2 — Static Analysis
Tools:
- MyPy
- Bandit
- dependency scanning

---

### Stage 3 — Unit Testing
Requirements:
- service coverage,
- deterministic workflows,
- retry logic validation.

---

### Stage 4 — Integration Testing
Spin up:
- Kafka
- Redis
- PostgreSQL
- Vector DB
- Local Temporal

Using:
- Docker MCP
- Docker Compose

---

### Stage 5 — Infrastructure Validation
Requirements:
- Terraform fmt
- Terraform validate
- Terraform plan

---

### Stage 6 — Container Validation
Requirements:
- Docker builds
- vulnerability scans
- runtime checks

---

### Stage 7 — Staging Deployment
Requirements:
- smoke tests
- health checks
- observability validation

---

# 18. Sequential Thinking MCP Integration

## Connect During Week 2

Purpose:
- orchestration reasoning,
- incident workflow planning,
- retry-chain design,
- deterministic state-machine validation.

Use Cases:
- LangGraph planning,
- remediation flows,
- fallback chains,
- RCA sequencing.

Why Important?
Prevents:
- chaotic agent behavior,
- circular workflows,
- non-deterministic orchestration.

---

# 19. Postgres MCP Integration

## Connect During Week 3

Purpose:
- operational metadata querying,
- lineage inspection,
- incident correlation,
- graph-aware reasoning.

Used By:
- RAG service,
- RCA agent,
- remediation workflows.

Operational Tables:
- incidents
- pipeline_runs
- lineage_edges
- spark_failures
- remediation_history
- embeddings_metadata

---

# 20. Docker MCP Integration

## Connect During Week 3

Purpose:
- local infra orchestration,
- deterministic integration testing,
- reproducible development environments.

Services To Run Locally:
- Kafka
- Redis
- PostgreSQL
- Qdrant
- Temporal
- Prometheus
- Grafana

---

# 21. LangSmith Integration

## Connect During Week 3

Purpose:
- agent tracing,
- workflow debugging,
- prompt evaluation,
- orchestration visibility.

MANDATORY REQUIREMENT:
Every agent workflow must expose:
- execution trace,
- reasoning path,
- retry history,
- state transitions,
- tool calls.

Without this:
multi-agent debugging becomes unmanageable.

---

# 22. Sentry Integration

## Connect During Week 4

Purpose:
- production exception tracking,
- distributed tracing,
- release monitoring,
- operational debugging.

All backend services must:
- emit structured errors,
- include correlation IDs,
- attach request metadata.

---

# 23. Kubernetes MCP Integration

## Connect During Week 6+

Only AFTER:
- stable local workflows,
- stable Docker environments,
- deterministic orchestration.

Purpose:
- pod inspection,
- deployment debugging,
- runtime diagnostics,
- infra-aware remediation agents.

DO NOT prematurely optimize Kubernetes.

---

# 24. Local Development Environment

## Required Local Stack

Use Docker Compose for:
- Kafka
- PostgreSQL
- Redis
- Qdrant
- Temporal
- Prometheus
- Grafana

---

## Local Commands

Required scripts:
```bash
make setup
make lint
make test
make integration-test
make infra-validate
make run-local
```

---

# 25. Observability Requirements

Every service MUST expose:

## Metrics
- request count
- latency
- workflow duration
- retry count
- failure rate

---

## Traces
- agent execution
- retrieval chains
- remediation workflows
- external API calls

---

## Logs
Structured JSON logs ONLY.

Mandatory fields:
- request_id
- correlation_id
- workflow_id
- service_name
- severity
- timestamp

---

# 26. Architecture Review Rules

Before merging ANY major feature:

Review:
- scalability impact,
- operational complexity,
- observability coverage,
- failure modes,
- rollback strategy,
- retry behavior,
- state persistence,
- infra cost implications.

---

# 27. Final Engineering Philosophy

The platform should feel like:
- modern infrastructure software,
- reliable operational tooling,
- intelligent systems engineering.

NOT:
- AI gimmicks,
- prompt wrappers,
- overengineered abstractions.

Optimize for:
- clarity,
- reliability,
- maintainability,
- operational intelligence,
- production realism.

The architecture must remain:
- coherent,
- observable,
- deterministic,
- extensible,
- debuggable.


---

# 28. Local-First & Free Development Strategy

This project MUST be designed as:
- local-first,
- reproducible,
- containerized,
- cloud-compatible,
- cost-efficient.

The MVP MUST run fully on a local machine using Docker Compose.

Cloud deployment is OPTIONAL and deferred until:
- workflows stabilize,
- architecture matures,
- operational validation succeeds.

---

# 29. Zero-Cost Development Philosophy

The platform should demonstrate:
- systems engineering,
- distributed workflows,
- operational intelligence,
- observability,
- reliability engineering,

WITHOUT requiring expensive cloud infrastructure.

The architecture must prioritize:
- local reproducibility,
- deterministic environments,
- infrastructure portability,
- minimal operational cost.

---

# 30. Local-First Architecture

## Primary Runtime

The entire platform must run locally using:

- Docker Compose
- Apache Spark
- Delta Lake
- Redpanda
- PostgreSQL
- Redis
- Qdrant
- Temporal
- FastAPI
- Prometheus
- Grafana
- MLflow

---

# 31. Replace Managed Cloud Services

## DO NOT Use Initially

| Managed Service | Replace With |
|---|---|
| Azure Databricks | Apache Spark Local |
| Event Hubs | Redpanda |
| Pinecone | Qdrant |
| AKS | Docker Compose |
| Managed Redis | Local Redis |
| Managed Postgres | Docker Postgres |
| Grafana Cloud | Local Grafana |
| MLflow Hosting | Local MLflow |

---

# 32. Local Infrastructure Topology

## Docker Compose Services

```yaml
services:
  gateway-api:
  orchestration-service:
  rag-service:
  metadata-service:
  observability-service:
  remediation-service:
  ingestion-service:

  postgres:
  redis:
  qdrant:
  redpanda:
  temporal:
  prometheus:
  grafana:
  mlflow:
  spark-master:
  spark-worker:
```

---

# 33. Apache Spark Local Cluster Setup

## Development Mode

Use:
- Spark standalone cluster
- Delta Lake
- Structured Streaming

Requirements:
- local medallion architecture,
- local Delta tables,
- partitioning,
- schema evolution,
- checkpointing,
- streaming support.

---

## Why This Matters

This still demonstrates:
- distributed data processing,
- big data engineering,
- Spark optimization,
- streaming architecture,
- operational workflows.

WITHOUT expensive Databricks costs.

---

# 34. Redpanda Instead Of Kafka

## Use Redpanda Locally

Reasons:
- Kafka API compatible,
- lightweight,
- Docker-friendly,
- low memory usage,
- simpler setup.

Used For:
- streaming ingestion,
- event-driven workflows,
- pipeline event simulation,
- incident event streaming.

---

# 35. Qdrant Local Vector Database

## Use Local Qdrant

Purpose:
- operational RAG,
- incident retrieval,
- metadata embeddings,
- Spark log embeddings.

Requirements:
- Dockerized deployment,
- persistent volume,
- metadata-aware retrieval.

---

# 36. Local MLflow Setup

## Run MLflow Locally

Purpose:
- experiment tracking,
- anomaly model tracking,
- evaluation logging,
- inference history.

This provides:
- realistic ML Ops workflows,
- reproducible model evaluation.

---

# 37. Local Observability Stack

## Mandatory Stack

### Prometheus
For:
- metrics scraping,
- workflow metrics,
- service health.

---

### Grafana
For:
- observability dashboards,
- incident monitoring,
- workflow tracing,
- infrastructure metrics.

---

### OpenTelemetry
For:
- distributed tracing,
- workflow instrumentation,
- request correlation.

---

# 38. Local Temporal Workflow Engine

## Use Temporal Locally

Purpose:
- durable execution,
- retry-safe orchestration,
- deterministic workflows,
- stateful agent execution.

This becomes:
- the backbone of orchestration reliability.

---

# 39. Docker Compose Requirements

## Mandatory Requirements

The entire platform MUST support:

```bash
docker compose up
```

to launch:
- all services,
- databases,
- vector stores,
- observability stack,
- orchestration runtime,
- streaming runtime.

---

# 40. Local Development Workflow

## Developer Flow

### Step 1
Clone repo.

---

### Step 2
Run:

```bash
make setup
```

---

### Step 3
Run:

```bash
docker compose up
```

---

### Step 4
Run:

```bash
make dev
```

---

### Step 5
Access:
- Grafana
- MLflow
- FastAPI docs
- Temporal UI
- Qdrant dashboard

locally.

---

# 41. Local Chaos Testing

## Mandatory Requirement

The local environment must support:
- failure injection,
- schema drift simulation,
- malformed event injection,
- streaming lag simulation,
- Spark failure simulation.

---

## Chaos Testing Purpose

Validate:
- observability quality,
- RCA quality,
- remediation quality,
- retry behavior,
- deterministic recovery.

---

# 42. Synthetic Enterprise Simulation

## Local Enterprise Simulation

The platform should simulate:
- large streaming pipelines,
- multiple DAGs,
- lineage explosions,
- operational incidents,
- Spark optimization issues.

Use:
- synthetic workloads,
- public datasets,
- replay pipelines.

---

# 43. Public Datasets For Local Testing

## Recommended Datasets

### GitHub Archive
Purpose:
- streaming events,
- developer activity analysis.

---

### NYC Taxi Dataset
Purpose:
- Spark optimization,
- partitioning experiments.

---

### StackOverflow Dumps
Purpose:
- operational RAG testing,
- metadata retrieval.

---

### SEC EDGAR
Purpose:
- large-scale ingestion,
- document intelligence,
- lineage workflows.

---

# 44. Cost Constraints

## Hard Requirement

The MVP should operate with:
- near-zero infrastructure cost,
- local-only deployment,
- optional cloud deployment.

---

## Allowed Costs

### Acceptable
- Claude subscription
- optional LLM API usage
- optional domain purchase

---

## Avoid
- always-on cloud clusters,
- managed Kubernetes,
- expensive vector DBs,
- enterprise cloud dependencies.

---

# 45. Cloud Migration Philosophy

Cloud deployment should be:
- optional,
- incremental,
- reproducible.

The platform architecture must support:
- local-first execution,
- cloud-compatible deployment.

---

## IMPORTANT

DO NOT tightly couple architecture to Azure.

Instead:
- abstract infrastructure layers,
- keep orchestration portable,
- maintain local reproducibility.

---

# 46. Kubernetes Strategy

## DO NOT USE INITIALLY

Kubernetes is deferred until:
- workflows stabilize,
- orchestration matures,
- observability stabilizes,
- local environments are reliable.

---

## Initial Runtime

Use ONLY:
- Docker Compose
- local containers
- local networking.

---

# 47. Final Local-First Philosophy

The MVP should feel like:
- a real distributed systems platform,
- reproducible infrastructure software,
- operational intelligence tooling.

The engineering depth should come from:
- orchestration,
- reliability,
- observability,
- metadata intelligence,
- agent reasoning,

NOT:
- expensive cloud infrastructure.

