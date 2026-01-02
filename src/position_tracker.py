"""
Position Tracker for the Gabagool Arbitrage Bot
Tracks YES/NO positions and calculates pair cost
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Record of a single trade"""
    timestamp: datetime
    side: str  # "YES" or "NO"
    quantity: float
    price: float
    cost: float  # quantity * price

    def __post_init__(self):
        self.cost = self.quantity * self.price


@dataclass
class Position:
    """Position for one side (YES or NO)"""
    quantity: float = 0.0
    total_cost: float = 0.0
    trades: list[Trade] = field(default_factory=list)

    @property
    def average_price(self) -> float:
        """Calculate average price paid"""
        if self.quantity == 0:
            return 0.0
        return self.total_cost / self.quantity

    def add_trade(self, quantity: float, price: float) -> Trade:
        """Add a trade to this position"""
        trade = Trade(
            timestamp=datetime.now(),
            side="",  # Will be set by caller
            quantity=quantity,
            price=price,
            cost=quantity * price,
        )
        self.quantity += quantity
        self.total_cost += trade.cost
        self.trades.append(trade)
        return trade


@dataclass
class PositionTracker:
    """
    Tracks YES and NO positions and calculates arbitrage metrics

    The core arbitrage formula:
    - Pair Cost = avg_YES + avg_NO
    - If Pair Cost < 1.0, profit is locked in

    Guaranteed profit = min(qty_YES, qty_NO) - (cost_YES + cost_NO) * (min_qty / total_qty)
    """
    yes_position: Position = field(default_factory=Position)
    no_position: Position = field(default_factory=Position)

    @property
    def pair_cost(self) -> float:
        """
        Calculate the pair cost (avg_YES + avg_NO)
        This is the key metric - must be < 1.0 for profit
        """
        return self.yes_position.average_price + self.no_position.average_price

    @property
    def total_cost(self) -> float:
        """Total USDC spent on both sides"""
        return self.yes_position.total_cost + self.no_position.total_cost

    @property
    def min_quantity(self) -> float:
        """Minimum quantity between YES and NO (hedged amount)"""
        return min(self.yes_position.quantity, self.no_position.quantity)

    @property
    def quantity_imbalance(self) -> float:
        """
        Imbalance between YES and NO quantities
        Positive = more YES, Negative = more NO
        """
        return self.yes_position.quantity - self.no_position.quantity

    @property
    def balance_ratio(self) -> float:
        """
        Ratio of smaller position to larger position
        1.0 = perfectly balanced
        """
        if self.yes_position.quantity == 0 or self.no_position.quantity == 0:
            return 0.0
        min_qty = min(self.yes_position.quantity, self.no_position.quantity)
        max_qty = max(self.yes_position.quantity, self.no_position.quantity)
        return min_qty / max_qty

    @property
    def guaranteed_payout(self) -> float:
        """
        Guaranteed payout at settlement
        = min(qty_YES, qty_NO) * $1.00
        """
        return self.min_quantity

    @property
    def locked_profit(self) -> float:
        """
        Profit that is mathematically locked in
        Only positive if pair_cost < 1.0 and we have balanced positions
        """
        if self.min_quantity == 0:
            return 0.0

        # Cost for the hedged portion
        hedged_cost = (
            self.yes_position.average_price + self.no_position.average_price
        ) * self.min_quantity

        # Hedged portion always pays out $1 per share
        hedged_payout = self.min_quantity

        return hedged_payout - hedged_cost

    @property
    def max_potential_profit(self) -> float:
        """Maximum potential profit if the larger side wins"""
        if self.yes_position.quantity >= self.no_position.quantity:
            # YES wins scenario
            return self.yes_position.quantity - self.total_cost
        else:
            # NO wins scenario
            return self.no_position.quantity - self.total_cost

    @property
    def min_potential_profit(self) -> float:
        """Minimum potential profit (worst case scenario)"""
        if self.yes_position.quantity >= self.no_position.quantity:
            # NO wins scenario (we have excess YES)
            return self.no_position.quantity - self.total_cost
        else:
            # YES wins scenario (we have excess NO)
            return self.yes_position.quantity - self.total_cost

    def add_yes_trade(self, quantity: float, price: float) -> Trade:
        """Record a YES purchase"""
        trade = self.yes_position.add_trade(quantity, price)
        trade.side = "YES"
        logger.info(
            f"YES Trade: {quantity:.2f} shares @ ${price:.4f} "
            f"| Avg: ${self.yes_position.average_price:.4f} "
            f"| Pair Cost: {self.pair_cost:.4f}"
        )
        return trade

    def add_no_trade(self, quantity: float, price: float) -> Trade:
        """Record a NO purchase"""
        trade = self.no_position.add_trade(quantity, price)
        trade.side = "NO"
        logger.info(
            f"NO Trade: {quantity:.2f} shares @ ${price:.4f} "
            f"| Avg: ${self.no_position.average_price:.4f} "
            f"| Pair Cost: {self.pair_cost:.4f}"
        )
        return trade

    def simulate_yes_trade(self, quantity: float, price: float) -> float:
        """
        Simulate a YES trade and return the new pair cost
        WITHOUT actually executing it
        """
        new_qty = self.yes_position.quantity + quantity
        new_cost = self.yes_position.total_cost + (quantity * price)
        new_avg_yes = new_cost / new_qty if new_qty > 0 else 0

        return new_avg_yes + self.no_position.average_price

    def simulate_no_trade(self, quantity: float, price: float) -> float:
        """
        Simulate a NO trade and return the new pair cost
        WITHOUT actually executing it
        """
        new_qty = self.no_position.quantity + quantity
        new_cost = self.no_position.total_cost + (quantity * price)
        new_avg_no = new_cost / new_qty if new_qty > 0 else 0

        return self.yes_position.average_price + new_avg_no

    def should_buy_yes(self, price: float, max_pair_cost: float) -> tuple[bool, float]:
        """
        Determine if we should buy YES at this price

        Returns:
            (should_buy, max_quantity)
        """
        # If we have no NO position yet, any YES price < max_pair_cost is ok
        if self.no_position.quantity == 0:
            if price < max_pair_cost:
                return True, float("inf")
            return False, 0

        # Calculate max quantity that keeps pair cost under limit
        # new_pair_cost = (yes_cost + new_cost) / (yes_qty + new_qty) + avg_NO < max_pair_cost
        # This is complex to solve exactly, so we use simulation

        if self.simulate_yes_trade(1, price) <= max_pair_cost:
            return True, float("inf")  # Simplified - in practice, calculate exact max

        return False, 0

    def should_buy_no(self, price: float, max_pair_cost: float) -> tuple[bool, float]:
        """
        Determine if we should buy NO at this price

        Returns:
            (should_buy, max_quantity)
        """
        if self.yes_position.quantity == 0:
            if price < max_pair_cost:
                return True, float("inf")
            return False, 0

        if self.simulate_no_trade(1, price) <= max_pair_cost:
            return True, float("inf")

        return False, 0

    def get_status(self) -> dict:
        """Get current position status"""
        return {
            "yes_quantity": self.yes_position.quantity,
            "yes_avg_price": self.yes_position.average_price,
            "yes_total_cost": self.yes_position.total_cost,
            "no_quantity": self.no_position.quantity,
            "no_avg_price": self.no_position.average_price,
            "no_total_cost": self.no_position.total_cost,
            "pair_cost": self.pair_cost,
            "total_cost": self.total_cost,
            "locked_profit": self.locked_profit,
            "balance_ratio": self.balance_ratio,
            "min_quantity": self.min_quantity,
        }

    def print_status(self):
        """Print formatted position status"""
        print("\n" + "=" * 60)
        print("POSITION STATUS")
        print("=" * 60)
        print(f"YES: {self.yes_position.quantity:,.2f} shares @ avg ${self.yes_position.average_price:.4f} = ${self.yes_position.total_cost:,.2f}")
        print(f"NO:  {self.no_position.quantity:,.2f} shares @ avg ${self.no_position.average_price:.4f} = ${self.no_position.total_cost:,.2f}")
        print("-" * 60)
        print(f"Pair Cost: ${self.pair_cost:.4f} {'< $1.00' if self.pair_cost < 1.0 else '>= $1.00'}")
        print(f"Total Spent: ${self.total_cost:,.2f}")
        print(f"Guaranteed Payout: ${self.guaranteed_payout:,.2f}")
        print(f"Locked Profit: ${self.locked_profit:,.2f}")
        print(f"Balance Ratio: {self.balance_ratio:.2%}")
        print("=" * 60 + "\n")

    def reset(self):
        """Reset all positions for a new trading window"""
        self.yes_position = Position()
        self.no_position = Position()
        logger.info("Positions reset for new trading window")
