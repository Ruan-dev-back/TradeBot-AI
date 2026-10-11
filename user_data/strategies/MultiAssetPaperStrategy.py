"""Estratégia multiativos SOMENTE para simulação; regras de SMA/RSI não lucrativas no histórico."""
from SmaRsiStrategy import SmaRsiStrategy


class MultiAssetPaperStrategy(SmaRsiStrategy):
    """Reaproveita a baseline, sem mudar indicadores ou prometer retornos."""

    def confirm_trade_entry(
        self, pair, order_type, amount, rate, time_in_force,
        current_time, entry_tag, side, **kwargs
    ) -> bool:
        return (
            self.config.get("dry_run") is True
            and self.config.get("trading_mode") == "spot"
            and self.config.get("exchange", {}).get("name") == "kraken"
            and pair in {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
            and pair in self.config.get("exchange", {}).get("pair_whitelist", [])
            and side == "long"
        )
