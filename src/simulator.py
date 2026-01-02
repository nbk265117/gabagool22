"""
Strategy Simulator for the Gabagool Bot
Test the arbitrage strategy without real money
"""
import random
from dataclasses import dataclass
from typing import Optional
import time

from colorama import init, Fore, Style

from position_tracker import PositionTracker
from arbitrage_engine import ArbitrageEngine, TradeSide
from config import BotConfig

init()


@dataclass
class SimulatedMarket:
    """Simulates a volatile 15-minute market"""
    base_price: float = 0.50  # Starting YES probability
    volatility: float = 0.15  # Price swing magnitude
    trend: float = 0.0  # Drift direction

    def tick(self) -> tuple[float, float]:
        """
        Generate next price tick

        Returns (yes_price, no_price) as ask prices
        """
        # Random walk with mean reversion
        self.trend += random.gauss(0, 0.02)
        self.trend = max(-0.1, min(0.1, self.trend))

        change = random.gauss(self.trend, self.volatility)
        self.base_price += change

        # Keep in bounds
        self.base_price = max(0.05, min(0.95, self.base_price))

        # YES ask is slightly above true price (spread)
        yes_ask = min(0.99, self.base_price + random.uniform(0.01, 0.03))

        # NO ask is based on inverse, also with spread
        no_true = 1.0 - self.base_price
        no_ask = min(0.99, no_true + random.uniform(0.01, 0.03))

        return yes_ask, no_ask


def run_simulation(
    num_ticks: int = 200,
    max_pair_cost: float = 0.99,
    max_trade_amount: float = 10.0,
    max_exposure: float = 500.0,
    verbose: bool = True,
):
    """
    Run a simulation of the arbitrage strategy

    Args:
        num_ticks: Number of price updates to simulate
        max_pair_cost: Maximum pair cost threshold
        max_trade_amount: Max per trade
        max_exposure: Total max exposure
        verbose: Print detailed output

    Returns:
        Final PositionTracker with results
    """
    # Setup
    config = BotConfig(
        private_key="simulation",
        funder_address="simulation",
        chain_id=137,
        max_pair_cost=max_pair_cost,
        max_trade_amount=max_trade_amount,
        max_total_exposure=max_exposure,
        target_balance_ratio=1.0,
        min_profit_target=5.0,
        log_level="INFO",
    )

    tracker = PositionTracker()
    engine = ArbitrageEngine(config, tracker)
    market = SimulatedMarket(
        base_price=random.uniform(0.3, 0.7),
        volatility=0.08,
    )

    trades_executed = 0
    opportunities_found = 0

    print(f"\n{Fore.CYAN}Starting Simulation{Style.RESET_ALL}")
    print(f"Max Pair Cost: {max_pair_cost}")
    print(f"Max Trade Amount: ${max_trade_amount}")
    print(f"Max Exposure: ${max_exposure}")
    print("-" * 60)

    for tick in range(num_ticks):
        yes_price, no_price = market.tick()
        market_pair = yes_price + no_price

        # Check for opportunity
        signal = engine.analyze_opportunity(yes_price, no_price)

        if signal and signal.side != TradeSide.NONE:
            opportunities_found += 1

            # Execute trade (simulated)
            if signal.side == TradeSide.YES:
                tracker.add_yes_trade(signal.quantity, signal.price)
            else:
                tracker.add_no_trade(signal.quantity, signal.price)

            trades_executed += 1

            if verbose:
                side_color = Fore.GREEN if signal.side == TradeSide.YES else Fore.MAGENTA
                print(
                    f"[{tick:3d}] {side_color}{signal.side.value:3s}{Style.RESET_ALL} "
                    f"{signal.quantity:6.2f} @ ${signal.price:.3f} | "
                    f"Pair: ${tracker.pair_cost:.4f} | "
                    f"Locked: ${tracker.locked_profit:.2f}"
                )

        # Check if profit is locked
        if tracker.locked_profit >= config.min_profit_target:
            if tracker.balance_ratio >= 0.8:
                if verbose:
                    print(f"\n{Fore.GREEN}Profit locked! Stopping...{Style.RESET_ALL}")
                break

        # Check exposure limit
        if tracker.total_cost >= max_exposure:
            if verbose:
                print(f"\n{Fore.YELLOW}Max exposure reached{Style.RESET_ALL}")
            break

        # Small delay for readability
        if verbose:
            time.sleep(0.05)

    # Final results
    print("\n" + "=" * 60)
    print(f"{Fore.CYAN}SIMULATION RESULTS{Style.RESET_ALL}")
    print("=" * 60)
    tracker.print_status()

    print(f"Ticks processed: {tick + 1}")
    print(f"Opportunities found: {opportunities_found}")
    print(f"Trades executed: {trades_executed}")

    # Simulate market resolution
    yes_wins = random.random() < market.base_price
    if yes_wins:
        final_value = tracker.yes_position.quantity
        outcome = "YES"
    else:
        final_value = tracker.no_position.quantity
        outcome = "NO"

    actual_profit = final_value - tracker.total_cost

    print(f"\n{Fore.YELLOW}Market Resolution: {outcome} wins{Style.RESET_ALL}")
    print(f"Final Value: ${final_value:.2f}")
    print(f"Total Cost: ${tracker.total_cost:.2f}")

    profit_color = Fore.GREEN if actual_profit > 0 else Fore.RED
    print(f"Actual Profit: {profit_color}${actual_profit:.2f}{Style.RESET_ALL}")

    return tracker


def run_multiple_simulations(
    num_simulations: int = 100,
    **kwargs,
) -> dict:
    """
    Run multiple simulations and aggregate results

    Returns statistics about strategy performance
    """
    profits = []
    win_count = 0

    print(f"\n{Fore.CYAN}Running {num_simulations} simulations...{Style.RESET_ALL}\n")

    for i in range(num_simulations):
        # Run simulation quietly
        config = BotConfig(
            private_key="simulation",
            funder_address="simulation",
            chain_id=137,
            max_pair_cost=kwargs.get("max_pair_cost", 0.99),
            max_trade_amount=kwargs.get("max_trade_amount", 10.0),
            max_total_exposure=kwargs.get("max_exposure", 500.0),
            target_balance_ratio=1.0,
            min_profit_target=5.0,
            log_level="WARNING",
        )

        tracker = PositionTracker()
        engine = ArbitrageEngine(config, tracker)
        market = SimulatedMarket(
            base_price=random.uniform(0.3, 0.7),
            volatility=0.08,
        )

        for _ in range(200):
            yes_price, no_price = market.tick()
            signal = engine.analyze_opportunity(yes_price, no_price)

            if signal and signal.side != TradeSide.NONE:
                if signal.side == TradeSide.YES:
                    tracker.add_yes_trade(signal.quantity, signal.price)
                else:
                    tracker.add_no_trade(signal.quantity, signal.price)

            if tracker.total_cost >= config.max_total_exposure:
                break
            if tracker.locked_profit >= config.min_profit_target:
                if tracker.balance_ratio >= 0.8:
                    break

        # Resolve
        yes_wins = random.random() < market.base_price
        final_value = (
            tracker.yes_position.quantity if yes_wins
            else tracker.no_position.quantity
        )
        profit = final_value - tracker.total_cost
        profits.append(profit)

        if profit > 0:
            win_count += 1

        # Progress
        if (i + 1) % 10 == 0:
            print(f"  Completed {i + 1}/{num_simulations}...")

    # Calculate statistics
    avg_profit = sum(profits) / len(profits)
    win_rate = win_count / num_simulations
    max_profit = max(profits)
    min_profit = min(profits)
    total_profit = sum(profits)

    print("\n" + "=" * 60)
    print(f"{Fore.CYAN}AGGREGATE RESULTS ({num_simulations} simulations){Style.RESET_ALL}")
    print("=" * 60)
    print(f"Win Rate: {Fore.GREEN}{win_rate:.1%}{Style.RESET_ALL}")
    print(f"Average Profit: ${avg_profit:.2f}")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Max Profit: ${max_profit:.2f}")
    print(f"Min Profit: ${min_profit:.2f}")
    print("=" * 60)

    return {
        "win_rate": win_rate,
        "avg_profit": avg_profit,
        "total_profit": total_profit,
        "max_profit": max_profit,
        "min_profit": min_profit,
        "profits": profits,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "multi":
        # Run multiple simulations
        run_multiple_simulations(100)
    else:
        # Run single simulation
        run_simulation(verbose=True)
