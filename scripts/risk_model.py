"""Diagnóstico dos exports reais e cenários aritméticos, nunca um novo backtest."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_guard import ROOT, HOLDOUT_START, require_locked_holdout, verify_baseline
from run_research import trade_metrics

FRACTIONS = (0.05, 0.10, 0.20)


@dataclass(frozen=True)
class Costs:
    name: str
    spread_bps: float = 0  # Spread completo; metade em cada execução.
    slippage_bps_per_side: float = 0
    extra_fee_bps_per_side: float = 0
    base_fee_bps_per_side: float = 10

    def __post_init__(self):
        for value in (self.spread_bps, self.slippage_bps_per_side,
                      self.extra_fee_bps_per_side, self.base_fee_bps_per_side):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Custos devem ser finitos e não negativos")
        if self.execution >= 1 or self.fee >= 1:
            raise ValueError("Custo por lado deve ser menor que 100%")

    @property
    def execution(self):
        return (self.spread_bps / 2 + self.slippage_bps_per_side) / 10000

    @property
    def fee(self):
        return (self.base_fee_bps_per_side + self.extra_fee_bps_per_side) / 10000


COST_SCENARIOS = (
    Costs("reference_fee_only"),
    Costs("low", spread_bps=4, slippage_bps_per_side=2),
    Costs("central", spread_bps=10, slippage_bps_per_side=10, extra_fee_bps_per_side=5),
    Costs("adverse", spread_bps=20, slippage_bps_per_side=20, extra_fee_bps_per_side=10),
)


def quantile(values, probability):
    if not values or not 0 <= probability <= 1:
        raise ValueError("Quantil exige amostra e probabilidade entre zero e um")
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability  # Interpolação linear, tipo 7.
    low, high = math.floor(location), math.ceil(location)
    return ordered[low] + (ordered[high] - ordered[low]) * (location - low)


def distribution(values):
    return {"count": len(values), "mean": statistics.mean(values),
            "std_sample": statistics.stdev(values) if len(values) > 1 else None,
            **{name: quantile(values, probability) for name, probability in
               (("min", 0), ("p10", .10), ("p25", .25), ("median", .50),
                ("p75", .75), ("p90", .90), ("max", 1))}}


def notionals(trade):
    orders = trade.get("orders", [])
    entries = [o for o in orders if o["ft_is_entry"]]
    exits = [o for o in orders if not o["ft_is_entry"]]
    if len(entries) != 1 or len(exits) != 1:
        raise ValueError("Modelo exige um fill de entrada e um de saída, sem DCA/parciais")
    if not math.isclose(entries[0]["amount"], exits[0]["amount"], rel_tol=1e-12):
        raise ValueError("Quantidades de entrada e saída divergentes")
    entry = entries[0]["amount"] * entries[0]["safe_price"]
    exit_ = exits[0]["amount"] * exits[0]["safe_price"]
    if not all(math.isfinite(value) and value > 0 for value in (entry, exit_)):
        raise ValueError("Notional inválido")
    return entry, exit_


def net_position_return(price_ratio, costs):
    if not math.isfinite(price_ratio) or price_ratio <= 0:
        raise ValueError("Razão de preços deve ser positiva e finita")
    execution_ratio = price_ratio * (1 - costs.execution) / (1 + costs.execution)
    return execution_ratio * (1 - costs.fee) / (1 + costs.fee) - 1


def replay(trades, fraction, costs, initial=1000):
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("Exposição deve estar entre zero e 100%")
    if not math.isfinite(initial) or initial <= 0:
        raise ValueError("Capital deve ser positivo")
    equity = peak = initial
    max_dd = 0.0
    path = [equity]
    pnl = []
    for trade in sorted(trades, key=lambda t: t["open_timestamp"]):
        entry, exit_ = notionals(trade)
        ratio = net_position_return(exit_ / entry, costs)
        profit = equity * fraction * ratio
        equity += profit
        pnl.append(profit)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        path.append(equity)
    return {"fraction_cash_including_entry_fee": fraction, "costs": asdict(costs),
            "initial": initial, "final_equity": equity, "net_profit": equity - initial,
            "net_return": equity / initial - 1, "max_drawdown_closed_trades": max_dd,
            "trades_retained": len(trades), "wins": sum(value > 0 for value in pnl),
            "equity_after_closes": path,
            "hypothetical_not_independent_validation": True}


def fixed_quantity_costs(trades, costs):
    total = 0.0
    for trade in trades:
        entry, exit_ = notionals(trade)
        paid = entry * (1 + costs.execution) * (1 + costs.fee)
        received = exit_ * (1 - costs.execution) * (1 - costs.fee)
        total += received - paid
    return total


def summarize(stat):
    trades = stat["trades"]
    metrics = trade_metrics(stat)
    groups = defaultdict(lambda: {"trades": 0, "wins": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0})
    total_fees = total_gross = 0.0
    flipped_by_fees = 0
    histogram = Counter({name: 0 for name in ("<= -5%", "(-5%, -2%]", "(-2%, 0%]", "(0%, 1%]", "(1%, 2%]", "> 2%")})
    longest_loss_streak = streak = 0
    ratios = []
    for trade in sorted(trades, key=lambda t: t["open_timestamp"]):
        entry, exit_ = notionals(trade)
        gross = exit_ - entry
        fees = entry * trade["fee_open"] + exit_ * trade["fee_close"]
        net = gross - fees
        if not math.isclose(net, trade["profit_abs"], abs_tol=1e-6):
            raise ValueError("Reconstrução de lucro líquido diverge do export")
        ratio = net / (entry * (1 + trade["fee_open"]))
        if not math.isclose(ratio, trade["profit_ratio"], abs_tol=1e-9):
            raise ValueError("Retorno por posição diverge do export")
        ratios.append(100 * ratio)
        flipped_by_fees += int(gross > 0 and net <= 0)
        total_gross += gross
        total_fees += fees
        group = groups[trade["exit_reason"]]
        for key, value in (("trades", 1), ("wins", int(net > 0)), ("gross_pnl", gross), ("fees", fees), ("net_pnl", net)):
            group[key] += value
        streak = streak + 1 if net < 0 else 0
        longest_loss_streak = max(longest_loss_streak, streak)
        value = 100 * ratio
        bucket = next((name for edge, name in ((-5, "<= -5%"), (-2, "(-5%, -2%]"),
                    (0, "(-2%, 0%]"), (1, "(0%, 1%]"), (2, "(1%, 2%]")) if value <= edge), "> 2%")
        histogram[bucket] += 1
    net_total = sum(t["profit_abs"] for t in trades)
    if not math.isclose(net_total, stat["profit_total_abs"], abs_tol=1e-6):
        raise ValueError("Soma dos trades não confere com o resumo")
    wins = [t["profit_ratio"] for t in trades if t["profit_abs"] > 0]
    losses = [-t["profit_ratio"] for t in trades if t["profit_abs"] < 0]
    avg_win = statistics.mean(wins) if wins else None
    avg_loss = statistics.mean(losses) if losses else None
    return {"trades": len(trades), "gross_pnl_fixed_fills": total_gross,
            "reconstructed_fees": total_fees, "net_pnl": net_total,
            "positive_gross_trades_made_nonpositive_by_fees": flipped_by_fees,
            "net_position_return_percent": distribution(ratios),
            "net_pnl_usdt": distribution([t["profit_abs"] for t in trades]),
            "holding_hours": distribution([t["trade_duration"] / 60 for t in trades]),
            "histogram_position_return_percent": dict(histogram), "exit_reasons": dict(groups),
            "mean_winner_position_return": avg_win, "mean_loser_position_loss": avg_loss,
            "breakeven_winrate_constant_weight": avg_loss / (avg_win + avg_loss) if avg_win and avg_loss else None,
            "max_consecutive_losses": longest_loss_streak, **metrics,
            "native_drawdown_closed": stat["max_drawdown_account"],
            "native_drawdown_marked": stat["wallet_stats"]["max_drawdown_account"],
            "net_wallet_return": stat["profit_total"],
            "fees_as_fraction_of_net_loss": total_fees / -net_total if net_total < 0 else None}


def build_analysis(root=ROOT):
    lock = verify_baseline(root)
    require_locked_holdout(root)
    result = {"baseline_commit": lock["baseline_commit"], "baseline_file_hashes": lock["files"],
              "source": "Published native Freqtrade Binance BTC/USDT spot 1h exports; no OHLCV acquisition",
              "holdout_prices_inspected": False, "periods": {}, "costs": [asdict(c) for c in COST_SCENARIOS]}
    for period, expected_count in lock["trades"].items():
        evidence = json.loads((root / f"docs/evidence/backtest-{period}.json").read_text())
        stat = evidence["freqtrade_summary"]
        if len(stat["trades"]) != expected_count or stat["total_trades"] != expected_count:
            raise ValueError("Quantidade de trades diverge da baseline congelada")
        if stat["starting_balance"] != 1000 or stat["stoploss"] != -0.05:
            raise ValueError("Carteira/stop-loss divergem da baseline")
        for trade in stat["trades"]:
            if (trade["pair"] != "BTC/USDT" or trade["is_short"] or trade["is_open"]
                    or trade["leverage"] != 1 or trade["fee_open"] != .001 or trade["fee_close"] != .001
                    or datetime.fromisoformat(trade["open_date"]) >= HOLDOUT_START):
                raise ValueError("Trade incompatível com o protocolo ou dentro do holdout")
        observed = summarize(stat)
        scenarios = [replay(stat["trades"], fraction, costs) for fraction in FRACTIONS for costs in COST_SCENARIOS]
        fixed = [{"costs": asdict(costs), "net_pnl_fixed_quantities": fixed_quantity_costs(stat["trades"], costs)}
                 for costs in COST_SCENARIOS]
        for scenario in scenarios:
            scenario["time_exposure_unchanged"] = observed["exposure"]
            scenario["average_capital_time_fraction"] = scenario["fraction_cash_including_entry_fee"] * observed["exposure"]
        result["periods"][period] = {"observed": observed, "hypothetical_exposure_replay": scenarios,
                                     "fixed_quantity_cost_sensitivity": fixed}
    central = next(c for c in COST_SCENARIOS if c.name == "central")
    loss_at_stop = -net_position_return(0.95, central)
    result["proposed_risk_policy"] = {"status": "proposal_only_not_implemented", "risk_budget": .005,
            "exposure_cap": .10, "modeled_loss_at_5_percent_stop_central_costs": loss_at_stop,
            "maximum_cash_fraction": min(.10, .005 / loss_at_stop),
            "risk_with_10_percent_gap_at_this_fraction": min(.10, .005 / loss_at_stop) * -net_position_return(.90, central)}
    return result


def render_report(analysis, bias=None, ci=None):
    periods = analysis["periods"]
    rows = ["# Auditoria técnica de perdas e gestão de risco", "",
            "Baseline SMA20/50 + RSI14 publicada, stop-loss de 5%, Binance BTC/USDT spot 1h.",
            "Estratégia, configuração, relatório original e exports permanecem congelados.",
            "2024 é desenvolvimento; janeiro–junho/2025 já foi observado e não seleciona parâmetros.",
            "Holdout 2025-07-01–2026-07-01 UTC reservado, sem consulta de preços/resultados nesta auditoria.", "",
            "## Integridade, CI e análises temporais", "",
            f"Commit de origem: `{analysis['baseline_commit']}`. Hashes em `docs/audit/baseline-lock.json`."]
    if ci:
        rows += [f"CI remoto: **{ci['status']}**, commit `{ci['head_sha']}`, [execução]({ci['url']}).",
                 "Esse CI corresponde ao commit remoto inspecionado antes desta auditoria; não prova CI do novo commit local."]
    if bias:
        look = bias["lookahead"]
        roll = bias["rolling_recursive"]
        rows += [f"Lookahead nativo Freqtrade 2026.9: {look['total_signals']} trades/sinais avaliados; "
                 f"entradas enviesadas {look['biased_entry_signals']}, saídas {look['biased_exit_signals']}, "
                 f"indicadores {look['biased_indicators']}; has_bias={look['has_bias']}.",
                 f"Causalidade suplementar: {bias['prefix_check']['prefixes']} prefixos, diferenças "
                 f"{bias['prefix_check']['differences']}.",
                 "Recursive nativo compara a última linha para 50/100/200/400/800 candles de histórico.",
                 f"Complemento rolling com 200 candles: {roll['candles_checked']} horas, "
                 f"erro máximo RSI {roll['max_absolute_errors']['rsi']:.8f} pontos, "
                 f"mudanças de sinais {roll['signal_flips']}, critério RSI ≤ {roll['rsi_tolerance']} ponto.",
                 "O lookahead nativo força carteira 1 bilhão, stake 10000 e max_open_trades=-1 (um par),",
                 "sem alterar arquivos da baseline. Ignora force_exit; seus valores financeiros não são uma nova comparação.",
                 "Não detectar viés nessas verificações não prova ausência universal de vazamento.",
                 "O recursive nativo avalia apenas a última linha; o complemento verifica efeitos nos sinais em todo 2024."]
        rows += ["", "| Histórico (candles) | Diferença relativa RSI na última linha, nativo (%) |",
                 "|---|---:|"]
        native_rsi = bias["recursive"]["relative_differences_last_row"].get("rsi", {})
        for startup in bias["recursive"]["startup_candles"]:
            value = native_rsi.get(str(startup))
            rendered = "sem diferença registrada" if value is None else f"{100*value:.8f}"
            rows.append(f"| {startup} | {rendered} |")
        rows += ["", "O nativo arredonda diferenças relativas a 12 casas e interrompe comparação ao convergir;",
                 "zero/ausência nessa tabela não garante igualdade matemática em todas as horas. O rolling",
                 "de 200 mantém a diferença absoluta sem esse arredondamento e confere sinais em todo 2024."]
    rows += ["", "## Fatos observados: 110 operações simuladas com candles reais", "",
             "| Métrica | 2024 | Jan–jun/2025 observado |", "|---|---:|---:|"]
    for key, title, scale, digits in (
        ("trades", "Trades", 1, 0), ("gross_pnl_fixed_fills", "P&L antes de taxas, mesmos fills (USDT)", 1, 4),
        ("reconstructed_fees", "Taxas (USDT)", 1, 4), ("net_pnl", "P&L líquido (USDT)", 1, 4),
        ("net_wallet_return", "Retorno líquido (%)", 100, 4), ("profit_factor", "Profit factor líquido", 1, 4),
        ("winrate", "Taxa de acerto (%)", 100, 2), ("exposure", "Exposição temporal (%)", 100, 2),
        ("native_drawdown_closed", "Drawdown de trades fechados (%)", 100, 2),
        ("native_drawdown_marked", "Drawdown da carteira marcada pelo motor (%)", 100, 2),
        ("mean_winner_position_return", "Média de retorno dos vencedores (%)", 100, 4),
        ("mean_loser_position_loss", "Média de perda dos perdedores (%)", 100, 4),
        ("breakeven_winrate_constant_weight", "Acerto de equilíbrio, pesos constantes (%)", 100, 2),
        ("max_consecutive_losses", "Maior sequência de perdas", 1, 0),
        ("positive_gross_trades_made_nonpositive_by_fees", "Trades positivos brutos tornados não positivos pelas taxas", 1, 0)):
        values = [periods[p]["observed"][key] * scale for p in ("development", "validation")]
        rows.append(f"| {title} | {values[0]:.{digits}f} | {values[1]:.{digits}f} |")
    rows += ["", "As taxas são reconstruídas de amount × preço × taxa em ambos os fills.",
             "P&L bruto menos taxas = P&L líquido, nas quantidades publicadas. Mesmo sem taxas, ambos",
             "os conjuntos de fills apresentam prejuízo. Esse contrafactual não recalcula capital nem decisões.",
             "A taxa de equilíbrio usa médias dos retornos por posição, com pesos iguais; não é garantia",
             "para stakes variáveis. O modelo original usou aproximadamente 99% do saldo por posição.", "",
             "### Distribuição de retorno líquido por posição (%)", "",
             "| Quantil/estatística | 2024 | Jan–jun/2025 |", "|---|---:|---:|"]
    for key in ("min", "p10", "p25", "median", "p75", "p90", "max", "mean", "std_sample"):
        rows.append(f"| {key} | {periods['development']['observed']['net_position_return_percent'][key]:.4f} | "
                    f"{periods['validation']['observed']['net_position_return_percent'][key]:.4f} |")
    rows += ["", "Quantis usam interpolação linear tipo 7; desvio padrão amostral. Distribuições em USDT,",
             "duração em horas e histograma estão no JSON integral. Amostras de 69/41 trades são pequenas",
             "e temporalmente dependentes; não foram tratados como observações IID para alegar significância.", "",
             "### Motivos de saída", "", "| Período | Motivo exportado | Trades | Bruto USDT | Taxas USDT | Líquido USDT |",
             "|---|---|---:|---:|---:|---:|"]
    for period, label in (("development", "2024"), ("validation", "2025 H1")):
        for reason, group in periods[period]["observed"]["exit_reasons"].items():
            rows.append(f"| {label} | {reason} | {group['trades']} | {group['gross_pnl']:.4f} | {group['fees']:.4f} | {group['net_pnl']:.4f} |")
    rows += ["", "O tag `sma_down_or_rsi_75` agrega cruzamento contrário e RSI ≥ 75; o export sozinho",
             "não separa essas causas. `force_exit` é fechamento administrativo no fim de 2024.",
             "As perdas dos stops dominam o P&L agregado, mas eliminar stops a posteriori não reproduziria",
             "os mesmos trades nem demonstra melhoria: as posições poderiam sofrer perdas adicionais.", "",
             "## Cenários hipotéticos de capital", "",
             "Replays aritméticos dos mesmos trades, preços relativos e datas; não são novos backtests nem",
             "validação independente. Cada período reinicia com 1000 USDT. A fração inclui a taxa de compra;",
             "o restante fica em caixa sem rendimento. Não há arredondamento de lotes, mínimos, rejeições,",
             "impacto ou mudança no conjunto de operações. Essa convenção difere do stake original antes da taxa.", "",
             "`r = (P_exit/P_entry) × (1-c)/(1+c) × (1-fee)/(1+fee) - 1`",
             "`E_next = E × (1 + fração × r)`; `c = spread_completo/2 + slippage_por_lado`.", "",
             "| Período | Fração da carteira | Líquido USDT | Retorno % | Drawdown fechado % | Capital × tempo médio % |",
             "|---|---:|---:|---:|---:|---:|"]
    for period, label in (("development", "2024"), ("validation", "2025 H1 observado")):
        for scenario in periods[period]["hypothetical_exposure_replay"]:
            if scenario["costs"]["name"] == "reference_fee_only":
                rows.append(f"| {label} | {100*scenario['fraction_cash_including_entry_fee']:.0f}% | {scenario['net_profit']:.4f} | "
                            f"{100*scenario['net_return']:.4f} | {100*scenario['max_drawdown_closed_trades']:.4f} | "
                            f"{100*scenario['average_capital_time_fraction']:.4f} |")
    rows += ["", "Exposição temporal permanece igual: o replay mantém todas as datas. Exposição financeira",
             "diminui. Capital × tempo é um proxy (fração-alvo × tempo posicionado), não uma média exata",
             "da exposição marcada a mercado durante cada posição. Drawdown desses cenários usa apenas",
             "fechamentos; não reconstrói perdas intrabar.",
             "Menor stake limita a magnitude das perdas e também dos ganhos; não cria vantagem estatística.", "",
             "## Sensibilidade de execução e custos", "",
             "Hipóteses de estresse, não estimativas de spread ou slippage histórico a partir de OHLCV 1h.",
             "Spread é completo e aplicado pela metade em cada lado; slippage e taxa extra são por lado.",
             "A taxa base de 10 bps por lado já está incluída; não é cobrada duas vezes.", "",
             "| Cenário | Spread completo bps | Slippage/lado bps | Taxa extra/lado bps |",
             "|---|---:|---:|---:|"]
    for costs in COST_SCENARIOS:
        rows.append(f"| {costs.name} | {costs.spread_bps:g} | {costs.slippage_bps_per_side:g} | {costs.extra_fee_bps_per_side:g} |")
    rows += ["", "Decomposição estática nas quantidades originais; não é carteira reexecutada:", "",
             "| Cenário | P&L líquido 2024 USDT | P&L líquido 2025 H1 USDT |", "|---|---:|---:|"]
    for index, costs in enumerate(COST_SCENARIOS):
        a = periods["development"]["fixed_quantity_cost_sensitivity"][index]["net_pnl_fixed_quantities"]
        b = periods["validation"]["fixed_quantity_cost_sensitivity"][index]["net_pnl_fixed_quantities"]
        rows.append(f"| {costs.name} | {a:.4f} | {b:.4f} |")
    rows += ["", "Replays com frações menores e execução adversa, todos igualmente hipotéticos:", "",
             "| Período | Exposição | Cenário | Retorno % | Drawdown fechado % |", "|---|---:|---|---:|---:|"]
    for period, label in (("development", "2024"), ("validation", "2025 H1 observado")):
        for scenario in periods[period]["hypothetical_exposure_replay"]:
            if scenario["costs"]["name"] in ("central", "adverse"):
                rows.append(f"| {label} | {100*scenario['fraction_cash_including_entry_fee']:.0f}% | {scenario['costs']['name']} | "
                            f"{100*scenario['net_return']:.4f} | {100*scenario['max_drawdown_closed_trades']:.4f} |")
    policy = analysis["proposed_risk_policy"]
    rows += ["", "## Proposta de gestão de capital, sem implementação", "",
             "Orçamento de perda nominal por trade: 0,5% do saldo; teto de exposição: 10%; uma posição",
             "spot long, sem DCA/alavancagem. Alocação inclui taxas. Essas são restrições de risco",
             "propostas, não uma escolha do cenário mais rentável nem uma otimização sobre 2025.",
             "`fração = min(10%, 0,5% / perda_por_posição_no_stop_com_custos)`.",
             f"Com stop de 5% e custos centrais, perda modelada por posição {100*policy['modeled_loss_at_5_percent_stop_central_costs']:.4f}%;",
             f"teto resultante {100*policy['maximum_cash_fraction']:.4f}% da carteira, em vez de 99%.",
             "Antes de simular ordens, arredondar quantidade para baixo, conferir lote/notional, rejeitar",
             "stakes abaixo do mínimo e reservar caixa para custos. Não elevar stake para atingir o mínimo.",
             "Propor revisão ao atingir 3% de drawdown e pausa de novas entradas aos 6%, até revisão registrada;",
             "3 perdas consecutivas acionam pausa simulada de 24h. Regras não foram aplicadas aos exports.",
             f"Um gap hipotético de −10%, nessa fração e custos centrais, causaria {100*policy['risk_with_10_percent_gap_at_this_fraction']:.4f}%",
             "de perda da carteira, acima do orçamento nominal: stop não garante o limite em gaps.", "",
             "## Por que perdeu: fatos e hipóteses", "",
             "**Fatos:** P&L bruto negativo, custos relevantes, profit factor abaixo de 1, mais trades",
             "perdedores que vencedores e perdas agregadas concentradas nos stops. O buy-and-hold já",
             "publicado foi superior nos dois períodos; a exposição temporal foi somente 22,35%/29,17%.",
             "Isso explica a identidade contábil das perdas e a baixa participação no movimento do ativo,",
             "sem identificar sozinho uma causa econômica única.", "",
             "**Hipóteses a testar somente em 2024:** cruzamentos atrasados em movimentos curtos podem",
             "gerar reversões; RSI ≥ 75 pode encerrar tendências cedo; ausência de filtro de regime pode",
             "aumentar whipsaws. Os exports não comprovam regime lateral nem permitem atribuir todas as",
             "saídas especificamente ao RSI. Ajustar/remover stops pelos trades já vistos seria seleção retrospectiva.", "",
             "## Próxima etapa e critérios para ML", "",
             "Veja [experiment-plan.md](experiment-plan.md) para folds de 2024, orçamento de experimentos,",
             "critérios de risco/custos e congelamento antes de abrir o novo holdout. A baseline atual não",
             "passa o critério econômico: perdeu mesmo antes de taxas nos fills publicados. ML fica bloqueado",
             "até dados/protocolo causais, benchmark simples robusto, custos de estresse e critérios objetivos",
             "serem satisfeitos. Nenhum ML, chave, operação real ou alegação de lucratividade futura nesta etapa.", ""]
    return "\n".join(line.rstrip() for line in rows)
