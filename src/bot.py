"""
Gabagool Arbitrage Bot - Main Entry Point
Replicates the $100k/month Polymarket arbitrage strategy

Strategy:
- Buy YES when YES is cheap (below moving average)
- Buy NO when NO is cheap (below moving average)
- Keep pair cost (avg_YES + avg_NO) < $1.00
- Profit is guaranteed when market resolves

Enhanced with insights from Reddit comments:
- Price analyzer to identify "cheap" vs "rich" prices
- Risk management with stop loss
- Pre-signed orders for faster execution
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

from colorama import init, Fore, Style

from config import BotConfig
from polymarket_client import PolymarketClient
from position_tracker import PositionTracker
from arbitrage_engine import ArbitrageEngine, TradeSide
from market_scanner import MarketScanner, Market
from price_analyzer import PriceAnalyzer, RiskManager

# Initialize colorama for Windows compatibility
init()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log"),
    ]
)
logger = logging.getLogger(__name__)


class GabagoolBot:
    """
    Main arbitrage bot class

    Implements the Gabagool strategy:
    1. Find Bitcoin 15-minute markets
    2. Monitor YES/NO prices with price analyzer
    3. Buy whichever side is cheap (below moving average)
    4. Stop when profit is locked OR risk limits hit
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.client = PolymarketClient(config)
        self.tracker = PositionTracker()
        self.engine = ArbitrageEngine(config, self.tracker)
        self.scanner: Optional[MarketScanner] = None

        # New components from Reddit insights
        self.price_analyzer = PriceAnalyzer(window_size=50)
        self.risk_manager = RiskManager(
            max_loss_per_window=50.0,
            max_drawdown_pct=0.10,
            max_unhedged_exposure=200.0,
        )

        self.running = False
        self.current_market: Optional[Market] = None
        self.session_trades = 0
        self.session_profit = 0.0
        self.windows_traded = 0

    async def start(self):
        """Start the bot"""
        print(self._banner())

        # Validate configuration
        try:
            self.config.validate()
        except ValueError as e:
            logger.error(f"Invalid configuration: {e}")
            return

        # Connect to Polymarket
        if not self.client.connect():
            logger.error("Failed to connect to Polymarket")
            return

        logger.info("Bot initialized successfully")
        self.running = True

        # Main trading loop
        async with MarketScanner() as scanner:
            self.scanner = scanner
            await self._trading_loop()

    async def _trading_loop(self):
        """Main trading loop - finds markets and trades"""
        while self.running:
            try:
                # Find next market
                market = await self.scanner.get_next_market()

                if market is None:
                    logger.info("No active markets found, waiting...")
                    await asyncio.sleep(30)
                    continue

                # Trade this market
                await self._trade_market(market)

                # Reset for next market
                self.tracker.reset()
                self.price_analyzer.reset()
                self.risk_manager.reset()
                self.windows_traded += 1

                await asyncio.sleep(5)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.running = False
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)

    async def _trade_market(self, market: Market):
        """Trade a single market window"""
        self.current_market = market
        logger.info(f"\n{'='*60}")
        logger.info(f"Trading: {market.question}")
        logger.info(f"Time remaining: {market.minutes_remaining:.1f} minutes")
        logger.info(f"Windows traded today: {self.windows_traded}")
        logger.info(f"{'='*60}\n")

        # Set initial capital for risk management
        self.risk_manager.set_initial_capital(self.config.max_total_exposure)

        # Trade until market closes or profit is locked
        while market.minutes_remaining > 0.5:  # Stop 30 seconds before close
            try:
                # Get current prices
                yes_bid, yes_ask = self.client.get_best_prices(market.yes_token_id)
                no_bid, no_ask = self.client.get_best_prices(market.no_token_id)

                if yes_ask is None or no_ask is None:
                    logger.warning("Could not get prices, retrying...")
                    await asyncio.sleep(1)
                    continue

                # Update risk manager
                self.risk_manager.update_exposure(
                    self.tracker.yes_position.quantity,
                    self.tracker.yes_position.total_cost,
                    self.tracker.no_position.quantity,
                    self.tracker.no_position.total_cost,
                    yes_bid or 0,  # Use bid for current value
                    no_bid or 0,
                )

                # Check risk limits
                should_stop, reason = self.risk_manager.should_stop_trading()
                if should_stop:
                    logger.warning(f"{Fore.RED}Risk limit hit: {reason}{Style.RESET_ALL}")
                    break

                # Use price analyzer to find opportunities
                opportunity = self.price_analyzer.get_opportunity(yes_ask, no_ask)

                if opportunity:
                    # Additional check with arbitrage engine
                    signal = self.engine.analyze_opportunity(yes_ask, no_ask)

                    if signal and signal.side != TradeSide.NONE:
                        # Check if we can add position
                        can_add, reason = self.risk_manager.can_add_position(
                            signal.price * signal.quantity,
                            self.tracker.yes_position.quantity,
                            self.tracker.no_position.quantity,
                        )

                        if can_add:
                            await self._execute_trade(signal, market, opportunity)
                        else:
                            logger.debug(f"Skipping trade: {reason}")

                # Print status periodically
                self._print_status(yes_ask, no_ask)

                # Check if profit is locked
                if self.tracker.locked_profit >= self.config.min_profit_target:
                    if self.tracker.balance_ratio >= 0.8:
                        logger.info(
                            f"\n{Fore.GREEN}Profit locked! "
                            f"${self.tracker.locked_profit:.2f}{Style.RESET_ALL}"
                        )
                        self.session_profit += self.tracker.locked_profit
                        break

                # Small delay - but not too long!
                # Reddit insight: "window to buy is too short (< 1 second)"
                await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(f"Error trading market: {e}")
                await asyncio.sleep(1)

        # Market ended - print final status
        self._print_final_status()

    async def _execute_trade(self, signal, market: Market, opportunity: dict):
        """Execute a trade signal"""
        token_id = (
            market.yes_token_id
            if signal.side == TradeSide.YES
            else market.no_token_id
        )

        discount = opportunity.get("discount", 0) * 100
        confidence = opportunity.get("confidence", 0)

        logger.info(
            f"\n{Fore.CYAN}Executing: "
            f"{signal.side.value} {signal.quantity:.2f} @ ${signal.price:.4f} "
            f"(discount: {discount:.1f}%, confidence: {confidence:.2f})"
            f"{Style.RESET_ALL}"
        )

        # Place the order
        result = self.client.place_limit_order(
            token_id=token_id,
            price=signal.price,
            size=signal.quantity,
        )

        if result:
            # Record the trade
            if signal.side == TradeSide.YES:
                self.tracker.add_yes_trade(signal.quantity, signal.price)
            else:
                self.tracker.add_no_trade(signal.quantity, signal.price)

            self.session_trades += 1
            logger.info(f"{Fore.GREEN}Trade executed successfully{Style.RESET_ALL}")
        else:
            logger.warning(f"{Fore.RED}Trade failed{Style.RESET_ALL}")

    def _print_status(self, yes_price: float, no_price: float):
        """Print current status"""
        market_pair = yes_price + no_price
        our_pair = self.tracker.pair_cost

        # Color code based on profitability
        if our_pair < 0.98:
            pair_color = Fore.GREEN
        elif our_pair < 1.0:
            pair_color = Fore.YELLOW
        else:
            pair_color = Fore.RED

        # Get price analyzer stats
        stats = self.price_analyzer.get_stats()

        status = (
            f"YES=${yes_price:.3f} NO=${no_price:.3f} "
            f"(Σ={market_pair:.3f}) | "
            f"Pair: {pair_color}${our_pair:.4f}{Style.RESET_ALL} | "
            f"Locked: ${self.tracker.locked_profit:.2f} | "
            f"Vol: {stats['yes_volatility']:.3f}/{stats['no_volatility']:.3f}"
        )
        print(f"\r{status}", end="", flush=True)

    def _print_final_status(self):
        """Print final status when market ends"""
        print()
        self.tracker.print_status()

        logger.info(f"Session trades: {self.session_trades}")
        logger.info(f"Session profit (locked): ${self.session_profit:.2f}")
        logger.info(f"Current window profit: ${self.tracker.locked_profit:.2f}")

    def _banner(self) -> str:
        """Return ASCII banner"""
        return f"""
{Fore.CYAN}
   ██████╗  █████╗ ██████╗  █████╗  ██████╗  ██████╗  ██████╗ ██╗
  ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔═══██╗██║
  ██║  ███╗███████║██████╔╝███████║██║  ███╗██║   ██║██║   ██║██║
  ██║   ██║██╔══██║██╔══██╗██╔══██║██║   ██║██║   ██║██║   ██║██║
  ╚██████╔╝██║  ██║██████╔╝██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝███████╗
   ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝

  Polymarket Arbitrage Bot - Gabagool Style
  Strategy: Buy both sides cheap, lock profit mathematically

  Enhanced with:
  - Price analyzer (cheap vs rich detection)
  - Risk management (stop loss)
  - Volatility tracking
{Style.RESET_ALL}
        """


async def main():
    """Main entry point"""
    config = BotConfig.from_env()
    bot = GabagoolBot(config)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
