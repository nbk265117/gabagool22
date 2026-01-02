"""
Arbitrage Engine for the Gabagool Bot
Implements the core arbitrage strategy: buy both sides when cheap
"""
import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from config import BotConfig
from position_tracker import PositionTracker

logger = logging.getLogger(__name__)


class TradeSide(Enum):
    YES = "YES"
    NO = "NO"
    NONE = "NONE"


@dataclass
class TradeSignal:
    """Signal to execute a trade"""
    side: TradeSide
    price: float
    quantity: float
    reason: str
    projected_pair_cost: float


class ArbitrageEngine:
    """
    Core arbitrage logic engine

    Strategy:
    1. Monitor YES and NO prices
    2. Buy whichever side is cheap (price + other_avg < max_pair_cost)
    3. Keep positions roughly balanced
    4. Stop when profit is locked (pair_cost < 1.0 and good balance)
    """

    def __init__(self, config: BotConfig, tracker: PositionTracker):
        self.config = config
        self.tracker = tracker

        # Strategy thresholds
        self.max_pair_cost = config.max_pair_cost
        self.max_trade_amount = config.max_trade_amount
        self.max_total_exposure = config.max_total_exposure
        self.min_profit_target = config.min_profit_target

    def analyze_opportunity(
        self,
        yes_price: float,
        no_price: float,
    ) -> Optional[TradeSignal]:
        """
        Analyze current prices and determine if there's a trade opportunity

        Args:
            yes_price: Current YES ask price (price to buy YES)
            no_price: Current NO ask price (price to buy NO)

        Returns:
            TradeSignal if there's an opportunity, None otherwise
        """
        # Check if we've hit our exposure limit
        if self.tracker.total_cost >= self.max_total_exposure:
            logger.debug("Max exposure reached, no new trades")
            return None

        # Check if profit is already locked
        if self._is_profit_locked():
            logger.info(f"Profit locked: ${self.tracker.locked_profit:.2f}")
            return None

        # Calculate current market pair cost (what market is offering)
        market_pair_cost = yes_price + no_price

        # If market pair cost is already >= 1.0, no arbitrage opportunity
        if market_pair_cost >= 1.0:
            logger.debug(f"No arbitrage: market pair cost = {market_pair_cost:.4f}")
            return None

        # Determine which side to buy based on:
        # 1. Which side keeps our pair cost lowest
        # 2. Which side helps balance our positions

        yes_signal = self._evaluate_yes_buy(yes_price, no_price)
        no_signal = self._evaluate_no_buy(yes_price, no_price)

        # Choose the better opportunity
        if yes_signal and no_signal:
            # Both are opportunities - prefer the one that:
            # 1. Gives better pair cost
            # 2. Or helps balance positions if pair costs are similar
            if yes_signal.projected_pair_cost < no_signal.projected_pair_cost - 0.001:
                return yes_signal
            elif no_signal.projected_pair_cost < yes_signal.projected_pair_cost - 0.001:
                return no_signal
            else:
                # Similar pair costs - prefer the side that balances
                return self._prefer_balancing_side(yes_signal, no_signal)

        return yes_signal or no_signal

    def _evaluate_yes_buy(
        self, yes_price: float, no_price: float
    ) -> Optional[TradeSignal]:
        """Evaluate if buying YES is a good opportunity"""
        # Simulate the trade
        quantity = self._calculate_quantity(yes_price)
        if quantity <= 0:
            return None

        projected_pair_cost = self.tracker.simulate_yes_trade(quantity, yes_price)

        # Check if this keeps us under the limit
        if projected_pair_cost > self.max_pair_cost:
            return None

        # Check if YES is relatively cheap
        # YES is cheap if: yes_price < (1 - no_avg_price) with some margin
        if self.tracker.no_position.quantity > 0:
            implied_yes_ceiling = 1.0 - self.tracker.no_position.average_price
            if yes_price >= implied_yes_ceiling:
                return None

        return TradeSignal(
            side=TradeSide.YES,
            price=yes_price,
            quantity=quantity,
            reason=f"YES cheap at ${yes_price:.4f}",
            projected_pair_cost=projected_pair_cost,
        )

    def _evaluate_no_buy(
        self, yes_price: float, no_price: float
    ) -> Optional[TradeSignal]:
        """Evaluate if buying NO is a good opportunity"""
        quantity = self._calculate_quantity(no_price)
        if quantity <= 0:
            return None

        projected_pair_cost = self.tracker.simulate_no_trade(quantity, no_price)

        if projected_pair_cost > self.max_pair_cost:
            return None

        # Check if NO is relatively cheap
        if self.tracker.yes_position.quantity > 0:
            implied_no_ceiling = 1.0 - self.tracker.yes_position.average_price
            if no_price >= implied_no_ceiling:
                return None

        return TradeSignal(
            side=TradeSide.NO,
            price=no_price,
            quantity=quantity,
            reason=f"NO cheap at ${no_price:.4f}",
            projected_pair_cost=projected_pair_cost,
        )

    def _calculate_quantity(self, price: float) -> float:
        """Calculate quantity to buy based on price and limits"""
        # How much can we spend?
        remaining_budget = self.max_total_exposure - self.tracker.total_cost
        trade_budget = min(self.max_trade_amount, remaining_budget)

        if trade_budget <= 0:
            return 0

        # Calculate quantity
        quantity = trade_budget / price
        return quantity

    def _prefer_balancing_side(
        self, yes_signal: TradeSignal, no_signal: TradeSignal
    ) -> TradeSignal:
        """When both sides are equally attractive, prefer the balancing side"""
        imbalance = self.tracker.quantity_imbalance

        # Positive imbalance = more YES, so prefer NO
        # Negative imbalance = more NO, so prefer YES
        if imbalance > 0:
            return no_signal
        elif imbalance < 0:
            return yes_signal
        else:
            # Perfectly balanced - prefer cheaper price
            if yes_signal.price < no_signal.price:
                return yes_signal
            return no_signal

    def _is_profit_locked(self) -> bool:
        """Check if we've locked in enough profit to stop trading"""
        if self.tracker.locked_profit >= self.min_profit_target:
            if self.tracker.balance_ratio >= 0.8:  # At least 80% balanced
                return True
        return False

    def get_trade_recommendation(
        self,
        yes_price: float,
        no_price: float,
    ) -> dict:
        """
        Get a detailed trade recommendation

        Returns dict with:
        - action: "BUY_YES", "BUY_NO", or "HOLD"
        - details: explanation and metrics
        """
        signal = self.analyze_opportunity(yes_price, no_price)

        if signal is None:
            return {
                "action": "HOLD",
                "reason": "No arbitrage opportunity",
                "market_pair_cost": yes_price + no_price,
                "our_pair_cost": self.tracker.pair_cost,
                "locked_profit": self.tracker.locked_profit,
            }

        return {
            "action": f"BUY_{signal.side.value}",
            "price": signal.price,
            "quantity": signal.quantity,
            "cost": signal.price * signal.quantity,
            "reason": signal.reason,
            "projected_pair_cost": signal.projected_pair_cost,
            "market_pair_cost": yes_price + no_price,
            "current_pair_cost": self.tracker.pair_cost,
        }

    def calculate_optimal_prices(self) -> dict:
        """
        Calculate optimal bid prices for both sides

        Returns the maximum price we should pay for each side
        while maintaining profitability
        """
        # If we have no positions, any price < max_pair_cost / 2 is okay
        if self.tracker.total_cost == 0:
            half_max = self.max_pair_cost / 2
            return {
                "max_yes_price": half_max,
                "max_no_price": half_max,
            }

        # Calculate max prices based on current positions
        # max_yes = max_pair_cost - avg_no (but not more than 0.95)
        # max_no = max_pair_cost - avg_yes (but not more than 0.95)

        if self.tracker.no_position.quantity > 0:
            max_yes = min(
                self.max_pair_cost - self.tracker.no_position.average_price,
                0.95
            )
        else:
            max_yes = self.max_pair_cost

        if self.tracker.yes_position.quantity > 0:
            max_no = min(
                self.max_pair_cost - self.tracker.yes_position.average_price,
                0.95
            )
        else:
            max_no = self.max_pair_cost

        return {
            "max_yes_price": max(max_yes, 0.01),
            "max_no_price": max(max_no, 0.01),
        }
