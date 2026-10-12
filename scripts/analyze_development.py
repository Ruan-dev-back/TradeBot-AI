"""2024 native exports and explicit hypothetical cost/risk replays, never holdout."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import math
from pathlib import Path
import tempfile
import zipfile

from audit_guard import require_development_dates, require_locked_holdout, verify_baseline
from paper_risk import RiskPolicy, RiskState
from risk_model import COST_SCENARIOS, fixed_quantity_costs, notionals
from run_research import trade_metrics

ROOT = Path(__file__).resolve().parents[1]


class TransientReplayState(RiskState):
    """Same policy/state transitions in RAM, exclusively for independent fold replays."""
    def save(self):
        pass  # No restart is modeled here. Actual operator still uses persisted RiskState.


def profit_metrics(profits):
    gains = sum(p for p in profits if p > 0)
    losses = -sum(p for p in profits if p < 0)
    return {'trades': len(profits), 'net_pnl': sum(profits),
            'profit_factor': gains / losses if losses else None,
            'winrate': sum(p > 0 for p in profits) / len(profits) if profits else None}


def rounded_quantity(stake, rate, tick):
    if not all(math.isfinite(x) and x > 0 for x in (stake, rate, tick)):
        raise ValueError('Invalid quantity/rate/tick')
    step = Decimal(str(tick))
    return float((Decimal(str(stake)) / Decimal(str(rate)) / step).to_integral_value(rounding=ROUND_FLOOR) * step)


def benchmark(frame, costs, minimum=5, tick=.00001):
    # Match the native effective boundary using OPEN at first and last timestamps.
    entry = float(frame['open'].iloc[0]) * (1 + costs.execution)
    exit_ = float(frame['open'].iloc[-1]) * (1 - costs.execution)
    amount = rounded_quantity(1000 / (1 + costs.fee), entry, tick)
    if amount * entry < minimum:
        raise ValueError('Benchmark below exchange minimum')
    paid, received = amount * entry * (1 + costs.fee), amount * exit_ * (1 - costs.fee)
    peak, drawdown = 1000.0, 0.0
    for index, row in enumerate(frame.itertuples(index=False)):
        mark = row.open if index == len(frame)-1 else row.close
        equity = 1000-paid + amount*mark*(1-costs.execution)*(1-costs.fee)
        peak = max(peak, equity)
        drawdown = max(drawdown, 1-equity/peak)
    return {'net_pnl': received-paid, 'net_return': (received-paid)/1000,
            'entry_raw_open': float(frame['open'].iloc[0]), 'exit_raw_open': float(frame['open'].iloc[-1]),
            'quantity': amount, 'fees': amount * (entry+exit_) * costs.fee,
            'max_drawdown_hourly_liquidation': drawdown,
            'cash_return': 0.0, 'cash_drawdown': 0.0}


def replay_opportunities(trades, frame, costs, minimum=5, tick=.00001):
    """Event replay of native opportunities only; not a full native cost backtest."""
    require_development_dates(frame['date'])
    fee, execution = costs.fee, costs.execution
    # Never increase sizing because the reference/low cost scenario is cheaper.
    policy = RiskPolicy(fee=max(.0015, fee), additional_fee=0,
                        spread=max(.001, costs.spread_bps/10000),
                        slippage=max(.001, costs.slippage_bps_per_side/10000))
    start, end = frame['date'].iloc[0].to_pydatetime(), frame['date'].iloc[-1].to_pydatetime()
    opened = {}
    for identifier, trade in enumerate(trades, 1):
        begin, finish = (datetime.fromisoformat(trade[k]) for k in ('open_date', 'close_date'))
        if (begin.tzinfo is None or finish.tzinfo is None
                or begin.utcoffset()!=timedelta(0) or finish.utcoffset()!=timedelta(0)
                or not start <= begin < end
                or not begin <= finish <= end or begin in opened):
            raise ValueError('Invalid or overlapping replay opportunity')
        opened[begin] = (identifier, trade, finish)
    cash, position = 1000.0, None
    profits, fills, skipped = [], [], []
    peak, max_dd, fees_total = 1000.0, 0.0, 0.0
    invested_integral = exposure_integral = 0.0
    max_entry_cash_fraction = max_nominal_risk_fraction = 0.0
    with tempfile.TemporaryDirectory(prefix='tradebot-cost-replay-') as directory:
        state = TransientReplayState(Path(directory) / 'risk.sqlite', policy)

        def close(raw_price, now, reason):
            nonlocal cash, position, fees_total
            received = position['amount'] * raw_price * (1-execution) * (1-fee)
            profit = received-position['paid']
            cash += received
            fees_total += position['amount'] * raw_price * (1-execution) * fee
            profits.append(profit)
            fills.append({'native_id': position['id'], 'opened': position['opened'].isoformat(),
                          'closed': now.isoformat(), 'net_pnl': profit, 'reason': reason,
                          'entry_cash_fraction': position['entry_cash_fraction']})
            state.observe(cash, now, [(position['id'], now, profit)])
            position = None

        for row in frame.itertuples(index=False):
            now = row.date.to_pydatetime()
            if position and position['close_at'] == now:
                close(position['native']['close_rate'], now, position['native']['exit_reason'])
            if now in opened:
                identifier, native, finish = opened[now]
                if position is not None or not state.allowed(now):
                    skipped.append({'id': identifier, 'reason': 'position/cooldown/drawdown'})
                else:
                    raw = native['open_rate']
                    rate = raw * (1+execution)
                    # Stake policy reserves conservative entry costs; execution is explicit here.
                    stake = policy.stake(cash, cash, minimum, cash)
                    quantity = rounded_quantity(stake, rate, tick) if stake else 0
                    paid = quantity * rate * (1+fee)
                    reserve = quantity * raw * (1+policy.entry_fee) * (1+policy.execution_cost)
                    if (quantity <= 0 or quantity*rate < minimum or paid > cash
                            or reserve > policy.cash_cap(cash, cash)+1e-9):
                        skipped.append({'id': identifier, 'reason': 'minimum/cash/risk'})
                    else:
                        fraction = reserve/cash
                        nominal = reserve*policy.loss_fraction/cash
                        max_entry_cash_fraction = max(max_entry_cash_fraction, fraction)
                        max_nominal_risk_fraction = max(max_nominal_risk_fraction, nominal)
                        position = {'id': identifier, 'native': native, 'close_at': finish,
                                    'amount': quantity, 'paid': paid, 'opened': now,
                                    'entry_cash_fraction': fraction}
                        fees_total += quantity*rate*fee
                        cash -= paid
                        if finish == now:
                            close(native['close_rate'], now, native['exit_reason'])
            terminal = now == end
            mark_time = now if terminal else now+timedelta(hours=1)
            mark_price = row.open if terminal else row.close
            value = position['amount']*mark_price*(1-execution)*(1-fee) if position else 0
            equity = cash+value
            peak = max(peak, equity)
            max_dd = max(max_dd, 1-equity/peak)
            state.observe(equity, mark_time)
            if position and (state.data['halted'] or terminal):
                close(mark_price, mark_time, 'risk_drawdown_halt' if state.data['halted'] else 'force_exit')
            if not terminal and position:
                invested_integral += 3600
                exposure_integral += value/equity*3600
            if cash < -1e-8:
                raise ValueError('Negative replay cash')
    duration = (end-start).total_seconds()
    return {**profit_metrics(profits), 'net_return': (cash-1000)/1000,
            'max_drawdown_hourly_liquidation': max_dd, 'fees': fees_total,
            'time_exposure_hourly': invested_integral/duration,
            'mean_capital_exposure_hourly': exposure_integral/duration,
            'max_entry_cash_fraction': max_entry_cash_fraction,
            'max_nominal_risk_fraction': max_nominal_risk_fraction,
            'skipped': skipped, 'hypothetical_fills': fills, 'risk_policy': asdict(policy),
            'limitation': 'native trade opportunities only; suppressed signals not reconstructed; hypothetical hourly fills'}


def main():
    import pandas as pd
    from audit_bias import read_development_only
    from validate_data import validate_candles
    verify_baseline();require_locked_holdout()
    lock = json.loads((ROOT/'docs/research2024-extension-lock.json').read_text())
    for name, expected in lock['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Pre-experiment protocol changed')
    source = ROOT/'user_data/data/binance/BTC_USDT-1h.feather'
    manifest = json.loads((ROOT/'docs/evidence/data_manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Source dataset lineage mismatch')
    frame = read_development_only(source)
    folder = sorted((ROOT/'user_data/research/development-experiments').glob('complete-*'))[-1]
    out = ROOT/'user_data/research/research2024-analysis';out.mkdir(parents=True,exist_ok=True)
    report = {'source': 'Binance BTC/USDT spot 1h only', 'holdout_prices_inspected': False,
              'protocol': lock, 'costs': [asdict(c) for c in COST_SCENARIOS], 'folds': {}}
    for fold in ('D1','D2','D3'):
        report['folds'][fold] = {}
        for directory in sorted((folder/fold).iterdir()):
            archive = next(directory.glob('*.zip'))
            with zipfile.ZipFile(archive) as z:
                name = next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
                native = json.loads(z.read(name));stat = next(iter(native['strategy'].values()))
                wallet_name = next(n for n in z.namelist() if n.endswith('_wallet.feather'))
                # Filter native wallet marks before exposing prices to pandas, including
                # the possible next-midnight record beyond the effective fold boundary.
                import pyarrow as pa
                import pyarrow.dataset as ds
                with tempfile.TemporaryDirectory(prefix='tradebot-wallet-') as tmp:
                    path = Path(tmp)/'wallet.feather';path.write_bytes(z.read(wallet_name))
                    dataset = ds.dataset(path,format='ipc');dtype = dataset.schema.field('date').type
                    lower = pa.scalar(datetime.fromisoformat(stat['backtest_start']).replace(tzinfo=timezone.utc),type=dtype)
                    upper = pa.scalar(datetime.fromisoformat(stat['backtest_end']).replace(tzinfo=timezone.utc),type=dtype)
                    wallet = dataset.to_table(filter=(ds.field('date')>=lower)&(ds.field('date')<=upper)).to_pandas()
                require_development_dates(wallet['date'])
                total = wallet.groupby('date')['total_quote'].sum()
                invested = wallet.loc[wallet['currency']!='USDT'].groupby('date')['total_quote'].sum()
                exposure = invested.reindex(total.index,fill_value=0)/total
            metrics = trade_metrics(stat)
            start = pd.Timestamp(stat['backtest_start'],tz='UTC');end = pd.Timestamp(stat['backtest_end'],tz='UTC')
            active = frame.loc[(frame['date']>=start)&(frame['date']<=end)].reset_index(drop=True)
            validate_candles(active);require_development_dates(active['date'])
            fees = sum(notionals(t)[0]*t['fee_open']+notionals(t)[1]*t['fee_close'] for t in stat['trades'])
            result = {'native': {'trades': stat['total_trades'], 'net_pnl': stat['profit_total_abs'],
              'net_return':stat['profit_total'],'profit_factor':metrics['profit_factor'] if math.isfinite(metrics['profit_factor'] or 0) else None,
              'winrate':metrics['winrate'],'time_exposure':metrics['exposure'],'fees':fees,
              'mean_capital_exposure_native_marks':float(exposure.mean()),
              'max_capital_exposure_native_marks':float(exposure.max()),
              'max_drawdown_closed':stat['max_drawdown_account'],
              'max_drawdown_marked':stat['wallet_stats']['max_drawdown_account'],
              'effective_start':str(start),'effective_end':str(end)}, 'scenarios': {}}
            for costs in COST_SCENARIOS:
                result['scenarios'][costs.name] = {'fixed_quantities_net_pnl':fixed_quantity_costs(stat['trades'],costs),
                  'benchmark':benchmark(active,costs), 'risk_replay':replay_opportunities(stat['trades'],active,costs)}
            report['folds'][fold][directory.name] = result
            (out/f'{fold}-{directory.name}-native.json').write_text(json.dumps({'native_json':native,'export_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'protocol':json.loads((directory/'protocol.json').read_text())},indent=2,allow_nan=False)+'\n')
    report['acceptance'] = {}
    for candidate in report['folds']['D1']:
        rows = [report['folds'][f][candidate] for f in ('D1','D2','D3')]
        central = [r['scenarios']['central']['risk_replay'] for r in rows]
        adverse = [r['scenarios']['adverse']['risk_replay'] for r in rows]
        profits = [f['net_pnl'] for r in central for f in r['hypothetical_fills']]
        combined = profit_metrics(profits)
        gates = {'minimum_sample':combined['trades']>=50 and all(r['trades']>=10 for r in central),
                 'central_pnl_pf':combined['net_pnl']>0 and (combined['profit_factor'] or 0)>=1.10,
                 'two_positive_folds':sum(r['net_pnl']>0 for r in central)>=2,
                 'adverse_nonnegative':sum(r['net_pnl'] for r in adverse)>=0,
                 'marked_drawdown':max(r['max_drawdown_hourly_liquidation'] for r in central)<=.06}
        report['acceptance'][candidate] = {'central_aggregate':combined,'adverse_aggregate_pnl':sum(r['net_pnl'] for r in adverse),
          'gates':gates,'economic_and_sample_gates_passed':all(gates.values()),'promoted':False,
          'remaining_gates':['full signal replay/native execution costs','native candidate lookahead/recursive','gap and block uncertainty'],
          'independent_validation':False}
    (out/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(out),'acceptance':report['acceptance']},indent=2))
    verify_baseline();require_locked_holdout()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
