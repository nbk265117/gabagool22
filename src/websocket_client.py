"""
WebSocket Client for Real-Time Price Feeds
Critical for low-latency trading

From Reddit: "The window to buy is too short (mostly less than a second)"
"""
import asyncio
import json
import logging
from typing import Callable, Optional
from dataclasses import dataclass

import websockets

logger = logging.getLogger(__name__)

# Polymarket WebSocket endpoint
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass
class PriceUpdate:
    """Real-time price update from WebSocket"""
    token_id: str
    best_bid: float
    best_ask: float
    timestamp: float


class WebSocketClient:
    """
    WebSocket client for real-time Polymarket price feeds

    This is essential for:
    - Sub-second price updates
    - Faster reaction to arbitrage opportunities
    - Reduced API latency vs polling
    """

    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.subscriptions: set[str] = set()
        self.callbacks: list[Callable[[PriceUpdate], None]] = []

    async def connect(self) -> bool:
        """Connect to WebSocket"""
        try:
            self.ws = await websockets.connect(WS_URL)
            self.running = True
            logger.info("Connected to Polymarket WebSocket")
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    async def subscribe(self, token_id: str):
        """Subscribe to price updates for a token"""
        if not self.ws:
            logger.error("WebSocket not connected")
            return

        message = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": [token_id],
        }

        await self.ws.send(json.dumps(message))
        self.subscriptions.add(token_id)
        logger.info(f"Subscribed to {token_id}")

    async def subscribe_market(self, yes_token_id: str, no_token_id: str):
        """Subscribe to both sides of a market"""
        await self.subscribe(yes_token_id)
        await self.subscribe(no_token_id)

    def on_price_update(self, callback: Callable[[PriceUpdate], None]):
        """Register callback for price updates"""
        self.callbacks.append(callback)

    async def listen(self):
        """Listen for price updates"""
        if not self.ws:
            logger.error("WebSocket not connected")
            return

        try:
            async for message in self.ws:
                if not self.running:
                    break

                try:
                    data = json.loads(message)
                    update = self._parse_update(data)
                    if update:
                        for callback in self.callbacks:
                            callback(update)
                except json.JSONDecodeError:
                    logger.debug(f"Invalid JSON: {message}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except websockets.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    def _parse_update(self, data: dict) -> Optional[PriceUpdate]:
        """Parse WebSocket message into PriceUpdate"""
        try:
            # Polymarket WebSocket format varies - adapt as needed
            if data.get("type") == "book":
                return PriceUpdate(
                    token_id=data.get("asset_id", ""),
                    best_bid=float(data.get("bids", [[0]])[0][0]) if data.get("bids") else 0,
                    best_ask=float(data.get("asks", [[0]])[0][0]) if data.get("asks") else 0,
                    timestamp=data.get("timestamp", 0),
                )
        except Exception as e:
            logger.debug(f"Failed to parse update: {e}")
        return None

    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        if self.ws:
            await self.ws.close()
            logger.info("WebSocket disconnected")


class OrderPreSigner:
    """
    Pre-signs orders for faster execution

    From Reddit (@yarumolabs):
    "I create the signatures for my entry and exit prices before hand
    in typescript so I just end up optimizing less than 20ms"

    This class pre-signs orders at multiple price levels so we can
    submit them instantly when opportunities arise.
    """

    def __init__(self, client):
        """
        Args:
            client: PolymarketClient instance
        """
        self.client = client
        self.pre_signed_orders: dict = {}  # {(token_id, price): signed_order}

    def pre_sign_orders(
        self,
        token_id: str,
        prices: list[float],
        quantity: float,
    ):
        """
        Pre-sign orders at multiple price levels

        Args:
            token_id: Token to trade
            prices: List of price levels to pre-sign
            quantity: Quantity for each order
        """
        from py_clob_client.order_builder.constants import BUY
        from py_clob_client.clob_types import OrderArgs

        for price in prices:
            try:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=quantity,
                    side=BUY,
                )
                signed_order = self.client.client.create_order(order_args)
                self.pre_signed_orders[(token_id, price)] = signed_order
                logger.debug(f"Pre-signed order: {token_id} @ ${price}")
            except Exception as e:
                logger.error(f"Failed to pre-sign order: {e}")

    def get_nearest_order(
        self,
        token_id: str,
        target_price: float,
    ) -> Optional[tuple]:
        """
        Get pre-signed order nearest to target price

        Returns:
            (signed_order, actual_price) or None
        """
        best_order = None
        best_diff = float("inf")
        best_price = None

        for (tid, price), order in self.pre_signed_orders.items():
            if tid != token_id:
                continue
            diff = abs(price - target_price)
            if diff < best_diff:
                best_diff = diff
                best_order = order
                best_price = price

        if best_order:
            return best_order, best_price
        return None

    def clear(self):
        """Clear pre-signed orders"""
        self.pre_signed_orders.clear()


async def demo_websocket():
    """Demo WebSocket connection"""
    client = WebSocketClient()

    if await client.connect():
        # Example token IDs - replace with actual
        await client.subscribe("example_yes_token")
        await client.subscribe("example_no_token")

        def on_update(update: PriceUpdate):
            print(f"Price update: {update.token_id} bid={update.best_bid} ask={update.best_ask}")

        client.on_price_update(on_update)

        # Listen for 30 seconds
        try:
            await asyncio.wait_for(client.listen(), timeout=30)
        except asyncio.TimeoutError:
            pass

        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(demo_websocket())
