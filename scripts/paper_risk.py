"""Fixed paper-only risk policy. Budgets are nominal, not guarantees on gaps."""

from dataclasses import asdict, dataclass
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3


def finite_positive(*values):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) and x > 0 for x in values)


@dataclass(frozen=True)
class RiskPolicy:
    position_cap: float = 0.10
    risk_budget: float = 0.005
    stop: float = 0.05
    fee: float = 0.004  # Conservative Kraken taker assumption, not Binance historical fee.
    additional_fee: float = 0.0005
    spread: float = 0.001  # Full spread; half applied on each side.
    slippage: float = 0.001  # Per side, a scenario assumption.
    drawdown_warning: float = 0.03
    drawdown_halt: float = 0.06
    consecutive_losses: int = 3
    cooldown_hours: int = 24

    def __post_init__(self):
        if (not finite_positive(self.position_cap, self.risk_budget, self.stop, self.fee,
                                self.drawdown_warning, self.drawdown_halt)
                or self.position_cap > 0.10 or self.risk_budget > 0.005 or self.stop != 0.05
                or not 0 <= self.additional_fee < 0.1 or not 0 <= self.spread < 0.1
                or not 0 <= self.slippage < 0.1 or self.fee >= 0.1
                or not self.drawdown_warning < self.drawdown_halt <= 0.06):
            raise ValueError('Invalid or enlarged paper risk budget')

    @property
    def entry_fee(self):
        return self.fee + self.additional_fee

    @property
    def execution_cost(self):
        return self.spread / 2 + self.slippage

    @property
    def loss_fraction(self):
        c, fee = self.execution_cost, self.entry_fee
        return 1 - (1 - self.stop) * (1 - c) / (1 + c) * (1 - fee) / (1 + fee)

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    def cash_cap(self, equity, free_cash):
        if not finite_positive(equity, free_cash):
            return 0.0
        return min(equity * self.position_cap, equity * self.risk_budget / self.loss_fraction,
                   free_cash)

    def stake(self, equity, free_cash, minimum, maximum):
        if (minimum is None or not finite_positive(minimum, maximum)):
            return 0.0
        # Reserve entry fee and modeled adverse entry execution in the cash budget.
        result = min(self.cash_cap(equity, free_cash) /
                     ((1 + self.entry_fee) * (1 + self.execution_cost)), maximum)
        return result if result >= minimum else 0.0  # Never upscale to exchange minimum.

    def allows_notional(self, notional, equity, free_cash, minimum):
        if not finite_positive(notional, equity, free_cash, minimum) or notional >= equity:
            return False
        cash = notional * (1 + self.entry_fee) * (1 + self.execution_cost)
        return (notional >= minimum and cash <= self.cash_cap(equity, free_cash) + 1e-9
                and cash * self.loss_fraction <= equity * self.risk_budget + 1e-9)


class RiskState:
    """SQLite atomic snapshot: peak, halt, cooldown and processed closed-trade IDs."""

    def __init__(self, path, policy=None, initial_equity=1000):
        self.policy = policy or RiskPolicy()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS risk (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            row = db.execute('SELECT body FROM risk WHERE id=1').fetchone()
            if row:
                self.data = json.loads(row[0])
                if self.data['policy_sha256'] != self.policy.fingerprint:
                    raise ValueError('Risk policy changed; explicit state reconciliation required')
            else:
                if not finite_positive(initial_equity):
                    raise ValueError('Invalid initial paper equity')
                self.data = dict(peak=initial_equity, equity=initial_equity, halted=False,
                                 warning=False, drawdown=0.0, cooldown_until=None,
                                 losses=0, closed_ids=[], policy_sha256=self.policy.fingerprint)
                db.execute('INSERT INTO risk VALUES (1, ?)', (json.dumps(self.data),))

    def save(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE risk SET body=? WHERE id=1',
                       (json.dumps(self.data, allow_nan=False),))

    def observe(self, equity, now, closed=()):
        if not finite_positive(equity) or now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError('Invalid equity or non-UTC observation')
        d = self.data
        d['equity'] = equity
        d['peak'] = max(d['peak'], equity)
        d['drawdown'] = 1 - equity / d['peak']
        d['warning'] = d['drawdown'] >= self.policy.drawdown_warning
        d['halted'] = d['halted'] or d['drawdown'] >= self.policy.drawdown_halt - 1e-12
        for identifier, closed_at, profit in sorted(closed, key=lambda t: (t[1], t[0])):
            if identifier in d['closed_ids']:
                continue
            if (closed_at.tzinfo is None or closed_at.utcoffset() != timedelta(0)
                    or closed_at > now or not math.isfinite(profit)):
                raise ValueError('Invalid closed trade')
            d['closed_ids'].append(identifier)
            d['losses'] = d['losses'] + 1 if profit < 0 else 0
            # One hour after any exit, 24 hours after each sequence of three losses.
            hours = self.policy.cooldown_hours if d['losses'] >= self.policy.consecutive_losses else 1
            until = closed_at + timedelta(hours=hours)
            previous = datetime.fromisoformat(d['cooldown_until']) if d['cooldown_until'] else closed_at
            d['cooldown_until'] = max(previous, until).isoformat()
            if hours == self.policy.cooldown_hours:
                d['losses'] = 0
        d['observed_at'] = now.isoformat()
        self.save()
        return self.allowed(now)

    def allowed(self, now):
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            return False
        until = self.data['cooldown_until']
        return not self.data['halted'] and (until is None or now >= datetime.fromisoformat(until))


def validate_paper_config(config, environ=None):
    """Reject runtime overrides, credentials, unbounded endpoints and real modes."""
    from freqtrade.enums import RunMode
    from paper_profiles import profile_for
    profile = profile_for(config.get('exchange', {}).get('name'))
    if (config.get('dry_run') is not True or config.get('trading_mode') != 'spot'
            or config.get('margin_mode', '') != '' or config.get('max_open_trades') != 1
            or config.get('dry_run_wallet') != 1000 or config.get('stake_currency') != 'USDT'
            or config.get('stake_amount') != 25 or config.get('timeframe') != '1h'
            or config.get('strategy', profile.strategy) != profile.strategy
            or config.get('fee') != RiskPolicy().fee
            or config.get('stoploss', -0.05) != -0.05
            or config.get('position_adjustment_enable', False) is not False
            or config.get('trailing_stop', False) is not False
            or config.get('force_entry_enable') is not False
            or config.get('api_server', {}).get('enabled', False) is not False
            or config.get('telegram', {}).get('enabled') is not False
            or config.get('runmode', RunMode.DRY_RUN) != RunMode.DRY_RUN):
        raise ValueError('Paper configuration must remain fixed, spot and dry-run only')
    ex = config.get('exchange', {})
    if (set(ex.get('pair_whitelist', [])) !=
            {'BTC/USDT', 'ETH/USDT', 'SOL/USDT'} or ex.get('pair_blacklist')
            or any(ex.get(k) for k in ('key', 'secret', 'password', 'uid', 'apiKey', 'api_key',
                                       'account_id', 'walletAddress', 'wallet_address', 'privateKey', 'private_key'))):
        raise ValueError('Only public spot markets without credentials are permitted')
    if ex.get('demo_trading') or ex.get('sandbox'):
        raise ValueError('Exchange demo/sandbox is not the local dry-run engine')
    for field in ('ccxt_config', 'ccxt_async_config'):
        settings = ex.get(field, {})
        allowed = {'enableRateLimit', 'timeout', 'requests_trust_env', 'aiohttp_trust_env', 'cafile'}
        if profile.exchange == 'okx':
            allowed.add('options')
            allowed.add('userAgent')
        if set(settings) - allowed:
            raise ValueError('CCXT endpoint/credential/options overrides are forbidden')
        if 'options' in settings and settings['options'] != {'defaultType': 'spot', 'fetchMarkets': {'types': ['spot']}}:
            raise ValueError('Only fixed OKX public spot market options are allowed')
        if 'userAgent' in settings and settings['userAgent'] != 'TradeBot-AI/0.1 public research':
            raise ValueError('Only the honest fixed TradeBot client identity is allowed')
        if 'cafile' in settings and settings['cafile'] != '/freqtrade/host-ca.pem':
            raise ValueError('Only the read-only managed CA file is allowed')
    if config.get('db_url') != 'sqlite:////freqtrade/user_data/' + profile.database:
        raise ValueError('Paper database must use the dedicated persistent SQLite path')
    if config.get('order_types', {}).get('stoploss_on_exchange'):
        raise ValueError('Exchange-side stop orders are forbidden')
    if any(name.startswith('FREQTRADE__') for name in (environ or {})):
        raise ValueError('FREQTRADE__ overrides are forbidden for this paper service')


def require_current_window(start, end, now):
    """Current warmup must be entirely after reserved holdout, never gap-backfilled."""
    from audit_guard import HOLDOUT_END
    if any(t.tzinfo is None or t.utcoffset() != timedelta(0) for t in (start, end, now)):
        raise ValueError('Current window must use UTC')
    if not HOLDOUT_END <= start < end <= now or end - start > timedelta(days=31):
        raise ValueError('Current-data window overlaps reservation or is not a bounded warmup')
