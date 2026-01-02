"""
Market Scanner for the Gabagool Bot
Finds and monitors Bitcoin 15-minute prediction markets
"""
import logging
import aiohttp
import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import GAMMA_API_URL

logger = logging.getLogger(__name__)


@dataclass
class Market:
    """Represents a Polymarket market"""
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    end_time: datetime
    volume: float
    liquidity: float

    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - datetime.now()

    @property
    def minutes_remaining(self) -> float:
        return self.time_remaining.total_seconds() / 60


class MarketScanner:
    """Scans for and monitors Bitcoin 15-minute markets"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_market: Optional[Market] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def find_btc_15min_markets(self) -> list[Market]:
        """
        Find active Bitcoin 15-minute prediction markets

        Returns list of markets sorted by end time
        """
        try:
            # Query Gamma API for Bitcoin markets
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100,
            }

            async with self.session.get(
                f"{GAMMA_API_URL}/markets",
                params=params,
            ) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch markets: {response.status}")
                    return []

                data = await response.json()

            # Filter for Bitcoin 15-minute markets
            btc_markets = []
            for market in data:
                question = market.get("question", "").lower()
                # Look for Bitcoin/BTC 15-minute markets
                if ("bitcoin" in question or "btc" in question) and "15" in question:
                    try:
                        # Parse market data
                        tokens = market.get("tokens", [])
                        yes_token = next(
                            (t for t in tokens if t.get("outcome") == "Yes"),
                            None
                        )
                        no_token = next(
                            (t for t in tokens if t.get("outcome") == "No"),
                            None
                        )

                        if not yes_token or not no_token:
                            continue

                        end_time_str = market.get("endDate")
                        if end_time_str:
                            end_time = datetime.fromisoformat(
                                end_time_str.replace("Z", "+00:00")
                            )
                        else:
                            continue

                        btc_markets.append(Market(
                            condition_id=market.get("conditionId"),
                            question=market.get("question"),
                            yes_token_id=yes_token.get("token_id"),
                            no_token_id=no_token.get("token_id"),
                            end_time=end_time,
                            volume=float(market.get("volume", 0)),
                            liquidity=float(market.get("liquidity", 0)),
                        ))
                    except Exception as e:
                        logger.debug(f"Error parsing market: {e}")
                        continue

            # Sort by end time (soonest first)
            btc_markets.sort(key=lambda m: m.end_time)
            return btc_markets

        except Exception as e:
            logger.error(f"Error scanning markets: {e}")
            return []

    async def get_next_market(self) -> Optional[Market]:
        """Get the next active market to trade"""
        markets = await self.find_btc_15min_markets()

        # Find a market with at least 2 minutes remaining
        for market in markets:
            if market.minutes_remaining > 2:
                return market

        return None

    async def wait_for_market(self, timeout_minutes: int = 30) -> Optional[Market]:
        """Wait for a new market to become available"""
        logger.info("Waiting for next market...")

        start_time = datetime.now()
        timeout = timedelta(minutes=timeout_minutes)

        while datetime.now() - start_time < timeout:
            market = await self.get_next_market()
            if market:
                logger.info(f"Found market: {market.question}")
                return market

            # Wait before checking again
            await asyncio.sleep(10)

        logger.warning("Timeout waiting for market")
        return None


async def scan_markets_demo():
    """Demo function to scan and display markets"""
    async with MarketScanner() as scanner:
        markets = await scanner.find_btc_15min_markets()

        print(f"\nFound {len(markets)} Bitcoin 15-min markets:\n")
        for market in markets[:5]:
            print(f"  {market.question}")
            print(f"    Condition ID: {market.condition_id}")
            print(f"    YES Token: {market.yes_token_id}")
            print(f"    NO Token: {market.no_token_id}")
            print(f"    Time Remaining: {market.minutes_remaining:.1f} min")
            print(f"    Volume: ${market.volume:,.0f}")
            print()


if __name__ == "__main__":
    asyncio.run(scan_markets_demo())
