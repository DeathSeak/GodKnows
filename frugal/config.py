"""Configuration loader and schema definition for Frugal."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import List

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

DEFAULT_CONFIG_TOML = """[compression]
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
"""


@dataclass(frozen=True)
class CompressionConfig:
    max_output_lines: int = 80
    head_lines: int = 10
    tail_lines: int = 20
    grep_patterns: List[str] = field(
        default_factory=lambda: ["error", "fatal", "exception", "traceback", "failed"]
    )
    tier2_threshold_lines: int = 30


@dataclass(frozen=True)
class DedupeConfig:
    enabled: bool = True
    ignore: List[str] = field(
        default_factory=lambda: ["package-lock.json", "pnpm-lock.yaml", "yarn.lock"]
    )


@dataclass(frozen=True)
class BreakerConfig:
    max_repeats: int = 3
    window_size: int = 5


@dataclass(frozen=True)
class VisualConfig:
    enabled: bool = True
    model: str = "gemma-4"
    raw_escape_hatch: bool = True


@dataclass(frozen=True)
class IntelligenceConfig:
    enabled: bool = True
    model: str = "gemma-4"
    fallback_to_tier1: bool = True


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool = True
    counter: str = "gemini"


@dataclass(frozen=True)
class PrivacyConfig:
    redact_secrets: bool = True


@dataclass(frozen=True)
class SecurityConfig:
    allow_shell: bool = False
    allowed_commands: List[str] = field(
        default_factory=lambda: [
            "pytest", "npm", "pnpm", "pip", "python", "node",
            "git", "ls", "cat", "rg", "grep", "vite", "jest",
            "cargo", "go", "make", "yarn"
        ]
    )
    denied_patterns: List[str] = field(
        default_factory=lambda: [
            "rm -rf", "sudo", "shutdown", "reboot", "mkfs",
            "curl | sh", "wget | sh", "eval", "exec",
            "> /dev/", "chmod -R 777", "nc -e", "bash -i",
            "dd if=", ":(){"
        ]
    )


@dataclass(frozen=True)
class FrugalConfig:
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    breaker: BreakerConfig = field(default_factory=BreakerConfig)
    visual: VisualConfig = field(default_factory=VisualConfig)
    intelligence: IntelligenceConfig = field(default_factory=IntelligenceConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


_CONFIG_CACHE: FrugalConfig | None = None


def get_default_config_path(root_dir: Path | None = None) -> Path:
    base = root_dir or Path.cwd()
    return base / ".frugal" / "config.toml"


def load_or_create_config(config_path: Path | None = None) -> FrugalConfig:
    """
    Loads config from config.toml, creating default if not found.
    """
    target = config_path or get_default_config_path()

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")

    try:
        content = target.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))
    except Exception:
        # Fall back to default config if parsing fails
        return FrugalConfig()

    comp_data = data.get("compression", {})
    compression = CompressionConfig(
        max_output_lines=comp_data.get("max_output_lines", 80),
        head_lines=comp_data.get("head_lines", 10),
        tail_lines=comp_data.get("tail_lines", 20),
        grep_patterns=comp_data.get("grep_patterns", ["error", "fatal", "exception", "traceback", "failed"]),
        tier2_threshold_lines=comp_data.get("tier2_threshold_lines", 30),
    )

    dedupe_data = data.get("dedupe", {})
    dedupe = DedupeConfig(
        enabled=dedupe_data.get("enabled", True),
        ignore=dedupe_data.get("ignore", ["package-lock.json", "pnpm-lock.yaml", "yarn.lock"]),
    )

    breaker_data = data.get("breaker", {})
    breaker = BreakerConfig(
        max_repeats=breaker_data.get("max_repeats", 3),
        window_size=breaker_data.get("window_size", 5),
    )

    visual_data = data.get("visual", {})
    visual = VisualConfig(
        enabled=visual_data.get("enabled", True),
        model=visual_data.get("model", "gemma-4"),
        raw_escape_hatch=visual_data.get("raw_escape_hatch", True),
    )

    intel_data = data.get("intelligence", {})
    intelligence = IntelligenceConfig(
        enabled=intel_data.get("enabled", True),
        model=intel_data.get("model", "gemma-4"),
        fallback_to_tier1=intel_data.get("fallback_to_tier1", True),
    )

    metrics_data = data.get("metrics", {})
    metrics = MetricsConfig(
        enabled=metrics_data.get("enabled", True),
        counter=metrics_data.get("counter", "gemini"),
    )

    privacy_data = data.get("privacy", {})
    privacy = PrivacyConfig(
        redact_secrets=privacy_data.get("redact_secrets", True),
    )

    sec_data = data.get("security", {})
    security = SecurityConfig(
        allow_shell=sec_data.get("allow_shell", False),
        allowed_commands=sec_data.get("allowed_commands", [
            "pytest", "npm", "pnpm", "pip", "python", "node",
            "git", "ls", "cat", "rg", "grep", "vite", "jest",
            "cargo", "go", "make", "yarn"
        ]),
        denied_patterns=sec_data.get("denied_patterns", [
            "rm -rf", "sudo", "shutdown", "reboot", "mkfs",
            "curl | sh", "wget | sh", "eval", "exec",
            "> /dev/", "chmod -R 777", "nc -e", "bash -i",
            "dd if=", ":(){"
        ]),
    )

    return FrugalConfig(
        compression=compression,
        dedupe=dedupe,
        breaker=breaker,
        visual=visual,
        intelligence=intelligence,
        metrics=metrics,
        privacy=privacy,
        security=security,
    )


def get_config(reload: bool = False, config_path: Path | None = None) -> FrugalConfig:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None or reload:
        _CONFIG_CACHE = load_or_create_config(config_path)
    return _CONFIG_CACHE
