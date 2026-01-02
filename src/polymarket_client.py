"""
Polymarket API Client for the Gabagool Arbitrage Bot
Handles connection to CLOB and market data fetching
"""
import logging
from typing import Optional
from decimal import Decimal

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

from config import BotConfig, CLOB_API_URL

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Client for interacting with Polymarket CLOB API"""

    def __init__(self, config: BotConfig):
        self.config = config
        self.client: Optional[ClobClient] = None
        self.api_creds: Optional[ApiCreds] = None

    def connect(self) -> bool:
        """Initialize connection to Polymarket CLOB"""
        try:
            # Initialize client with credentials
            self.client = ClobClient(
                CLOB_API_URL,
                key=self.config.private_key,
                chain_id=self.config.chain_id,
                funder=self.config.funder_address,
            )

            # Derive API credentials from private key
            self.api_creds = self.client.derive_api_creds()
            self.client.set_api_creds(self.api_creds)

            logger.info("Connected to Polymarket CLOB API")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            return False

    def get_market(self, condition_id: str) -> Optional[dict]:
        """Get market information by condition ID"""
        try:
            return self.client.get_market(condition_id)
        except Exception as e:
            logger.error(f"Failed to get market {condition_id}: {e}")
            return None

    def get_orderbook(self, token_id: str) -> Optional[dict]:
        """Get orderbook for a specific token (YES or NO)"""
        try:
            return self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Failed to get orderbook for {token_id}: {e}")
            return None

    def get_best_prices(self, token_id: str) -> tuple[Optional[float], Optional[float]]:
        """
        Get best bid and ask prices for a token
        Returns (best_bid, best_ask)
        """
        try:
            orderbook = self.get_orderbook(token_id)
            if not orderbook:
                return None, None

            best_bid = None
            best_ask = None

            if orderbook.get("bids") and len(orderbook["bids"]) > 0:
                best_bid = float(orderbook["bids"][0]["price"])

            if orderbook.get("asks") and len(orderbook["asks"]) > 0:
                best_ask = float(orderbook["asks"][0]["price"])

            return best_bid, best_ask

        except Exception as e:
            logger.error(f"Failed to get best prices: {e}")
            return None, None

    def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """Get midpoint price for a token"""
        try:
            midpoint = self.client.get_midpoint(token_id)
            return float(midpoint) if midpoint else None
        except Exception as e:
            logger.error(f"Failed to get midpoint price: {e}")
            return None

    def place_limit_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str = BUY,
    ) -> Optional[dict]:
        """
        Place a limit order

        Args:
            token_id: The token to trade (YES or NO token ID)
            price: Price in USDC (0.01 to 0.99)
            size: Number of shares to buy
            side: BUY or SELL

        Returns:
            Order response or None if failed
        """
        try:
            # Build order arguments
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
            )

            # Create and sign the order
            signed_order = self.client.create_order(order_args)

            # Submit the order
            response = self.client.post_order(signed_order, OrderType.GTC)

            logger.info(f"Order placed: {size} shares @ ${price} - {response}")
            return response

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None

    def place_market_order(
        self,
        token_id: str,
        amount: float,
    ) -> Optional[dict]:
        """
        Place a market order (aggressive limit order)

        Args:
            token_id: The token to trade
            amount: Amount in USDC to spend

        Returns:
            Order response or None if failed
        """
        try:
            # Get best ask price and add slippage
            _, best_ask = self.get_best_prices(token_id)
            if not best_ask:
                logger.error("No ask price available for market order")
                return None

            # Add 1% slippage for market order
            price = min(best_ask * 1.01, 0.99)
            size = amount / price

            return self.place_limit_order(token_id, price, size, BUY)

        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            self.client.cancel(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        try:
            self.client.cancel_all()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    def get_balance(self) -> Optional[float]:
        """Get USDC balance"""
        try:
            # This would need to query the blockchain or use Polymarket's balance API
            # For now, return None as this requires additional setup
            return None
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None
