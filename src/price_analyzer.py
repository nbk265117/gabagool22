"""
Price Analyzer for the Gabagool Bot
Identifies "cheap" vs "rich" prices using technical analysis

Key insight from Reddit comments:
"This misses the single most important part: what is used to identify cheap vs rich prices"
"""
import logging
from dataclasses import dataclass
from typing import Optional
from collections import deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class PricePoint:
    """Single price observation"""
    timestamp: float
    yes_price: float
    no_price: float

    @property
    def pair_cost(self) -> float:
        return self.yes_price + self.no_price


class PriceAnalyzer:
    """
    Analyzes prices to determine if YES or NO is "cheap"

    A price is considered cheap when:
    1. It's significantly below its recent average
    2. The pair cost (YES + NO) is below 1.0
    3. There's volatility indicating emotional trading

    Key metrics:
    - Moving average deviation
    - Volatility (standard deviation)
    - Pair cost spread from 1.0
    """

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.yes_prices: deque = deque(maxlen=window_size)
        self.no_prices: deque = deque(maxlen=window_size)
        self.pair_costs: deque = deque(maxlen=window_size)

        # Thresholds (tunable)
        self.cheap_threshold = 0.15  # 15% below average = cheap
        self.volatility_threshold = 0.05  # Min volatility to trade
        self.max_pair_cost = 0.99  # Max pair cost to consider

    def add_price(self, yes_price: float, no_price: float):
        """Record a new price observation"""
        self.yes_prices.append(yes_price)
        self.no_prices.append(no_price)
        self.pair_costs.append(yes_price + no_price)

    @property
    def yes_average(self) -> float:
        """Moving average of YES prices"""
        if not self.yes_prices:
            return 0.5
        return statistics.mean(self.yes_prices)

    @property
    def no_average(self) -> float:
        """Moving average of NO prices"""
        if not self.no_prices:
            return 0.5
        return statistics.mean(self.no_prices)

    @property
    def yes_volatility(self) -> float:
        """Standard deviation of YES prices"""
        if len(self.yes_prices) < 2:
            return 0
        return statistics.stdev(self.yes_prices)

    @property
    def no_volatility(self) -> float:
        """Standard deviation of NO prices"""
        if len(self.no_prices) < 2:
            return 0
        return statistics.stdev(self.no_prices)

    @property
    def avg_pair_cost(self) -> float:
        """Average pair cost"""
        if not self.pair_costs:
            return 1.0
        return statistics.mean(self.pair_costs)

    def is_yes_cheap(self, current_yes: float) -> tuple[bool, float]:
        """
        Determine if YES is cheap

        Returns:
            (is_cheap, discount_percentage)
        """
        if len(self.yes_prices) < 5:
            # Not enough data - use simple threshold
            return current_yes < 0.45, 0

        avg = self.yes_average
        if avg == 0:
            return False, 0

        discount = (avg - current_yes) / avg

        # YES is cheap if:
        # 1. Price is below average by threshold
        # 2. There's enough volatility (emotional trading)
        is_cheap = (
            discount >= self.cheap_threshold and
            self.yes_volatility >= self.volatility_threshold
        )

        return is_cheap, discount

    def is_no_cheap(self, current_no: float) -> tuple[bool, float]:
        """
        Determine if NO is cheap

        Returns:
            (is_cheap, discount_percentage)
        """
        if len(self.no_prices) < 5:
            return current_no < 0.45, 0

        avg = self.no_average
        if avg == 0:
            return False, 0

        discount = (avg - current_no) / avg

        is_cheap = (
            discount >= self.cheap_threshold and
            self.no_volatility >= self.volatility_threshold
        )

        return is_cheap, discount

    def get_opportunity(
        self,
        yes_price: float,
        no_price: float,
    ) -> Optional[dict]:
        """
        Analyze current prices and return opportunity if exists

        Returns dict with:
        - side: "YES" or "NO" or None
        - price: current price
        - discount: how much below average
        - confidence: strength of signal
        """
        # First check: pair cost must be reasonable
        pair_cost = yes_price + no_price
        if pair_cost >= self.max_pair_cost:
            return None

        # Record prices
        self.add_price(yes_price, no_price)

        # Check both sides
        yes_cheap, yes_discount = self.is_yes_cheap(yes_price)
        no_cheap, no_discount = self.is_no_cheap(no_price)

        # If both are cheap (rare but possible), pick the cheaper one
        if yes_cheap and no_cheap:
            if yes_discount > no_discount:
                return {
                    "side": "YES",
                    "price": yes_price,
                    "discount": yes_discount,
                    "confidence": min(yes_discount / self.cheap_threshold, 2.0),
                    "pair_cost": pair_cost,
                }
            else:
                return {
                    "side": "NO",
                    "price": no_price,
                    "discount": no_discount,
                    "confidence": min(no_discount / self.cheap_threshold, 2.0),
                    "pair_cost": pair_cost,
                }

        if yes_cheap:
            return {
                "side": "YES",
                "price": yes_price,
                "discount": yes_discount,
                "confidence": min(yes_discount / self.cheap_threshold, 2.0),
                "pair_cost": pair_cost,
            }

        if no_cheap:
            return {
                "side": "NO",
                "price": no_price,
                "discount": no_discount,
                "confidence": min(no_discount / self.cheap_threshold, 2.0),
                "pair_cost": pair_cost,
            }

        return None

    def get_stats(self) -> dict:
        """Get current analysis statistics"""
        return {
            "observations": len(self.yes_prices),
            "yes_avg": self.yes_average,
            "no_avg": self.no_average,
            "yes_volatility": self.yes_volatility,
            "no_volatility": self.no_volatility,
            "avg_pair_cost": self.avg_pair_cost,
        }

    def reset(self):
        """Reset for new trading window"""
        self.yes_prices.clear()
        self.no_prices.clear()
        self.pair_costs.clear()


class RiskManager:
    """
    Risk management module

    From Reddit: "I'm focused on the risk management strategy now to basically
    have a solid stop loss mechanism during sudden price swings"
    """

    def __init__(
        self,
        max_loss_per_window: float = 50.0,
        max_drawdown_pct: float = 0.10,
        max_unhedged_exposure: float = 200.0,
    ):
        self.max_loss_per_window = max_loss_per_window
        self.max_drawdown_pct = max_drawdown_pct
        self.max_unhedged_exposure = max_unhedged_exposure

        self.initial_capital = 0.0
        self.current_exposure = 0.0
        self.unrealized_pnl = 0.0

    def set_initial_capital(self, capital: float):
        """Set starting capital for the window"""
        self.initial_capital = capital

    def update_exposure(
        self,
        yes_qty: float,
        yes_cost: float,
        no_qty: float,
        no_cost: float,
        yes_price: float,
        no_price: float,
    ):
        """Update current exposure and P&L"""
        total_cost = yes_cost + no_cost

        # Current value if we could sell now
        yes_value = yes_qty * yes_price
        no_value = no_qty * no_price
        current_value = yes_value + no_value

        self.current_exposure = total_cost
        self.unrealized_pnl = current_value - total_cost

    def should_stop_trading(self) -> tuple[bool, str]:
        """
        Check if we should stop trading due to risk limits

        Returns:
            (should_stop, reason)
        """
        # Check absolute loss limit
        if self.unrealized_pnl < -self.max_loss_per_window:
            return True, f"Max loss reached: ${self.unrealized_pnl:.2f}"

        # Check drawdown percentage
        if self.initial_capital > 0:
            drawdown = -self.unrealized_pnl / self.initial_capital
            if drawdown > self.max_drawdown_pct:
                return True, f"Max drawdown reached: {drawdown:.1%}"

        return False, ""

    def can_add_position(
        self,
        new_cost: float,
        current_yes_qty: float,
        current_no_qty: float,
    ) -> tuple[bool, str]:
        """
        Check if we can add a new position

        Returns:
            (can_add, reason)
        """
        # Check unhedged exposure
        qty_diff = abs(current_yes_qty - current_no_qty)
        unhedged = qty_diff  # Approximate unhedged exposure

        if unhedged > self.max_unhedged_exposure:
            return False, f"Unhedged exposure too high: {unhedged:.2f}"

        return True, ""

    def reset(self):
        """Reset for new trading window"""
        self.current_exposure = 0.0
        self.unrealized_pnl = 0.0
