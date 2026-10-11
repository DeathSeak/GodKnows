<!-- ═══════════════════════════════════════════════════════════════
     AGENT DIRECTIVE — READ THIS BEFORE ANYTHING ELSE
     ═══════════════════════════════════════════════════════════════
     This document is the SINGLE SOURCE OF TRUTH for the Frugal project.

     RULES:
     1. If any implementation decision conflicts with an invariant below,
        the invariant ALWAYS wins.
     2. If an edge case is not explicitly covered, derive the solution
        from the Core Principles in Section 2.
     3. Implement modules in the exact order specified in Section 13.
     4. Do NOT skip any module. Do NOT simplify any invariant.
     5. Every tool call MUST be wrapped in try/except. Failures must
        return structured error messages, never crash the MCP server.
     6. All file paths must be validated before any I/O operation.
     7. All user-facing strings must use the exact format templates
        specified in this document.
     8. Do NOT use `shell=True` anywhere in the codebase.
     9. Do NOT use `tiktoken` as the primary token counter.
    10. Gemma 4 is used for BOTH complex text compression AND visual
        analysis. It is NOT limited to screenshots.
     ═══════════════════════════════════════════════════════════════ -->

# FRUGAL — Complete Architecture Specification v2.0

**Target Agent:** Gemini-3.8-flash (Google Antigravity IDE)
**Language:** Python 3.11+
**Core Frameworks:** FastMCP, SQLite3, Google Generative AI SDK
**License:** MIT

---

## 1. Project Mission

Frugal is an MCP (Model Context Protocol) middleware that acts as a **token firewall** for AI coding agents. It intercepts tool calls (shell commands, file reads, UI screenshots), compresses the context through a **3-tier compression engine**, and preserves all raw data on disk for lossless retrieval.

**One-line pitch:** *"Frugal reduces AI agent context consumption by 80%+ while maintaining 100% diagnostic fidelity."*

---

## 2. Core Principles (Non-Negotiable Invariants)

These principles override ALL other instructions.

### P1: Tiered Compression
Frugal uses a 3-tier compression engine:
- **Tier 1 (Deterministic):** Regex/heuristics. Fast, free, sub-millisecond. Handles simple cases.
- **Tier 2 (Intelligent Text):** Gemma 4. Handles complex logs, nested tracebacks, multi-error outputs, anything regex cannot cleanly parse.
- **Tier 3 (Multimodal):** Gemma 4 vision. Handles UI screenshots.

### P2: Lossless Guarantee
NO data is ever permanently lost. Every raw log, file snapshot, and screenshot MUST be saved to `.frugal/` on disk BEFORE any compression occurs. The agent must always be able to retrieve the original data via escape hatch tools.

### P3: Progressive Disclosure
Always return the smallest actionable summary first. Raw data is hidden behind escape hatch pointers. The agent requests more only when needed.

### P4: Security by Design
All shell executions must be sanitized. Path traversal must be blocked. Secrets must be redacted. `shell=True` is NEVER used.

### P5: Measurable Impact
Token savings must be measured using the official Gemini `countTokens` API. Estimations (e.g., `len(text)//4`) are NOT acceptable for benchmark reporting.

### P6: Structured Outputs
All tool responses must use structured formats (JSON blocks or clearly delimited text sections) so calling agents can parse them reliably.

### P7: Graceful Degradation
If Gemma 4 API is unavailable, Tier 2 and Tier 3 must fall back to Tier 1 deterministic compression. The MCP server must NEVER crash due to an API failure.

### P8: Idempotent State
All state mutations (SQLite writes, file saves) must be idempotent. Calling the same tool twice with the same input must not corrupt state.

---

## 3. System Architecture

AI Coding Agent (Claude Code / Cursor / Windsurf / Cline)
        |
        | MCP Tool Calls
        v
+-----------------------------------------------------+
|              FRUGAL MCP SERVER (server.py)           |
+-----------------------------------------------------+
|  [security.py]   [redactor.py]   [breaker.py]        |
|        |              |               |              |
|        v              v               v              |
|  +-----------------------------------------------+   |
|  |         TIERED COMPRESSION ENGINE             |   |
|  |  Tier 1: squeezer.py     (Regex/Heuristics)   |   |
|  |  Tier 2: intelligence.py (Gemma 4 Text)       |   |
|  |  Tier 3: intelligence.py (Gemma 4 Vision)     |   |
|  +-----------------------+-----------------------+   |
|                          |                           |
|  [deduper.py]     [state.py]     [metrics.py]        |
|        |              |               |              |
|        v              v               v              |
|  +-----------------------------------------------+   |
|  |      storage.py  (Escape Hatch / .frugal/)    |   |
|  +-----------------------------------------------+   |
+-----------------------------------------------------+
        |
        v
Local Shell / Project Files / Screenshots

### Data Flow for `frugal_bash`:

    1. security.check_command()     -> Block if malicious
    2. breaker.check()              -> Alert if death loop detected
    3. security.run_command()       -> Execute safely (shell=False)
    4. redactor.redact()            -> Mask secrets in output
    5. storage.save_log()           -> Persist raw output to disk
    6. squeezer.squeeze()           -> Tier 1: Deterministic compression
    7. IF needs_intelligence:
         intelligence.intelligent_squeeze() -> Tier 2: Gemma 4 text
    8. token_counter.count()        -> Measure token savings
    9. metrics.record()             -> Store in SQLite
    10. Return structured response  -> Summary + Escape hatch pointer

### Data Flow for `frugal_analyze_ui`:

    1. security.validate_path()          -> Block path traversal
    2. storage.save_visual()             -> Persist raw screenshot to disk
    3. intelligence.analyze_screenshot() -> Tier 3: Gemma 4 vision
    4. token_counter.count()             -> Measure token savings
    5. metrics.record()                  -> Store in SQLite
    6. Return structured JSON            -> Analysis + Escape hatch pointer

---

## 4. Project Directory Structure

Create this EXACT file tree. Do not deviate.

    frugal/
    ├── .frugal/                      # Runtime directory (gitignored)
    │   ├── config.toml               # Runtime configuration
    │   ├── state.db                  # SQLite persistent state
    │   ├── logs/                     # Raw bash outputs
    │   │   └── run_<uuid>.log
    │   ├── visual/                   # Raw screenshots + Gemma analysis
    │   │   ├── ui_<uuid>.png
    │   │   └── ui_<uuid>.json
    │   └── files/                    # File snapshots (future use)
    │       └── snap_<uuid>.txt
    │
    ├── frugal/                       # Main Python package
    │   ├── __init__.py               # Package init, version string
    │   ├── server.py                 # FastMCP orchestration
    │   ├── security.py               # Command allowlists, path sanitization
    │   ├── redactor.py               # Secret masking
    │   ├── state.py                  # SQLite connection & schema management
    │   ├── storage.py                # Disk persistence & escape hatch
    │   ├── squeezer.py               # Tier 1: Deterministic compression
    │   ├── intelligence.py           # Tier 2 & 3: Gemma 4 compression
    │   ├── breaker.py                # Death loop detection
    │   ├── deduper.py                # File read deduplication
    │   ├── metrics.py                # Event logging & reporting
    │   └── token_counter.py          # Gemini API token counting
    │
    ├── benchmark/
    │   ├── scenarios/                # Test scenario payloads
    │   │   ├── failing_pytest/
    │   │   ├── noisy_npm_install/
    │   │   ├── repeated_file_read/
    │   │   ├── agent_death_loop/
    │   │   └── ui_bug_screenshot/
    │   ├── run_benchmark.py          # Automated benchmark script
    │   └── results/                  # Generated reports
    │       ├── results.json
    │       └── report.md
    │
    ├── tests/
    │   ├── test_squeezer.py
    │   ├── test_intelligence.py
    │   ├── test_deduper.py
    │   ├── test_breaker.py
    │   ├── test_security.py
    │   ├── test_storage.py
    │   ├── test_metrics.py
    │   └── test_server.py
    │
    ├── pyproject.toml
    ├── README.md
    └── .gitignore                    # Must include .frugal/

---

## 5. Database Schema (`state.db`)

Managed by `state.py`. All tables MUST be created on first run.

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    turn INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS command_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    command TEXT NOT NULL,
    command_hash TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN ('log','visual','file')),
    path TEXT NOT NULL,
    meta TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    raw_tokens INTEGER NOT NULL DEFAULT 0,
    compressed_tokens INTEGER NOT NULL DEFAULT 0,
    saved_tokens INTEGER NOT NULL DEFAULT 0,
    tier_used INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_file_reads_path ON file_reads(path);
CREATE INDEX IF NOT EXISTS idx_file_reads_session ON file_reads(session_id);
CREATE INDEX IF NOT EXISTS idx_command_runs_hash ON command_runs(command_hash);
CREATE INDEX IF NOT EXISTS idx_command_runs_session ON command_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_metrics_session ON metrics(session_id);
```

### `state.py` Requirements:
- Use `sqlite3.connect()` with context managers to prevent DB locks.
- Provide `get_session_id()`: returns current session ID (UUID4, cached in memory).
- Provide `get_connection()`: returns connection with `row_factory = sqlite3.Row`.
- On startup, call `initialize_db()` which creates all tables and indexes.
- If `.frugal/state.db` is locked, retry 3 times with 100ms delay before raising.
- Enable WAL mode (`PRAGMA journal_mode=WAL`) for concurrent access safety.

---

## 6. Configuration (`config.toml`)

Location: `.frugal/config.toml`. Create with defaults if missing.

```toml
[compression]
max_output_lines = 80
head_lines = 10
tail_lines = 20
grep_patterns = ["error", "fatal", "exception", "traceback", "failed"]
tier2_threshold_lines = 30

[dedupe]
enabled = true
ignore = ["package-lock.json", "pnpm-lock.yaml", "yarn.lock"]

[breaker]
max_repeats = 3
window_size = 5

[visual]
enabled = true
model = "gemma-4"
raw_escape_hatch = true

[intelligence]
enabled = true
model = "gemma-4"
fallback_to_tier1 = true

[metrics]
enabled = true
counter = "gemini"

[privacy]
redact_secrets = true

[security]
allow_shell = false
allowed_commands = [
    "pytest", "npm", "pnpm", "pip", "python", "node",
    "git", "ls", "cat", "rg", "grep", "vite", "jest",
    "cargo", "go", "make", "yarn"
]
denied_patterns = [
    "rm -rf", "sudo", "shutdown", "reboot", "mkfs",
    "curl | sh", "wget | sh", "eval", "exec",
    "> /dev/", "chmod -R 777", "nc -e", "bash -i",
    "dd if=", ":(){"
]
```

---

## 7. Module Specifications

---

### 7.1 `security.py` — Guardrails & Sanitization

**Role:** Prevents arbitrary code execution, path traversal, and command injection.

**Invariants:**
- NEVER use `subprocess.run(..., shell=True)`.
- ALWAYS use `shlex.split(command)` with `shell=False`.
- Block commands not in the allowlist.
- Block commands matching any denied pattern.
- Validate all file paths to prevent traversal.

**Functions:**

```python
def check_command(command: str) -> SecurityResult:
    """
    Validates a command against allowlist and denylist.
    Returns SecurityResult(allowed: bool, reason: str)

    Logic:
    1. Parse command with shlex.split()
    2. Extract executable (first token)
    3. Check if executable is in ALLOWED_COMMANDS
    4. Check if full command string matches any DENIED_PATTERNS
    5. Return result
    """

def run_command(command: str) -> CommandResult:
    """
    Executes a validated command safely.
    Returns CommandResult(stdout: str, stderr: str, returncode: int)

    Implementation:
    - subprocess.run(shlex.split(command), shell=False,
                     capture_output=True, text=True, timeout=120)
    - On TimeoutExpired: return CommandResult(exit_code=-1)
    - On FileNotFoundError: return CommandResult(exit_code=-2)
    """

def validate_path(path: str) -> str:
    """
    Validates and resolves a file path.
    Returns resolved absolute path.
    Raises SecurityError if path is outside project root.

    Logic:
    1. Resolve path using pathlib.Path.resolve()
    2. Get project root (current working directory)
    3. Check: resolved_path.is_relative_to(project_root)
    4. If not: raise SecurityError("Path traversal detected")
    """
```

**Data Classes:**

```python
@dataclass
class SecurityResult:
    allowed: bool
    reason: str = ""

@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int
```

**Edge Cases:**
- Empty command string -> return SecurityResult(False, "Empty command")
- Command with only whitespace -> return SecurityResult(False, "Empty command")
- `shlex.split()` raises ValueError on malformed quotes -> catch, return SecurityResult(False, "Malformed command")
- Path is a symlink pointing outside project root -> resolve symlink, then validate
- Binary file passed to `frugal_read_file` -> detect via null bytes, return error message

---

### 7.2 `redactor.py` — Secret Masking

**Role:** Strips secrets from stdout/stderr before compression AND before disk storage. Secrets must never be persisted.

**Invariants:**
- Apply BEFORE `storage.save_log()` and BEFORE any compression.
- Redaction applies to BOTH disk storage and display output.

**Regex Patterns:**

```python
SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+', r'\1=[REDACTED]'),
    (r'(?i)(secret|token|password|passwd)\s*[=:]\s*\S+', r'\1=[REDACTED]'),
    (r'(?i)(database_url|db_url|connection_string)\s*[=:]\s*\S+', r'\1=[REDACTED]'),
    (r'(?i)(aws_access_key_id|aws_secret_access_key)\s*[=:]\s*\S+', r'\1=[REDACTED]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_OPENAI_KEY]'),
    (r'ghp_[a-zA-Z0-9]{36}', '[REDACTED_GITHUB_TOKEN]'),
    (r'gho_[a-zA-Z0-9]{36}', '[REDACTED_GITHUB_TOKEN]'),
    (r'xoxb-[a-zA-Z0-9\-]+', '[REDACTED_SLACK_TOKEN]'),
    (r'(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),
]
```

**Function:**

```python
def redact(text: str) -> str:
    """
    Applies all SECRET_PATTERNS to the input text.
    Returns redacted text.
    Must be called BEFORE storage.save_log() and BEFORE compression.
    """
```

**Edge Cases:**
- Input is None or empty -> return ""
- Regex match spans multiple lines -> handle with `re.MULTILINE`
- False positives (e.g., variable named "password" in code) -> acceptable trade-off, prefer safety

---

### 7.3 `storage.py` — The Escape Hatch

**Role:** Persists all raw data to disk. This is the lossless guarantee.

**Invariants:**
- Save BEFORE any compression occurs.
- Use UUID4 for all artifact IDs.
- Register every artifact in the `artifacts` table in `state.db`.
- Create `.frugal/` subdirectories if they don't exist.

**Functions:**

```python
def save_log(raw_output: str) -> tuple[str, str]:
    """
    Saves raw command output to .frugal/logs/run_<uuid>.log
    Returns (log_id, pointer_string)

    Pointer format:
    [Raw output saved: .frugal/logs/run_<uuid>.log |
     Inspect with: frugal_get_log(log_id="<uuid>")]
    """

def save_visual(image_bytes: bytes, analysis_json: dict) -> tuple[str, str, str]:
    """
    Saves screenshot to .frugal/visual/ui_<uuid>.png
    Saves analysis JSON to .frugal/visual/ui_<uuid>.json
    Returns (visual_id, image_path, analysis_path)
    """

def save_file_snapshot(path: str, content: str) -> tuple[str, str]:
    """
    Saves file content to .frugal/files/snap_<uuid>.txt
    Returns (snapshot_id, pointer_string)
    """

def get_log_slice(log_id: str, start_line: int = 1, end_line: int = 200) -> str:
    """
    Reads a slice of raw log from disk.
    Returns the requested lines.
    If log_id not found: return error message.
    If line range exceeds file: return available lines.
    """

def get_visual(visual_id: str, raw: bool = False) -> str:
    """
    Retrieves visual analysis or raw screenshot.
    If raw=False: return the JSON analysis.
    If raw=True: return base64-encoded original image.
    """
```

**Edge Cases:**
- `.frugal/` directory doesn't exist -> create with `os.makedirs(exist_ok=True)`
- Disk is full -> catch `OSError`, return error message
- `log_id` contains path traversal characters -> validate, reject
- File is binary (contains null bytes) -> skip saving, return warning

---

### 7.4 `squeezer.py` — Tier 1: Deterministic Compression

**Role:** Fast, regex/heuristic-based compression. No LLM calls.

**Invariants:**
- Do NOT build a complex Finite State Machine (FSM). Use regex and heuristics.
- Must return a tuple: `(compressed_text: str, needs_intelligence: bool)`
- `needs_intelligence` is True when the output is too complex for Tier 1.

**Functions:**

```python
def squeeze_output(command: str, exit_code: int, raw_output: str) -> tuple[str, bool]:
    """
    Tier 1 deterministic compression.
    Returns (compressed_text, needs_intelligence)

    Pipeline:
    1. Strip ANSI escape codes and \r
    2. If exit_code == 0 and command is verbose runner -> success summary
    3. If exit_code != 0 -> extract failure block
    4. If output still > 30 lines OR has nested traceback -> needs_intelligence = True
    """

def strip_ansi(text: str) -> str:
    """
    Removes ANSI escape codes, color codes, carriage returns.
    Regex: r'\x1b\[[0-9;]*m' and r'\r'
    """

def is_verbose_command(command: str) -> bool:
    """
    Returns True for: npm install, pnpm install, pip install,
    poetry install, cargo build, yarn install
    """

def extract_failure_block(text: str) -> str:
    """
    For failing commands, extract the most relevant failure info.
    Keep: first 10 lines, last 20 lines.
    Grep middle for: error|fatal|exception|traceback|failed
    Strip internal paths: site-packages/, node_modules/, .cache/
    """

def has_nested_traceback(text: str) -> bool:
    """
    Returns True if text contains multiple 'Traceback' occurrences
    or deeply nested exception chains.
    """

def has_multiple_errors(text: str) -> bool:
    """
    Returns True if text contains 3+ distinct error signatures.
    """
```

**Decision Logic for `needs_intelligence`:**

```python
needs_intelligence = (
    len(compressed.split('\n')) > 30 or
    has_nested_traceback(compressed) or
    has_multiple_errors(compressed) or
    is_unclear_failure(compressed)  # No clear error signature found
)
```

**Output Format for Tier 1:**

    [FRUGAL SUMMARY]
    Command: <command>
    Exit code: <code>
    Status: SUCCESS|FAILED
    Compressed output: <X> lines retained from <Y> lines.

    [FAILURE SIGNATURE]
    <error message if failed>

    [ESCAPE HATCH]
    frugal_get_log(log_id="<uuid>")

**Edge Cases:**
- Output is empty -> return "[FRUGAL] Command produced no output.", False
- Output is exactly 1 line -> return as-is, False
- Command not in verbose list but exit_code == 0 -> still compress if > 50 lines
- Binary output (null bytes) -> return "[FRUGAL] Binary output suppressed.", False

---

### 7.5 `intelligence.py` — Tier 2 & 3: Gemma 4 Compression

**Role:** Handles complex text compression (Tier 2) and visual analysis (Tier 3) using Gemma 4.

**Invariants:**
- ALWAYS fall back to Tier 1 if Gemma 4 API fails.
- ALWAYS save raw data to disk BEFORE calling Gemma 4.
- Return structured JSON, never free-form text.
- Timeout: 30 seconds per API call.

**Tier 2 Function (Text Compression):**

```python
def intelligent_squeeze(raw_output: str, command: str, exit_code: int) -> str:
    """
    Tier 2: Gemma 4 analyzes complex text output.
    Returns structured JSON summary.

    Prompt:
    'You are a senior DevOps engineer analyzing terminal output
     for an AI coding agent. Be concise and actionable.

     Command: {command}
     Exit Code: {exit_code}

     Analyze this output and return a JSON object with:
     - summary: One-line description of what happened
     - root_cause: The most likely root cause
     - error_signature: The exact error message
     - affected_files: List of files likely involved
     - suggested_actions: 2-3 concrete next steps
     - confidence: high/medium/low

     Raw output:
     {raw_output}

     Return ONLY valid JSON. No markdown. No explanation.'
    """
```

**Tier 3 Function (Visual Analysis):**

```python
def analyze_screenshot(screenshot_path: str, task_hint: str = "") -> str:
    """
    Tier 3: Gemma 4 analyzes UI screenshots.
    Returns structured JSON.

    Prompt:
    'You are a UI QA engineer analyzing a screenshot for an AI
     coding agent. Return JSON with:
     - summary: One-line description
     - issues: Array of {element, problem, severity, confidence, selector_guess}
     - visible_text: Array of visible text strings
     - layout_notes: Description of layout issues
     - suggested_next_steps: 2-3 actionable steps

     Task hint: {task_hint}

     Return ONLY valid JSON. No markdown.'
    """
```

**API Call Wrapper:**

```python
def call_gemma4(prompt: str, image_path: str = None) -> str:
    """
    Calls Gemma 4 via Google Generative AI SDK.

    If image_path is provided: send as multimodal input.
    If not: send as text-only.

    Timeout: 30 seconds.
    On failure: raise GemmaAPIError (caught by caller for fallback).
    """
```

**Fallback Logic:**

```python
try:
    result = intelligence.intelligent_squeeze(raw_output, command, exit_code)
except GemmaAPIError:
    # Fall back to Tier 1
    result, _ = squeezer.squeeze_output(command, exit_code, raw_output)
    result += "\n[FRUGAL NOTE] Gemma 4 unavailable. Tier 1 compression used."
```

**Edge Cases:**
- Gemma 4 returns invalid JSON -> attempt to parse; if fails, wrap raw response in JSON
- Gemma 4 returns empty response -> fall back to Tier 1
- Image file is corrupted -> return error message, don't crash
- Image file is not an image (e.g., text file) -> return error message
- API key not set -> return error message suggesting configuration
- Rate limited -> retry once after 2 seconds, then fall back to Tier 1

---

### 7.6 `breaker.py` — Circuit Breaker

**Role:** Detects agent death loops and blind retries.

**Invariants:**
- Use SQLite `command_runs` table, NOT in-memory ring buffer.
- Track command hash + exit code.
- Trigger after 3 consecutive identical failures.

**Function:**

```python
def check_command(command: str) -> str | None:
    """
    Checks if this command triggers the circuit breaker.
    Returns alert string if triggered, None otherwise.

    Logic:
    1. Hash the command string (SHA-256)
    2. Query last 3 entries in command_runs with this hash
    3. If all 3 exist AND all have exit_code != 0 -> trigger
    4. If triggered: return structured alert
    5. Always: insert current command into command_runs
    """
```

**Alert Format:**

    [FRUGAL CIRCUIT BREAKER TRIGGERED]
    Command: <command>
    Repeated failures: 3
    Last error signature: <extracted from previous runs>

    Likely causes:
    - <cause 1>
    - <cause 2>

    Recommended actions:
    - Read the failing test file
    - Inspect configuration
    - Do NOT rerun the same command without changing code

**Edge Cases:**
- First time running a command -> no alert, just record
- Command succeeds after failures -> reset counter (don't alert)
- Database is locked -> retry 3 times, then skip breaker check (don't block execution)

---

### 7.7 `deduper.py` — File Read Deduplication

**Role:** Prevents context waste from repetitive file reading.

**Invariants:**
- Use SQLite `file_reads` table, NOT in-memory dictionary.
- Hash files with SHA-256.
- Support `force=True` to bypass deduplication.

**Function:**

```python
def check_and_read(path: str, force: bool = False) -> tuple[str, bool]:
    """
    Checks if file has been read before with same content.
    Returns (content_or_sentinel, was_deduplicated)

    Logic:
    1. Validate path via security.validate_path()
    2. Read file content
    3. Compute SHA-256 hash
    4. Query file_reads for this path + hash
    5. If match found AND not force:
       Return sentinel message, True
    6. If no match OR force:
       Update file_reads table
       Return full content, False
    """
```

**Sentinel Format:**

    [FRUGAL DEDUPE]
    File: <path>
    Status: unchanged since previous read
    Previous turn: <N>
    Lines skipped: <count>
    Hash: sha256:<first 8 chars>...
    Use force=True to reload.

**Edge Cases:**
- File doesn't exist -> return error message
- File is binary -> return "[FRUGAL] Binary file detected. Content suppressed."
- File is empty -> return "[FRUGAL] File is empty."
- File is larger than 1MB -> return first 1000 lines + warning
- Path is in ignore list (package-lock.json, etc.) -> always return full content
- Encoding error -> try utf-8, then latin-1, then return error

---

### 7.8 `metrics.py` — Event Logging & Reporting

**Role:** Records token savings for every tool call.

**Invariants:**
- Record EVERY tool call, even if no compression occurred.
- Use `token_counter.py` for actual counts.
- Store in SQLite `metrics` table.

**Functions:**

```python
def record_bash_event(session_id, command, exit_code, raw_output,
                      compressed_output, tier_used, latency_ms):
    """
    Records a frugal_bash event.
    Counts raw_tokens and compressed_tokens using token_counter.
    Inserts into metrics table.
    """

def record_read_event(session_id, path, was_deduplicated,
                      raw_content, compressed_content):
    """Records a frugal_read_file event."""

def record_visual_event(session_id, visual_id, raw_tokens, compressed_tokens):
    """Records a frugal_analyze_ui event."""

def get_session_stats(session_id) -> dict:
    """
    Returns aggregate stats for the session:
    {
        "bash_calls": int,
        "file_reads": int,
        "visual_analyses": int,
        "duplicate_reads_blocked": int,
        "death_loops_interrupted": int,
        "baseline_tokens": int,
        "frugal_tokens": int,
        "saved_tokens": int,
        "reduction_percent": float,
        "token_counter": "gemini-countTokens"
    }
    """
```

---

### 7.9 `token_counter.py` — Gemini API Token Counting

**Role:** Measures actual token counts using the official Gemini API.

**Invariants:**
- Do NOT use `tiktoken` as primary counter. It is inaccurate for Gemini/Gemma.
- Use the Gemini `countTokens` API endpoint.
- Cache results by content hash to avoid redundant API calls.
- Fall back to `len(text) // 4` ONLY if API is unavailable, and mark as estimated.

**Functions:**

```python
def count_text_tokens(text: str, model: str = "gemma-4") -> int:
    """
    Counts tokens for text using Gemini countTokens API.

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:countTokens
    Body: {"contents": [{"parts": [{"text": text}]}]}

    Cache by SHA-256 of text to avoid redundant calls.
    On API failure: return len(text) // 4 and mark as estimated.
    """

def count_image_tokens(image_path: str, model: str = "gemma-4") -> int:
    """
    Counts tokens for an image using Gemini countTokens API.

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:countTokens
    Body: {"contents": [{"parts": [{"inline_data":
           {"mime_type": "image/png", "data": base64}}]}]}

    On API failure: return 5000 as rough estimate, mark as estimated.
    """

def count_payload_tokens(payload: str) -> int:
    """
    Counts tokens for a complete tool response payload.
    Includes compressed text + pointers + escape hatch strings.
    """
```

**Caching Strategy:**

```python
# In-memory LRU cache (max 1000 entries)
@lru_cache(maxsize=1000)
def _cached_count(text_hash: str, text: str, model: str) -> int:
    ...
```

---

### 7.10 `server.py` — FastMCP Orchestration

**Role:** The main MCP server. Wires all modules together.

**Invariants:**
- Do NOT put business logic in server.py. Only orchestration.
- Every tool must be wrapped in try/except.
- Every tool must return a string (MCP requirement).
- Initialize all modules on startup.

**Tools to Register:**

```python
from fastmcp import FastMCP

mcp = FastMCP("Frugal")

@mcp.tool()
def frugal_bash(command: str) -> str:
    """Executes a shell command with Frugal tiered compression."""
    # 1. Security check
    # 2. Circuit breaker check
    # 3. Execute command
    # 4. Redact secrets
    # 5. Save raw output (escape hatch)
    # 6. Tier 1 compression
    # 7. If needs_intelligence: Tier 2 compression
    # 8. Record metrics
    # 9. Return formatted response

@mcp.tool()
def frugal_read_file(path: str, force: bool = False) -> str:
    """Reads a file with hash deduplication."""
    # 1. Validate path
    # 2. Check deduplication
    # 3. Return content or sentinel
    # 4. Record metrics

@mcp.tool()
def frugal_get_log(log_id: str, start_line: int = 1, end_line: int = 200) -> str:
    """Escape hatch: retrieves raw logs from disk."""
    # 1. Validate log_id
    # 2. Read slice from disk
    # 3. Return content

@mcp.tool()
def frugal_analyze_ui(screenshot_path: str, task_hint: str = "") -> str:
    """Analyzes UI screenshot using Gemma 4 multimodal."""
    # 1. Validate path
    # 2. Save raw screenshot
    # 3. Tier 3: Gemma 4 analysis
    # 4. Save analysis JSON
    # 5. Record metrics
    # 6. Return structured JSON + escape hatch

@mcp.tool()
def frugal_get_visual(visual_id: str, raw: bool = False) -> str:
    """Escape hatch: retrieves visual analysis or raw screenshot."""
    # 1. Validate visual_id
    # 2. If raw: return base64 image
    # 3. If not raw: return JSON analysis

@mcp.tool()
def frugal_stats() -> str:
    """Returns token savings metrics for current session."""
    # 1. Query metrics table
    # 2. Return formatted stats
```

**Startup Initialization:**

```python
def initialize():
    """Called once when MCP server starts."""
    state.initialize_db()
    storage.ensure_directories()
    config.load_or_create()
```

---

## 8. Edge Cases & Failure Handling Matrix

| Scenario | Handling |
|---|---|
| Gemma 4 API down | Fall back to Tier 1. Add note to output. |
| SQLite DB locked | Retry 3x with 100ms delay. If still locked, skip state ops. |
| File path traversal attempt | Block. Return SecurityError message. |
| Binary file passed to read_file | Detect null bytes. Return suppression message. |
| Command timeout (>120s) | Kill process. Return timeout error. |
| Empty command output | Return "[FRUGAL] Command produced no output." |
| Screenshot is corrupted | Return error. Don't crash. |
| API key not configured | Return setup instructions. Don't crash. |
| File > 1MB | Return first 1000 lines + warning. |
| Disk full | Catch OSError. Return error message. |
| Concurrent access to state.db | Use WAL mode. Retry on lock. |
| Gemma 4 returns invalid JSON | Wrap in fallback structure. |
| Command with shell metacharacters | shlex.split handles. If fails, block. |
| Symlink pointing outside project | Resolve, validate, block if outside. |

---

## 9. Benchmark Specification

### Scenarios to Test:

1. **failing_pytest:** Run `pytest` with a failing test. Measure compression.
2. **noisy_npm_install:** Run `npm install`. Measure success compression.
3. **repeated_file_read:** Read same file 3 times. Measure dedup savings.
4. **agent_death_loop:** Run same failing command 3 times. Measure breaker.
5. **ui_bug_screenshot:** Analyze a screenshot. Measure visual compression.
6. **complex_traceback:** Run command producing nested traceback. Measure Tier 2.

### Benchmark Output Format:

```json
{
  "session_id": "benchmark_<timestamp>",
  "token_counter": "gemini-countTokens",
  "scenarios": [
    {
      "name": "failing_pytest",
      "baseline_tokens": 41236,
      "frugal_tokens": 9874,
      "saved_tokens": 31362,
      "reduction_percent": 76.06,
      "tier_used": 2
    }
  ],
  "total": {
    "baseline_tokens": 139970,
    "frugal_tokens": 26584,
    "saved_tokens": 113386,
    "reduction_percent": 81.01
  }
}
```

### `run_benchmark.py` Requirements:
- Run each scenario sequentially.
- Measure baseline (raw output tokens) vs Frugal (compressed tokens).
- Use `token_counter.py` for all measurements.
- Generate `results.json` and `report.md`.
- Print summary table to stdout.

---

## 10. `pyproject.toml`

```toml
[project]
name = "frugal"
version = "2.0.0"
description = "Token firewall for AI coding agents"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=0.1.0",
    "google-generativeai>=0.8.0",
    "toml>=0.10.2",
    "click>=8.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

---

## 11. `.gitignore`

    .frugal/
    __pycache__/
    *.pyc
    *.egg-info/
    dist/
    build/
    .venv/
    *.db

---

## 12. README.md Structure

    # Frugal — A Token Firewall for AI Coding Agents

    ## Problem
    AI agents waste context on verbose logs, repeated reads, and screenshots.

    ## Solution
    Frugal is an MCP middleware with a 3-tier compression engine.

    ## Architecture
    [Include architecture diagram]

    ## Benchmark Results
    [Include benchmark table]

    ## Quick Start
    pip install -e .
    frugal init
    frugal bench

    ## Security
    Command allowlisting, path validation, secret redaction.
    Production roadmap: sandboxed execution.

    ## License
    MIT

---

## 13. Implementation Order

Implement in this EXACT order. Do not skip.

### Phase 1: Foundation
1. `state.py` — SQLite schema and connection management
2. `storage.py` — Disk persistence and escape hatch
3. `security.py` — Command validation and path sanitization
4. `redactor.py` — Secret masking

### Phase 2: Compression Engine
5. `squeezer.py` — Tier 1 deterministic compression
6. `intelligence.py` — Tier 2 & 3 Gemma 4 compression

### Phase 3: Agent Protection
7. `breaker.py` — Circuit breaker
8. `deduper.py` — File read deduplication

### Phase 4: Metrics
9. `token_counter.py` — Gemini API token counting
10. `metrics.py` — Event logging and reporting

### Phase 5: Orchestration
11. `server.py` — FastMCP server with all tools

### Phase 6: Validation
12. `benchmark/run_benchmark.py` — Benchmark harness
13. `tests/` — Unit tests for all modules
14. `README.md` — Documentation

---

## 14. Testing Requirements

Each module MUST have corresponding unit tests.

### Minimum Test Coverage:
- `test_security.py`: Test allowlist, denylist, path traversal, shell=False
- `test_squeezer.py`: Test ANSI stripping, success compression, failure extraction
- `test_intelligence.py`: Test Gemma 4 mock calls, fallback on API failure
- `test_deduper.py`: Test hash matching, force=True, binary files
- `test_breaker.py`: Test 3-failure trigger, reset on success
- `test_storage.py`: Test save/retrieve, escape hatch, missing files
- `test_metrics.py`: Test recording, aggregation, stats
- `test_server.py`: Integration test of all MCP tools

### Test Invariants:
- All tests must pass with `pytest tests/`
- No test should require network access (mock Gemma 4 API)
- No test should modify files outside `.frugal/`

---

## 15. Final Validation Checklist

Before considering the project complete, verify:

- [ ] All 11 Python modules exist and are importable
- [ ] `state.db` is created on first run with all tables
- [ ] `.frugal/` directory structure is created automatically
- [ ] `frugal_bash` executes commands without `shell=True`
- [ ] `frugal_bash` saves raw output before compression
- [ ] `frugal_bash` escalates to Gemma 4 for complex output
- [ ] `frugal_read_file` deduplicates unchanged files
- [ ] `frugal_read_file` supports `force=True`
- [ ] `frugal_get_log` retrieves raw logs from disk
- [ ] `frugal_analyze_ui` saves screenshot before analysis
- [ ] `frugal_analyze_ui` returns structured JSON
- [ ] `frugal_get_visual` supports `raw=True` for original image
- [ ] `frugal_stats` returns measured token savings
- [ ] Circuit breaker triggers after 3 identical failures
- [ ] Secrets are redacted from output
- [ ] Path traversal is blocked
- [ ] Gemma 4 failure falls back to Tier 1 gracefully
- [ ] Benchmark runs all 6 scenarios
- [ ] Benchmark uses Gemini countTokens API
- [ ] All tests pass
- [ ] README.md is complete with benchmark table
- [ ] LICENSE file exists (MIT)
- [ ] .gitignore excludes .frugal/

---

## 16. Key Presentation Points for Judges

1. **3-Tier Compression Engine:** Deterministic regex for speed, Gemma 4 for intelligence, multimodal for vision.
2. **Lossless Guarantee:** Every raw artifact is preserved on disk with escape hatch retrieval.
3. **Measurable Impact:** Real token counts via Gemini API, not estimates.
4. **Security by Design:** Command allowlisting, path validation, secret redaction, sandbox roadmap.
5. **Production Credibility:** SQLite state, config files, comprehensive tests, structured error handling.

---

**END OF SPECIFICATION. BEGIN IMPLEMENTATION.**
