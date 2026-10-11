"""Confere CI público no GitHub HTML quando a API está bloqueada pelo proxy."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://github.com/Ruan-dev-back/TradeBot-AI"


def parse_run_page(page, expected_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Commit esperado deve ser SHA completo")
    if f"/Ruan-dev-back/TradeBot-AI/commit/{expected_sha}" not in page:
        raise ValueError("Execução de CI não corresponde ao commit esperado")
    match = re.search(r'<span class="h4 color-fg-default">(Success|Failure|Cancelled|In progress)</span>', page)
    if not match:
        raise ValueError("Status de CI não identificável; badge sozinho não prova o commit")
    return {"Success": "success", "Failure": "failure", "Cancelled": "cancelled",
            "In progress": "in_progress"}[match[1]]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "TradeBot-AI-research-audit/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def check():
    remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/feat/mvp-foundation"],
                                     cwd=ROOT, text=True).split()
    if len(remote) != 2:
        raise ValueError("Branch remota não identificada")
    sha = remote[0]
    page = fetch(BASE + "/actions?query=branch%3Afeat%2Fmvp-foundation")
    run_paths = list(dict.fromkeys(re.findall(r'/Ruan-dev-back/TradeBot-AI/actions/runs/\d+', page)))
    for path in run_paths[:10]:
        run_page = fetch("https://github.com" + path)
        if f"/Ruan-dev-back/TradeBot-AI/commit/{sha}" not in run_page:
            continue
        status = parse_run_page(run_page, sha)
        return {"checked_at": datetime.now(timezone.utc).isoformat(), "head_sha": sha,
                "current_local_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "status": status, "url": "https://github.com" + path,
                "evidence_method": "GitHub public run HTML: exact commit URL and explicit status",
                "run_page_sha256": hashlib.sha256(run_page.encode()).hexdigest(),
                "commit_link_evidence": f"/Ruan-dev-back/TradeBot-AI/commit/{sha}",
                "status_evidence": f'<span class="h4 color-fg-default">{status.capitalize()}</span>',
                "api_limit": "gh/API request blocked with proxy CONNECT 403; public HTML verified instead"}
    raise ValueError("Não encontrada execução inequívoca para o commit remoto; CI não confirmado")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
