# Gabagool22 - Polymarket Arbitrage Bot

Replication of the famous Gabagool trading strategy that generates $100k+/month on Polymarket through mathematical arbitrage on Bitcoin 15-minute prediction markets.

## Strategy Overview

The strategy exploits pricing inefficiencies in binary prediction markets:

1. **Buy both YES and NO** at different times when each side becomes temporarily cheap
2. **Keep pair cost < $1.00**: `avg_YES + avg_NO < 1.00`
3. **Guaranteed profit**: One side always pays $1, so if you paid less than $1 for the pair, you profit

### Example

```
Buy YES: 1,266 shares @ $0.517 = $655
Buy NO:  1,294 shares @ $0.449 = $581
────────────────────────────────────
Total Cost: $1,236
Pair Cost: $0.517 + $0.449 = $0.966

If YES wins → Get $1,266 → Profit: $30
If NO wins  → Get $1,294 → Profit: $58
```

**No prediction needed - profit is mathematically locked.**

## Project Structure

```
gabagool22/
├── src/
│   ├── bot.py              # Main bot entry point
│   ├── config.py           # Configuration management
│   ├── polymarket_client.py # Polymarket API client
│   ├── position_tracker.py  # Position tracking & pair cost calculation
│   ├── arbitrage_engine.py  # Core arbitrage logic
│   ├── market_scanner.py    # Find Bitcoin 15-min markets
│   └── simulator.py         # Strategy simulator (no real money)
├── logs/                    # Bot logs
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
└── README.md
```

## Installation

```bash
# Clone the repository
git clone https://github.com/nbk265117/gabagool22.git
cd gabagool22

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Edit `.env` with your settings:

```bash
# Required: Your Ethereum private key (from Polymarket wallet)
PRIVATE_KEY=your_private_key_here

# Required: Your funder address (wallet holding USDC on Polymarket)
FUNDER_ADDRESS=0x...

# Strategy Parameters
MAX_PAIR_COST=0.99      # Max acceptable pair cost (0.99 = 1% profit margin)
MAX_TRADE_AMOUNT=10     # Max USDC per single trade
MAX_TOTAL_EXPOSURE=1000 # Max total USDC to deploy per market
MIN_PROFIT_TARGET=5     # Min profit before stopping
```

## Usage

### Run Simulation (Recommended First)

Test the strategy without real money:

```bash
cd src

# Single simulation with detailed output
python simulator.py

# Run 100 simulations for statistics
python simulator.py multi
```

### Run Live Bot

```bash
cd src
python bot.py
```

The bot will:
1. Scan for active Bitcoin 15-minute markets
2. Monitor YES/NO prices in real-time
3. Buy whichever side is cheap
4. Stop when profit is locked or market ends

## Key Metrics

| Metric | Description |
|--------|-------------|
| **Pair Cost** | `avg_YES + avg_NO` - must be < 1.0 for profit |
| **Locked Profit** | Guaranteed profit based on balanced positions |
| **Balance Ratio** | How balanced YES/NO positions are (1.0 = perfect) |

## Risk Disclaimer

- This bot trades real money on Polymarket
- Past performance does not guarantee future results
- The strategy requires fast execution - you're competing with other bots
- Always test with small amounts first
- Never invest more than you can afford to lose

## Technical Notes

### Latency
- Polymarket servers: `eu-west-2` (~15-17ms but blocked for most)
- Usable regions: `eu-west-1`, `eu-west-4` (~22ms)
- Order placement: ~60-70ms typical

### API Limits
- Opportunities appear ~25-50 times per 15-min window
- Each window allows ~20 shares fill before market moves
- Must be faster than competing bots

## Credits

Strategy based on analysis of [@gabagool22](https://polymarket.com/@gabagool22) on Polymarket.

Original Reddit post: [Inside the Mind of a Polymarket BOT: $100k/month Strategy Explained](https://www.reddit.com/r/PredictionsMarkets/comments/1phgdzd/)

## License

MIT License - Use at your own risk.
