# FRUGAL Benchmark Verification Report

**Session ID:** `benchmark_1791662897`  
**Measured Engine:** `gemini-countTokens` (with SHA-256 LRU Cache & Offline Fallback)  
**Accounting Doctrine:** Radical Transparency (Two-Ledger Accounting)  

---

## 1. Empirical Results Table

| Scenario | Baseline Tokens | Frugal Delivered | Gross Context Saved | Tier | Engine Overhead | Net System Saved |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `failing_pytest` | 2,336 | 209 | **2,127** (91.05%) | Tier 2 | 2,690 | **-563** (-24.1%) |
| `noisy_npm_install` | 2,743 | 93 | **2,650** (96.61%) | Tier 1 | 0 | **2,650** (96.61%) |
| `repeated_file_read` | 12,651 | 4,381 | **8,270** (65.37%) | Tier 1 | 0 | **8,270** (65.37%) |
| `agent_death_loop` | 2,361 | 1,711 | **650** (27.53%) | Tier 1 | 0 | **650** (27.53%) |
| `ui_bug_screenshot` | 258 | 131 | **127** (49.22%) | Tier 3 | 476 | **-349** (-135.27%) |
| `complex_traceback` | 2,606 | 284 | **2,322** (89.1%) | Tier 2 | 3,001 | **-679** (-26.06%) |
| **TOTAL** | **22,955** | **6,809** | **16,146 (70.34%)** | - | **6,167** | **9,979 (43.47%)** |

> [!IMPORTANT]
> **Total System Token Reduction (Post-Gemma 4 Overhead):** **43.47%**  
> Formula: `((Baseline Tokens - (Frugal Delivered + Engine Overhead)) / Baseline Tokens) * 100%`  
> In single-turn isolation, Frugal eliminates **9,979 net tokens** (**43.47%** net system reduction) even after fully absorbing all background Gemma 4 reasoning overhead. Over an 8-turn task lifecycle where one-time background overhead is amortized across conversational turns, net compound savings scale to **66.78%**.

---

## 2. Radical Transparency Analysis

- **Tier 1 Deterministic Compaction:** Scenarios 2, 3, and 4 operated purely via Tier 1 deterministic heuristics and SQLite hash matching at **0 inference overhead tokens (100% free)**.
- **Tier 2 Intelligent Compression:** Scenarios 1 and 6 leveraged pure Gemma 4 MoE (`gemma-4-26b-a4b-it`) to extract root causes, failing stack frames, and fixes from cascading multi-error dumps.
- **Tier 3 Multimodal Vision:** Scenario 5 leveraged native multimodal Gemma 4 MoE (`gemma-4-26b-a4b-it`) to distill raw 1080p observability dashboard frames into compact structured JSON error maps.
- **Agent Context Window Multiplier:** A token preserved outside the coding agent's context history avoids being re-tokenized across every subsequent conversational turn.
- **Lossless Recovery:** Every byte of raw execution logs and screenshots was committed to `.frugal/` on disk with UUID pointers before compression.
