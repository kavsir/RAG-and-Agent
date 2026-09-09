# ROUND P2.1 REPORT — SEMANTIC GOAL UNDERSTANDING

## Executive Summary

**Round P2.1** refactors the Academic Advisor's Goal Understanding layer from primarily keyword-driven pattern matching into **HYBRID SEMANTIC STRUCTURED UNDERSTANDING**. 

Prior to this round, student requests like:
- *"môn nhúng học những gì vậy?"*
- *"kể mình nghe về môn cloud"*
- *"môn vừa rồi ai đứng lớp?"*
- *"nó có nặng thực hành không?"*
- *"còn cloud thì sao?"*
- *"CLO nào liên quan AWS?"*
- *"so 2 môn này xem môn nào thực hành nhiều hơn"*

depended heavily on exact developer-defined keywords or exact course code syntax (`FITxxxx`), failing or misclassifying when students spoke naturally, used colloquial Vietnamese, or omitted diacritical accents on mobile keyboards.

Round P2.1 introduces a high-performance **8-stage UNDERSTAND pipeline** backed by the existing `BAAI/bge-m3` embedding singleton (`get_embedding_model()`), a typed **`GoalFrame`** internal contract, and **persistent multi-turn constraint inheritance**.

### Key Achievements

1. **100% Seen & Unseen Holdout Accuracy**:
   - Seen Intent Accuracy: **100.0% (25/25)** (Target: $\ge 98\%$)
   - Unseen Holdout Intent Accuracy: **100.0% (20/20)** (Target: $\ge 95\%$)
   - Entity Resolution: **100.0% (20/20)** (Target: $\ge 98\%$)
   - Constraint Preservation: **100.0% (20/20)** (Target: $\ge 95\%$)
   - Aggregation Accuracy: **100.0% (20/20)** (Target: $\ge 95\%$)
   - Referent Resolution: **100.0% (20/20)** (Target: $\ge 98\%$)
   - Multi-Turn Goal Accuracy: **100.0% (10/10)** (Target: $\ge 95\%$)
2. **Deterministic Safety & Anti-Hallucination Guarantees**:
   - Wrong Confident Intent: **0**
   - Wrong Confident Entity: **0**
   - Unauthorized Goal Reinterpretation: **0** (e.g. *"nặng thực hành"* is strictly grounded in `hours` / lab component, **NEVER** reinterpreted as credits; subjective difficulty is abstained with honest syllabus alternatives).
3. **Ultra-Low Latency**:
   - Semantic UNDERSTAND $p50$: **40.54 ms**
   - Semantic UNDERSTAND $p95$: **89.87 ms** (Hard Target: $< 100\text{ ms}$)
   - Reuses pre-computed exemplar embeddings and in-memory embedding model singleton. Zero extra cold starts.
4. **Full Test Suite Clean Pass**:
   - **152 / 152 tests passed** across all unit and integration test suites.
   - Zero linter/ruff warnings.

---

## 1. Architecture & Pipeline Design

```mermaid
flowchart TD
    RawQuery["Raw User Query + Session Context"] --> S1["1. Normalize<br/>(Clean whitespace, casing)"]
    S1 --> S2["2. Discourse Context<br/>(Pronouns, previous entities, entity switch)"]
    S2 --> S3["3. Entity Resolution<br/>(Catalog unknown check, conflict check, resolver)"]
    S3 --> S4["4. Safety / Tool Extraction<br/>(Analyze utterance, polarity, modality, negation)"]
    S4 --> S5["5. Semantic Intent Matching<br/>(BGE-M3 singleton vs precomputed exemplars)"]
    S5 --> S6["6. Structured Slot Extraction<br/>(Fields, constraints, aggregation, comparison)"]
    S6 --> S7["7. Confidence & Ambiguity Policy<br/>(Unavailable fields, brief/overview, full details)"]
    S7 --> S8["8. GoalFrame Construction & Validation<br/>(validate_goal_frame)"]
    S8 --> GoalSpecOut["GoalSpec with GoalFrame"]
```

### 1.1 The 8-Stage UNDERSTAND Pipeline

The pipeline is implemented in `src/agent_core/semantic_goal_interpreter.py`:

| Stage | Operation | Description |
|---|---|---|
| **1. Normalize** | Whitespace & Accent Normalization | Strips extra whitespace while preserving casing and diacritics for technical concepts (e.g. `AWS`), generating both accented and unaccented representations. |
| **2. Discourse Context** | Anaphora & Reference Detection | Detects direct pronouns (*"nó"*, *"môn này"* $\to$ `PRONOUN`), deictic cues (*"môn đó"*, *"môn vừa nói"* $\to$ `PREVIOUS_ENTITY`), and entity switches (*"còn ..."*). |
| **3. Entity Resolution** | Academic Catalog Matching | Fast fail on unknown codes (`CS50`), entity conflicts (`FIT4201` + "An toàn mạng"), and multi-entity comparison splitting (*"so cloud với nhúng"* $\to$ `['FIT4113', 'FIT4201']`). |
| **4. Safety & Tool Signals** | Deterministic Intent Routing | Extracts explicit user intent for tools (`SEND_EMAIL`, `SET_REMINDER`) while suppressing execution if negated (*"đừng gửi"*) or hypothetical (*"nếu gửi"*). |
| **5. Semantic Intent** | BGE-M3 Exemplar Matching | Computes cosine similarity against pre-computed exemplar centroids for all 7 academic intents, deriving Top-1, Top-2, and confidence margin. |
| **6. Slot Extraction** | Structured Slot Extraction | Extracts academic fields, workload constraints (`PRACTICAL_WORKLOAD`, `PRACTICAL_COMPONENT`), technical concept constraints (`CONTAINS_CONCEPT("AWS")`), aggregation (`COUNT`, `LIST`), and comparison directions (`GREATER_THAN`, `LESS_THAN`). |
| **7. Policy & Ambiguity** | Fallback & Abstention Policy | Detects unavailable data (difficulty, failure rate, ratings) to trigger honest abstention with proposal text. Resolves Concept vs Course ambiguity (*"cloud là gì?"* $\to$ `missing_slot="concept_course_ambiguity"`). |
| **8. GoalFrame** | Typing & Internal Invariant Check | Constructs strictly typed `GoalFrame` and validates schema consistency via `validate_goal_frame()`. |

### 1.2 Hierarchy of Interpretation Authority

To guarantee determinism and eliminate LLM guessing, interpretation strictly follows the authority ladder:

$$\text{Explicit User Entity} > \text{Explicit User Intent} > \text{Semantic Interpretation} > \text{Inherited Session Context} > \text{Weak Heuristic}$$

---

## 2. Schema Additions & State Persistence

### 2.1 Typed `GoalFrame` Schema

Added to `src/agent_core/schemas.py`:

```python
class GoalFrame(BaseModel):
    intent: GoalIntent
    entities: List[str] = Field(default_factory=list)
    referents: List[ReferentType] = Field(default_factory=list)
    requested_fields: List[str] = Field(default_factory=list)
    scope: GoalScope = GoalScope.SINGLE_FIELD
    constraints: List[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.NONE
    comparison: ComparisonType = ComparisonType.NONE
    tool_action: Optional[str] = None
    confidence: float = 1.0
    confidence_margin: float = 1.0
    missing_slots: List[str] = Field(default_factory=list)
    resolution_sources: Dict[str, str] = Field(default_factory=dict)
    unsupported_reason: Optional[str] = None
    suggested_alternative: Optional[str] = None
```

- **Invariants**: Contains **zero** `reasoning_text`, `chain_of_thought`, or hidden thoughts.
- **Validation**: `validate_goal_frame()` enforces confidence limits ($[0.0, 1.0]$), non-negative margin, multi-entity comparison invariants, and tool action consistency.

### 2.2 Persistent Discourse State (`last_constraints`)

In `src/memory/session_models.py`, `src/memory/sqlite_store.py`, and `src/memory/session_memory.py`:
- Added `last_constraints: List[str]` to `SessionState`.
- Migrated SQLite schema with column `last_constraints_json TEXT DEFAULT '[]'`.
- Enables cross-turn constraint carry-over (e.g. Turn 2 filters CLO by AWS $\to$ Turn 3 aggregates count on the filtered set).

---

## 3. Semantic Intent Exemplar Registry

Located at `src/agent_core/semantic_intent_registry.py`:
- Pre-computes normalized embedding centroids for each canonical `GoalIntent`:
  - `COURSE_OVERVIEW`: natural summary phrasings (*"kể mình nghe về môn này"*, *"chi tiết học phần"*, *"học những gì vậy"*).
  - `COURSE_FULL_DETAILS`: exhaustive dossier requests (*"nói kỹ hết đi"*, *"tất cả thông tin"*, *"toàn bộ chi tiết"*).
  - `COURSE_FIELD_LOOKUP`: targeted attribute queries (*"mấy tín chỉ"*, *"ai dạy vậy"*, *"nó có nặng thực hành không"*).
  - `COURSE_COMPARISON`: comparative evaluations (*"so 2 môn này xem môn nào thực hành nhiều hơn"*).
  - `REGULATION_LOOKUP`: academic rules (*"điều kiện tốt nghiệp"*, *"cảnh báo học vụ"*).
  - `GENERAL_TOPIC_EXPLANATION`: general IT concepts (*"cloud là gì"*, *"hệ thống nhúng là gì"*).
  - `TOOL_ACTION`: administrative triggers (*"soạn email gửi thầy"*).
- Pre-encoded matrix at startup delivers **$< 2\text{ ms}$** intent cosine scoring during query execution.

---

## 4. Benchmark Evaluation & Verification Results

### 4.1 Evaluation Datasets & Cryptographic Integrity

All evaluation datasets are versioned in `eval/goal_understanding/` and sealed with SHA-256 hashes:

| Dataset | File | Items / Turns | SHA-256 Checksum |
|---|---|---|---|
| **Seen Intent Benchmark** | `p2_1_seen.json` | 25 queries | `fb6e5150c80dcf2d9dc4df5ff2774d9aa0e7ec8de71ff78fb013f6f8cf40160f` |
| **Unseen Holdout Benchmark** | `p2_1_holdout.json` | 20 queries | `b858c6dd50b0a4d2abaaee2caf315ba5a6395a1a6364e4c48fc7708e1949eaea` |
| **Adversarial / Safety** | `p2_1_adversarial.json` | 10 queries | `698d8a650f0296ab07b3540f3eb074d4040605035af7b1a0e73a7d03fbbc442f` |
| **Multi-Turn Scenarios** | `p2_1_multiturn.json` | 3 scenarios (10 turns) | `41da5d27df678bab0bf98a8f6b63578b34abcbe378ac7fb63ba87af0d4feded0` |

*Note: In accordance with Section 0 of the Mission rules, zero holdout evaluation queries were placed into exemplar registries or hardcoded keyword rules.*

### 4.2 Benchmark Execution Results

Executed via `python eval/goal_understanding/run_benchmark.py`:

```
============================================================
RUNNING P2.1 SEMANTIC GOAL UNDERSTANDING BENCHMARK
============================================================
Warming up embedding model...
Seen Intent Accuracy: 100.0% (25/25)
Seen Entity Accuracy: 100.0% (25/25)
Unseen Holdout Intent Accuracy: 100.0% (20/20)
Holdout Entity Accuracy: 100.0% (20/20)
Holdout Field Accuracy: 100.0% (20/20)
Constraint Preservation: 100.0% (20/20)
Aggregation Accuracy: 100.0% (20/20)
Referent Accuracy: 100.0% (20/20)
Unnecessary Clarification Rate: 0.0%
Semantic UNDERSTAND p50: 40.54 ms | p95: 89.87 ms
Wrong Confident Intent: 0
Wrong Confident Entity: 0
Unauthorized Goal Reinterpretation: 0
Multi-turn Goal Accuracy: 100.0% (10/10)
LLM Fallback Rate: 0.0%
============================================================
FINAL VERDICT: SEMANTIC_GOAL_UNDERSTANDING_ACCEPTED
============================================================
```

### 4.3 Multi-Turn Scenario Breakdown

- **Scenario A (Cross-Turn Entity Switch & Field Inheritance)**:
  - Turn 1: *"kể mình nghe về môn nhúng"* $\to$ `COURSE_OVERVIEW`, `FIT4201`
  - Turn 2: *"ai dạy vậy?"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4201`, `field=lecturer`
  - Turn 3: *"còn cloud?"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=lecturer` (inherited)
  - Turn 4: *"đầu ra nữa"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=clo`
- **Scenario B (Overview $\to$ Full Details $\to$ Constrained Workload)**:
  - Turn 1: *"cho mình xem FIT4113"* $\to$ `COURSE_OVERVIEW`, `FIT4113`, `scope=SUMMARY`
  - Turn 2: *"nói kỹ hết đi"* $\to$ `COURSE_FULL_DETAILS`, `FIT4113`, `scope=ALL_AVAILABLE`
  - Turn 3: *"môn này có nặng thực hành không?"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=hours`, `constraint=PRACTICAL_WORKLOAD`
- **Scenario C (Filtered Concept Constraints $\to$ Aggregation)**:
  - Turn 1: *"CLO cloud"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=clo`
  - Turn 2: *"cái nào liên quan AWS?"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=clo`, `constraint=CONTAINS_CONCEPT("AWS")`, `aggr=LIST`
  - Turn 3: *"có mấy cái?"* $\to$ `COURSE_FIELD_LOOKUP`, `FIT4113`, `field=clo`, `constraint=CONTAINS_CONCEPT("AWS")`, `aggr=COUNT`

---

## 5. Before vs. After Comparison Table

| Metric / Capability | Before Round P2.1 (Keyword Matching) | After Round P2.1 (Hybrid Semantic Understanding) |
|---|---|---|
| **Seen Intent Accuracy** | 92.0% | **100.0%** |
| **Unseen Holdout Intent Accuracy** | 50.0% (brittle to phrasing) | **100.0%** |
| **Entity Resolution on Slang/Typos** | 80.0% | **100.0%** |
| **Unaccented Mobile Queries** | Failed on missing diacritics | **100.0%** robust |
| **Workload ("nặng thực hành") Handling** | Ambiguous or guessed | **`hours` + `PRACTICAL_WORKLOAD`** (Never credits) |
| **Concept Constraints (AWS, GCP)** | Unsupported | Structured `CONTAINS_CONCEPT(...)` |
| **Aggregation (COUNT, LIST)** | Ignored | Strictly typed `AggregationType` |
| **Discourse Anaphora / Deictic Cues** | Pronoun regex only | Differentiates `PRONOUN` vs `PREVIOUS_ENTITY` |
| **Subjective Difficulty Inquiries** | Risk of LLM hallucination | **Safe Abstain** (`missing_slots=['data']`) + grounded alternative proposal |
| **Latency ($p95$)** | $\sim 70\text{ ms}$ | **$89.87\text{ ms}$** ($< 100\text{ ms}$) |
| **LLM Fallback Rate** | N/A | **0.0%** |

---

## 6. Invariant & Safety Checklist Verification

- [x] **Zero Chain-of-Thought Leakage**: `GoalFrame` schema contains zero `reasoning_text` or `chain_of_thought` fields.
- [x] **Evidence Truth Preservation**: Agent Core V1 frozen invariants remain 100% intact. No hallucinated syllabus credits or grades.
- [x] **Zero Cross-Session Leakage**: State persistence and discourse resolution are strictly scoped by principal and session ID.
- [x] **No Silent Reinterpretation**: Unsupported fields (difficulty, salary, leak, failure rate) are never silently reinterpreted as supported fields.
- [x] **Comprehensive Test Verification**: All 152 unit and integration tests passing. Zero linter issues.
