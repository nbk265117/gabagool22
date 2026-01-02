"""
Configuration module for the Gabagool Arbitrage Bot
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    """Bot configuration settings"""
    # API Configuration
    private_key: str
    funder_address: str
    chain_id: int

    # Trading Parameters
    max_pair_cost: float  # Maximum YES + NO average cost (e.g., 0.99)
    max_trade_amount: float  # Max USDC per single trade
    max_total_exposure: float  # Max total USDC to deploy
    target_balance_ratio: float  # Target YES/NO quantity ratio
    min_profit_target: float  # Minimum profit before stopping

    # Operational
    log_level: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables"""
        return cls(
            private_key=os.getenv("PRIVATE_KEY", ""),
            funder_address=os.getenv("FUNDER_ADDRESS", ""),
            chain_id=int(os.getenv("CHAIN_ID", "137")),
            max_pair_cost=float(os.getenv("MAX_PAIR_COST", "0.99")),
            max_trade_amount=float(os.getenv("MAX_TRADE_AMOUNT", "10")),
            max_total_exposure=float(os.getenv("MAX_TOTAL_EXPOSURE", "1000")),
            target_balance_ratio=float(os.getenv("TARGET_BALANCE_RATIO", "1.0")),
            min_profit_target=float(os.getenv("MIN_PROFIT_TARGET", "5")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    def validate(self) -> bool:
        """Validate configuration"""
        if not self.private_key:
            raise ValueError("PRIVATE_KEY is required")
        if not self.funder_address:
            raise ValueError("FUNDER_ADDRESS is required")
        if self.max_pair_cost >= 1.0:
            raise ValueError("MAX_PAIR_COST must be less than 1.0")
        if self.max_pair_cost < 0.9:
            raise ValueError("MAX_PAIR_COST seems too low, check your config")
        return True


# Polymarket API endpoints
CLOB_API_URL = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# Bitcoin 15-minute market identifiers (these change - need to fetch dynamically)
BTC_MARKET_SLUG = "bitcoin-15-minute"
