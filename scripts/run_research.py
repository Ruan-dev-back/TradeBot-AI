"""Executa pesquisa no Compose e gera relatório de evidências, inclusive falhas."""

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

from safety import PERIODS, validate_config
from audit_guard import require_legacy_research_allowed

ROOT = Path(__file__).resolve().parents[1]


def read_backtest(directory, expected_period=None):
    archives = sorted(directory.glob("*.zip"))
    if len(archives) != 1:
        raise ValueError(f"Esperado um export novo, encontrados {len(archives)} em {directory}")
    with zipfile.ZipFile(archives[0]) as archive:
        stats = []
        for name in archive.namelist():
            if name.endswith(".json") and not name.endswith((".meta.json", "_config.json")):
                value = json.loads(archive.read(name))
                if "strategy" in value and "SmaRsiStrategy" in value["strategy"]:
                    stats.append(value["strategy"]["SmaRsiStrategy"])
    if len(stats) != 1:
        raise ValueError("Export não contém um resultado inequívoco da estratégia")
    stat = stats[0]
    required = {"trades", "total_trades", "profit_total_abs", "profit_total", "final_balance",
                "max_drawdown_account", "max_drawdown_abs", "market_change",
                "backtest_start", "backtest_end"}
    if not required.issubset(stat):
        raise ValueError(f"Resumo incompleto: {sorted(required - set(stat))}")
    for key in required - {"trades", "backtest_start", "backtest_end"}:
        if not isinstance(stat[key], (float, int)) or not math.isfinite(stat[key]):
            raise ValueError(f"Métrica inválida: {key}")
    trades = stat["trades"]
    if stat["total_trades"] != len(trades):
        raise ValueError("Contagem de operações inconsistente")
    if abs(sum(t["profit_abs"] for t in trades) - stat["profit_total_abs"]) > 0.01:
        raise ValueError("Lucro agregado inconsistente com operações exportadas")
    if expected_period is not None:
        start, end = PERIODS[expected_period]
        actual = (stat["backtest_start"], stat["backtest_end"])
        expected = tuple(datetime.strptime(date, "%Y%m%d").strftime("%Y-%m-%d %H:%M:%S") for date in (start, end))
        if actual != expected or stat.get("pairlist") != ["BTC/USDT"] or stat.get("timeframe") != "1h":
            raise ValueError("Export não corresponde ao período/par/timeframe solicitado")
        if stat.get("stoploss") != -0.05 or stat.get("starting_balance") != 1000:
            raise ValueError("Stop-loss ou carteira diverge da baseline")
        for trade in trades:
            if (trade.get("pair") != "BTC/USDT" or trade.get("is_short") is not False
                    or trade.get("leverage") != 1 or trade.get("is_open") is not False
                    or trade.get("fee_open") != 0.001 or trade.get("fee_close") != 0.001):
                raise ValueError("Trade viola o protocolo spot/long/taxas")
        trade_metrics(stat)  # Recusa trades fora do intervalo ou posições sobrepostas.
    fees = 0.0
    for trade in trades:
        orders = trade.get("orders")
        if orders:
            fees += sum(order["amount"] * order["safe_price"]
                        * trade["fee_open" if order["ft_is_entry"] else "fee_close"] for order in orders)
        else:
            fees += trade["amount"] * (trade["open_rate"] * trade["fee_open"] + trade["close_rate"] * trade["fee_close"])
    if not math.isfinite(fees) or fees < 0:
        raise ValueError("Total de taxas inválido")
    return stat, fees, archives[0]


def trade_metrics(stat):
    def timestamp(value, summary=False):
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            if not summary:
                raise ValueError("Datas de trades devem conter timezone UTC")
            date = date.replace(tzinfo=timezone.utc)  # Contrato dos resumos Freqtrade.
        if date.utcoffset().total_seconds() != 0:
            raise ValueError("Datas de trades devem ser UTC")
        return date.timestamp()
    start = timestamp(stat["backtest_start"], summary=True)
    end = timestamp(stat["backtest_end"], summary=True)
    if end <= start:
        raise ValueError("Período efetivo inválido")
    profits, intervals = [], []
    for trade in stat["trades"]:
        opened, closed = timestamp(trade["open_date"]), timestamp(trade["close_date"])
        if not (start <= opened < end and opened <= closed <= end):
            raise ValueError("Trade fora do período efetivo")
        intervals.append((opened, closed))
        profit = trade["profit_abs"]
        if not math.isfinite(profit):
            raise ValueError("Lucro de trade não finito")
        profits.append(profit)
    intervals.sort()
    if any(right[0] < left[1] for left, right in zip(intervals, intervals[1:])):
        raise ValueError("Posições sobrepostas apesar de max_open_trades=1")
    gains = sum(p for p in profits if p > 0)
    losses = -sum(p for p in profits if p < 0)
    factor = gains / losses if losses else (math.inf if gains else None)
    wins = sum(p > 0 for p in profits)
    return {"profit_factor": factor, "wins": wins,
            "winrate": wins / len(profits) if profits else None,
            "exposure": sum(closed - opened for opened, closed in intervals) / (end - start)}


def render_report(run_id, steps, results, manifest, hashes):
    rows = [
        "# Relatório de pesquisa — TradeBot AI", "",
        f"Execução `{run_id}`. Tempos e períodos deste relatório em UTC.", "",
        "Dados públicos Binance spot, BTC/USDT, 1h; carteira fictícia independente de",
        "1000 USDT em cada período. Estratégia SMA20/50 + RSI14, stop-loss de 5%.",
        "Taxa assumida de 0,1% por lado; não é consulta à tarifa de uma conta real.", "",
        "## Evidências de execução", "",
        "| Etapa | Resultado | Código | Log |", "|---|---|---:|---|",
    ]
    for step in steps:
        log = f"`{step['log']}`" if step.get("log") else "—"
        rows.append(f"| {step['name']} | {step['status']} | {step.get('code', '—')} | {log} |")
    for step in steps:
        if step.get("test_count") is not None:
            rows += ["", f"Suíte desta execução: **{step['test_count']} testes**, resultado {step['status']}."]
    rows += ["", "## Resultados financeiros", "",
             "| Métrica | Desenvolvimento | Validação |", "|---|---:|---:|"]
    metric_names = [
        "Período solicitado (fim exclusivo)", "Situação", "Período efetivo Freqtrade",
        "Operações fechadas (inclui encerramento final)", "Taxa assumida por lado",
        "Lucro líquido (USDT)", "Retorno líquido na carteira", "Saldo final (USDT)",
        "Taxas reconstruídas dos trades (USDT)", "Drawdown máximo relativo da conta",
        "Drawdown máximo absoluto (USDT)", "Market change Freqtrade (close/close, bruto)",
        "Buy-and-hold líquido da carteira (99% investido)", "Buy-and-hold lucro líquido (USDT)",
        "Candles ativos validados",
        "Profit factor líquido", "Taxa de acerto", "Exposição temporal",
        "Drawdown máximo da carteira marcada a mercado",
    ]
    values = {name: dict.fromkeys(metric_names, "N/D") for name in PERIODS}
    for name, (start, end) in PERIODS.items():
        v = values[name]
        v["Período solicitado (fim exclusivo)"] = f"{start}–{end}"
        v["Taxa assumida por lado"] = "0,1%"
        result = results.get(name)
        if not result:
            v["Situação"] = "Não concluído; sem métricas"
            continue
        stat, fees, archive = result
        metrics = trade_metrics(stat)
        factor = metrics["profit_factor"]
        v.update({
            "Situação": "Backtest concluído",
            "Período efetivo Freqtrade": f"{stat['backtest_start']} – {stat['backtest_end']}",
            "Operações fechadas (inclui encerramento final)": str(stat["total_trades"]),
            "Lucro líquido (USDT)": f"{stat['profit_total_abs']:.4f}",
            "Retorno líquido na carteira": f"{100 * stat['profit_total']:.4f}%",
            "Saldo final (USDT)": f"{stat['final_balance']:.4f}",
            "Taxas reconstruídas dos trades (USDT)": f"{fees:.4f}",
            "Drawdown máximo relativo da conta": f"{100 * stat['max_drawdown_account']:.4f}%",
            "Drawdown máximo absoluto (USDT)": f"{stat['max_drawdown_abs']:.4f}",
            "Market change Freqtrade (close/close, bruto)": f"{100 * stat['market_change']:.4f}%",
            "Profit factor líquido": "N/D" if factor is None else ("∞ (sem perdas)" if math.isinf(factor) else f"{factor:.4f}"),
            "Taxa de acerto": "N/D" if metrics["winrate"] is None else f"{100 * metrics['winrate']:.4f}%",
            "Exposição temporal": f"{100 * metrics['exposure']:.4f}%",
        })
        wallet_dd = stat.get("wallet_stats", {}).get("max_drawdown_account")
        if wallet_dd is not None:
            v["Drawdown máximo da carteira marcada a mercado"] = f"{100 * wallet_dd:.4f}%"
        if manifest:
            candles = manifest["periods"][name]
            ratio = candles["last_close"] / candles["first_open"]
            net = 0.99 * (ratio * (1 - 0.001) / (1 + 0.001) - 1)
            v["Buy-and-hold líquido da carteira (99% investido)"] = f"{100 * net:.4f}%"
            v["Buy-and-hold lucro líquido (USDT)"] = f"{1000 * net:.4f}"
            v["Candles ativos validados"] = str(candles["candles"])
    keys = list(dict.fromkeys(key for v in values.values() for key in v))
    for key in keys:
        rows.append(f"| {key} | {values['development'].get(key, 'N/D')} | {values['validation'].get(key, 'N/D')} |")
    rows += ["", "## Integridade e método", ""]
    for name, digest in hashes.items():
        rows.append(f"- SHA-256 `{name}`: `{digest}`.")
    if manifest:
        rows += [f"- OHLCV: `{manifest['file']}`; SHA-256 `{manifest['sha256']}`.",
                 f"- Cobertura total: {manifest['first']} a {manifest['last']}; {manifest['candles']} candles."]
        rows += [f"- Origem única: {manifest['source']}; {manifest['exchange']} {manifest['pair']} {manifest['timeframe']}."]
    else:
        rows += ["- Cobertura OHLCV não validada nesta execução; não há métricas financeiras verificadas."]
    rows += [
        "- Desenvolvimento: 2024; validação: primeiro semestre de 2025, sem sobreposição.",
        "- 200 candles anteriores são apenas warm-up; cada backtest reinicia a carteira e posições.",
        "- Parâmetros fixados antes dos testes; sem hyperopt ou seleção usando a validação.",
        "- Taxas reconstruídas dos fills exportados: amount × safe_price × fee de cada lado; já incluídas no lucro líquido.",
        "- Profit factor = lucros líquidos positivos / módulo dos negativos; taxa de acerto = trades positivos / total.",
        "- Exposição temporal = duração total das posições / duração UTC do período; uma posição no máximo.",
        "- Buy-and-hold: compra no primeiro open e venda no último close do período, taxa de",
        "  0,1% nos dois lados, 99% do capital incluindo custo de compra e 1% em caixa.",
        "- Market change do Freqtrade usa primeiro/último close, sem taxas, e difere desse benchmark.",
        "- Drawdown é o indicador da conta exportado pelo Freqtrade; não equivale necessariamente",
        "  ao drawdown intrabar marcado a mercado. Custos de spread, slippage e impacto não modelados.",
        "- Os testes causais por prefixos são evidência básica, não substituem a análise completa de lookahead.",
        "- Backtest não estabelece lucratividade futura. Nenhuma ordem real foi enviada.",
        "", "## Comandos desta execução", "",
    ]
    if any("--offline" in step.get("command", "") for step in steps):
        rows[rows.index("## Comandos desta execução"):rows.index("## Comandos desta execução")] = [
            "- Modo offline: snapshot real dos filtros atuais Binance/CCXT; filtros históricos não disponíveis.",
            "- Motor nativo Freqtrade em contêiner com network_mode=none e taxa explícita; OHLCV real, sem acesso à exchange.", "",
        ]
    for step in steps:
        if step.get("command"):
            rows += [f"### {step['name']}", "", "```sh", step["command"], "```", ""]
        if step.get("error"):
            rows += ["Erro observado:", "", "```text", step["error"], "```", ""]
    rows += ["## Próximo passo", "",
             ("Revisar o comportamento e os riscos no período de desenvolvimento. A validação já foi "
              "observada: qualquer ajuste posterior exige reservar um novo período não usado."
              if len(results) == 2 else
              "Resolver o bloqueio descrito acima e repetir `python3 scripts/run_research.py`, "
              "mantendo os mesmos parâmetros. Não trocar de mercado nem inventar resultados."), ""]
    return "\n".join(line.rstrip() for line in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["auto", "api", "archive"], default="auto")
    args = parser.parse_args()
    try:
        require_legacy_research_allowed([])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "user_data/research" / run_id
    run_dir.mkdir(parents=True)
    steps, results = [], {}
    manifest = None
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in ("user_data/config.json", "user_data/strategies/SmaRsiStrategy.py", "docker-compose.yml",
                           "scripts/download_archive.py", "scripts/offline_backtest.py", "docker-compose.offline.yml")}
    compose_prefix = ["docker", "compose"]
    if os.environ.get("HTTPS_PROXY") and Path("/etc/ssl/certs/ca-certificates.crt").is_file():
        compose_prefix += ["-f", "docker-compose.yml", "-f", "docker-compose.cloud.yml"]
        hashes["docker-compose.cloud.yml"] = hashlib.sha256((ROOT / "docker-compose.cloud.yml").read_bytes()).hexdigest()

    def run(name, command, timeout=180, required_text=None):
        log = run_dir / f"{name}.log"
        print(f"[{name}] {shlex.join(command)}", flush=True)
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, timeout=timeout)
            output, code = process.stdout, process.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or b""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            output += f"\nTIMEOUT após {timeout}s\n"
            code = 124
            if "--name" in command:
                container = command[command.index("--name") + 1]
                subprocess.run(["docker", "rm", "--force", container],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except OSError as exc:
            output, code = str(exc), 127
        log.write_text(output)
        # Alguns comandos de listagem podem retornar zero apesar de erro de configuração.
        semantic_error = bool(re.search(r"Configuration error:| - ERROR - | - CRITICAL - ", output))
        ok = code == 0 and not semantic_error and (required_text is None or required_text in output)
        step = {"name": name, "command": shlex.join(command), "code": code,
                "status": "PASSOU" if ok else "FALHOU", "log": str(log.relative_to(ROOT))}
        if not ok:
            errors = [line for line in output.splitlines()
                      if re.search(r"ClientHttpProxyError:|ClientConnectorDNSError:|SSLCertVerificationError:|Configuration error:", line)]
            excerpt = list(dict.fromkeys(errors)) + output.splitlines()[-24:]
            step["error"] = "\n".join(excerpt) or "Saída esperada ausente"
        if name == "tests":
            summary = re.search(r"Ran (\d+) tests[^\n]*", output)
            if summary:
                step["test_count"] = int(summary.group(1))
        steps.append(step)
        print(f"[{name}] {step['status']} (código {code}); {log.relative_to(ROOT)}", flush=True)
        return ok

    def compose(name, args, offline=False, **kwargs):
        prefix = compose_prefix + (["-f", "docker-compose.offline.yml"] if offline else [])
        return run(name, prefix + ["run", "--rm", "--name",
                         f"tradebot-ai-{run_id.lower()}-{name}", "freqtrade"] + args, **kwargs)

    try:
        validate_config(json.loads((ROOT / "user_data/config.json").read_text()), {})
        docker_ok = run("docker-info", ["docker", "info", "--format", "{{.ServerVersion}}"])
        compose_ok = run("compose-config", compose_prefix + ["config", "--quiet"])
        if docker_ok and compose_ok:
            version_ok = compose("version", ["--version"], required_text="Freqtrade Version:")
            tests_ok = compose("tests", ["test"], offline=True, required_text="\nOK\n")
            strategies_ok = compose("strategies", ["list-strategies"], required_text="SmaRsiStrategy")
            selected_source = args.source
            downloaded = False
            if args.source != "archive":
                downloaded = compose("download", ["download-data"], timeout=900)
                if not downloaded and args.source == "auto":
                    steps[-1]["required"] = False  # Falha real preservada; fallback verificado abaixo.
            if args.source == "archive" or (not downloaded and args.source == "auto"):
                downloaded = compose("archive-download", ["download-archive"], timeout=900)
                selected_source = "archive"
            compose("list-data", ["list-data"])
            manifest_path = ROOT / "user_data/research/data_manifest.json"
            manifest_path.unlink(missing_ok=True)
            data_ok = compose("validate-data", ["validate-data"])
            if data_ok:
                manifest = json.loads(manifest_path.read_text())
                shutil.copy2(manifest_path, run_dir / "data_manifest.json")
            if version_ok and tests_ok and strategies_ok and downloaded and data_ok:
                for name in PERIODS:
                    directory = ROOT / "user_data/backtest_results" / run_id / name
                    command = ["backtesting", "--period", name, "--output-dir",
                               f"/freqtrade/user_data/backtest_results/{run_id}/{name}"]
                    if selected_source == "archive":
                        command.append("--offline")
                    if compose(name, command, offline=selected_source == "archive", timeout=600):
                        try:
                            results[name] = read_backtest(directory, expected_period=name)
                        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
                            steps.append({"name": f"export-{name}", "status": "FALHOU", "error": str(exc)})
            else:
                steps.append({"name": "backtests", "status": "NÃO EXECUTADOS",
                              "error": "Pré-requisito obrigatório falhou; métricas não calculadas."})
        else:
            steps.append({"name": "Docker workflow", "status": "NÃO EXECUTADO",
                          "error": "Docker/Compose indisponível. Nada foi instalado automaticamente."})
    except (ValueError, OSError, KeyError) as exc:
        steps.append({"name": "pesquisa", "status": "FALHOU", "error": str(exc)})
    (run_dir / "commands.json").write_text(json.dumps(steps, indent=2) + "\n")
    report = render_report(run_id, steps, results, manifest, hashes)
    (run_dir / "results.md").write_text(report)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/results.md").write_text(report)
    evidence = ROOT / "docs/evidence"
    evidence.mkdir(exist_ok=True)
    # Exports antigos não podem parecer evidência da execução atual se esta falhar.
    for name in ("backtest-development.json", "backtest-validation.json", "data_manifest.json", "market_snapshot.json"):
        (evidence / name).unlink(missing_ok=True)
    (evidence / "commands.json").write_text(json.dumps(steps, indent=2) + "\n")
    if manifest:
        (evidence / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        snapshot_path = ROOT / "user_data/data/binance/market_snapshot.json"
        if snapshot_path.exists():
            shutil.copy2(snapshot_path, evidence / "market_snapshot.json")
    for name, (stat, fees, archive) in results.items():
        derived = trade_metrics(stat)
        infinite_factor = derived["profit_factor"] is not None and math.isinf(derived["profit_factor"])
        if infinite_factor:
            derived["profit_factor"] = None
        derived["profit_factor_no_losses"] = infinite_factor
        (evidence / f"backtest-{name}.json").write_text(json.dumps({
            "run_id": run_id, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "reconstructed_fees": fees, "derived_metrics": derived, "freqtrade_summary": stat,
        }, indent=2, allow_nan=False) + "\n")
    for step in steps:
        if step.get("log"):
            shutil.copy2(ROOT / step["log"], evidence / (step["name"] + ".log"))
    print("Relatório: docs/results.md", flush=True)
    return 0 if len(results) == 2 and all(s["status"] == "PASSOU" for s in steps if s.get("required", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
