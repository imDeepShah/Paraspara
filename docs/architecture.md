# Paraspara architecture

This diagram separates the human journey, agent orchestration, trust boundaries, persistence, and external model provider.

```mermaid
flowchart TB
    subgraph DEVICE[Participant device]
        WEB[Responsive multilingual web UI]
    end

    subgraph APP[Paraspara application boundary]
        API[FastAPI API]
        POLICY[Consent and persona-view policy]
        ORCH[Strands orchestration agent]

        subgraph TOOLS[Bounded Strands tools]
            T1[classify_dana]
            T2[evaluate_safeguards]
            T3[find_capacity]
        end

        HUMAN{Human decision required?}
        CASES[(SQLite cases and consent)]
        EVENTS[(Append-only audit events)]
    end

    subgraph PEOPLE[Human participants]
        PERSON[Person seeking support]
        SUPPORTER[Individual Supporter]
        PARTNER[Care Partner]
        REVIEWER[Human Review Lead]
        FUNDER[Institutional Funder]
    end

    subgraph AWS[AWS boundary]
        BEDROCK[Amazon Bedrock]
        NOVA[Global Amazon Nova 2 Lite]
    end

    PERSON -->|Need and language| WEB
    WEB -->|HTTPS / JSON| API
    API --> POLICY
    POLICY -->|Consent-controlled prompt| ORCH
    ORCH --> T1
    ORCH --> T2
    ORCH --> T3
    ORCH <-->|Inference| BEDROCK
    BEDROCK --> NOVA

    T3 <-->|Capacity only; no recipient identity| SUPPORTER
    T3 <-->|Pooled programme capacity| FUNDER

    ORCH -->|Proposed private plan| HUMAN
    HUMAN -->|Consent| PERSON
    HUMAN -->|Ground-truth check| PARTNER
    HUMAN -->|Exception only| REVIEWER

    POLICY -->|Minimum necessary fields| PARTNER
    POLICY -->|Conflict and evidence| REVIEWER
    POLICY -->|Anonymous aggregate outcome| FUNDER
    POLICY -->|No direct recipient access| SUPPORTER

    API <--> CASES
    API --> EVENTS
    ORCH --> EVENTS
    PERSON -->|Outcome confirmation| API
```

## Trust boundaries

1. **Participant device:** collects a synthetic demonstration request and displays only the selected participant's view.
2. **Application boundary:** enforces consent, redaction, case state, validation, and audit recording.
3. **AWS boundary:** receives the minimum prompt required for live inference. Real sensitive data must not be used in this hackathon build.
4. **Human authority:** consent, ground-truth verification, exceptions, and final outcome confirmation remain human decisions.

## Data minimisation by participant

| Participant | Information exposed |
| --- | --- |
| Person seeking support | Their own request, private plan, consent state, and outcome |
| Individual Supporter | Shareable constraints and required capacity; no recipient identity |
| Care Partner | Safe plan and minimum operational facts |
| Human Review Lead | Conflict, evidence, uncertainty, and available options |
| Institutional Funder | Support type, required capacity, and anonymous aggregate outcome |

## Agent execution

```mermaid
sequenceDiagram
    actor Person
    participant API as Paraspara API
    participant Agent as Strands Agent
    participant Tools as Bounded tools
    participant Bedrock as Amazon Bedrock
    actor Human as Care Partner / Review Lead

    Person->>API: Submit need and language
    API->>Agent: Consent-first interpretation request
    Agent->>Tools: classify_dana
    Agent->>Tools: evaluate_safeguards
    Agent->>Tools: find_capacity
    Agent->>Bedrock: Reason over tool results
    Bedrock-->>Agent: Structured private plan
    Agent-->>API: Plan, uncertainty, safeguards, tool trace
    API-->>Person: Review or revise private plan
    Person->>API: Consent
    API->>Human: Only the next necessary decision
    Human->>API: Verify or resolve
    API-->>Person: Support outcome
    Person->>API: Confirm outcome
    API-->>API: Record anonymous evidence and audit events
```
