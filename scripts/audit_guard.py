"""Protege a baseline publicada e a reserva temporal, sem dependências externas."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEVELOPMENT_END = datetime(2025, 1, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 7, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 7, 1, tzinfo=timezone.utc)


def verify_baseline(root=ROOT):
    lock = json.loads((root / "docs/audit/baseline-lock.json").read_text())
    for name, expected in lock["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Baseline publicada alterada: {name}")
    return lock


def require_locked_holdout(root=ROOT):
    policy = json.loads((root / "docs/holdout-lock.json").read_text())
    if (policy.get("status") != "reserved_locked" or policy.get("timezone") != "UTC"
            or datetime.fromisoformat(policy["start"]) != HOLDOUT_START
            or datetime.fromisoformat(policy["end_exclusive"]) != HOLDOUT_END):
        raise ValueError("Reserva do holdout deve permanecer fechada neste estágio")
    return policy


def require_legacy_research_allowed(argv, root=ROOT):
    if argv and argv[0] not in {"download-data", "download-archive", "validate-data", "backtesting"}:
        return
    if (root / "docs/holdout-lock.json").exists():
        require_locked_holdout(root)
    # Também bloqueia se docs não estiver montado no Compose base.
    raise ValueError(
        "Holdout reservado: o fluxo histórico lê/adquire candles de fronteira após 2025-07-01 "
        "e pode sobrescrever resultados publicados. Use scripts/run_audit.py; nenhum holdout foi aberto."
    )


def require_development_dates(dates):
    if any(date.tzinfo is None or date.utcoffset().total_seconds() != 0
           or not DEVELOPMENT_START <= date < DEVELOPMENT_END for date in dates):
        raise ValueError("Auditoria de indicadores aceita somente datas UTC de desenvolvimento em 2024")
