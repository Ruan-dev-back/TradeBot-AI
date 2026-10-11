"""Executa auditoria sem aquisições, preservando resultados e o holdout reservado."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from audit_guard import ROOT, require_locked_holdout, verify_baseline
from risk_model import build_analysis, render_report


def validate_bias(summary, lock, root=ROOT):
    manifest = json.loads((root / "docs/evidence/data_manifest.json").read_text())
    if (summary.get("baseline_files") != lock["files"] or summary.get("period") != "20240101-20250101"
            or summary.get("holdout_prices_inspected") is not False
            or summary.get("passed") is not True
            or summary.get("candles") != 9528
            or summary.get("source_dataset_sha256") != manifest["sha256"]
            or summary.get("audit_script_sha256") != hashlib.sha256((root / "scripts/audit_bias.py").read_bytes()).hexdigest()
            or summary.get("offline_adapter_sha256") != hashlib.sha256((root / "scripts/offline_backtest.py").read_bytes()).hexdigest()
            or datetime.fromisoformat(summary["first"]) != datetime(2023, 12, 1, tzinfo=timezone.utc)
            or datetime.fromisoformat(summary["last"]) != datetime(2024, 12, 31, 23, tzinfo=timezone.utc)):
        raise ValueError("Auditoria temporal não corresponde à baseline/janela congelada")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-bias", action="store_true", help="Reutilizar somente artefato de mesma baseline, verificado")
    args = parser.parse_args()
    lock = verify_baseline()
    require_locked_holdout()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "user_data/research/risk-audit" / run_id
    run_dir.mkdir(parents=True)
    evidence = ROOT / "docs/audit/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    steps = []

    def execute(name, command, timeout):
        log = run_dir / (name + ".log")
        print(f"[{name}] início", flush=True)
        with log.open("w") as output:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                output.write(f"\n{exc}\n")
                code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
                if "--name" in command:
                    name_created = command[command.index("--name") + 1]
                    subprocess.run(["docker", "rm", "--force", name_created], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30)
        step = {"name": name, "command": command, "code": code,
                "log": str(log.relative_to(ROOT)), "status": "passed" if code == 0 else "failed"}
        steps.append(step)
        shutil.copyfile(log, evidence / (name + ".log"))
        print(f"[{name}] {step['status']}; código {code}", flush=True)
        return code == 0

    ci_path = run_dir / "ci.json"
    ci_ok = execute("ci", [sys.executable, "scripts/check_ci.py", "--output", str(ci_path)], 180)
    ci = json.loads(ci_path.read_text()) if ci_path.exists() else {
        "status": "unconfirmed", "head_sha": "unknown", "url": "https://github.com/Ruan-dev-back/TradeBot-AI/actions"}
    (evidence / "ci.json").write_text(json.dumps(ci, indent=2) + "\n")
    prefix = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.audit.yml"]
    tests_ok = execute("tests", prefix + ["run", "--rm", "--name", f"tradebot-audit-{run_id.lower()}-tests", "freqtrade", "test"], 180)
    tests_output = (run_dir / "tests.log").read_text()
    match = re.search(r"Ran (\d+) tests", tests_output)
    tests_ok = tests_ok and match is not None and "\nOK\n" in tests_output
    if not tests_ok:
        raise RuntimeError("Suíte obrigatória não passou; auditoria não apresentada como concluída")
    steps[-1]["test_count"] = int(match[1])
    bias_path = ROOT / "user_data/research/audit-bias/latest.json"
    if not args.reuse_bias:
        if not execute("bias", prefix + ["run", "--rm", "--name", f"tradebot-audit-{run_id.lower()}-bias", "freqtrade", "audit-bias"], 600):
            raise RuntimeError("Auditoria temporal falhou; consultar saída completa")
    bias = json.loads(bias_path.read_text())
    validate_bias(bias, lock)
    if args.reuse_bias:
        steps.append({"name": "bias", "status": "reused_verified", "source": str(bias_path.relative_to(ROOT))})
    shutil.copyfile(bias_path, evidence / "bias.json")
    analysis = build_analysis()
    analysis["run_id"] = run_id
    analysis["tests_passed"] = int(match[1])
    analysis["ci"] = ci
    analysis["bias"] = bias
    report = render_report(analysis, bias, ci)
    report += f"\nSuíte final: **{match[1]} testes passando**, incluindo os 41 originais. Execução `{run_id}`.\n"
    verify_baseline()
    require_locked_holdout()
    (ROOT / "docs/risk-report.md").write_text(report)
    for target in (run_dir / "risk-analysis.json", evidence / "risk-analysis.json"):
        target.write_text(json.dumps(analysis, indent=2, allow_nan=False) + "\n")
    for target in (run_dir / "commands.json", evidence / "commands.json"):
        target.write_text(json.dumps(steps, indent=2) + "\n")
    (run_dir / "risk-report.md").write_text(report)
    print("Relatório: docs/risk-report.md; baseline preservada; nenhum preço do holdout consultado.", flush=True)
    return 0 if ci_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
