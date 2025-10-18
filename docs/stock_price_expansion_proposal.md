# Stock Price Model Expansion Proposal

## Current State
The `StockPrice` model currently stores minimal data:
- price, previous_close, change, change_percent
- market_state, currency, exchange
- updated_at

## Proposed Expansion

Based on analysis of yfinance data, I propose adding the following fields to create a more comprehensive stock data model:

### Priority 1: Intraday Trading Data (High Value, Update Frequently)
These fields are essential for real-time trading insights and are readily available from yfinance:

```python
# Intraday price range
open: Mapped[float | None]  # Today's opening price
day_high: Mapped[float | None]  # Today's high
day_low: Mapped[float | None]  # Today's low
volume: Mapped[int | None]  # Trading volume today

# Bid/Ask spread (real-time market depth)
bid: Mapped[float | None]  # Current bid price
ask: Mapped[float | None]  # Current ask price
bid_size: Mapped[int | None]  # Bid size
ask_size: Mapped[int | None]  # Ask size
```

**Use cases:**
- Show daily price range in UI
- Calculate volatility metrics
- Display bid-ask spread for active traders
- Volume trending analysis

### Priority 2: Market Capitalization & Volume Metrics (High Value, Update Daily)
Critical for filtering and ranking stocks:

```python
# Market size metrics
market_cap: Mapped[int | None]  # Market capitalization
shares_outstanding: Mapped[int | None]  # Total shares

# Volume metrics
average_volume: Mapped[int | None]  # Average daily volume (3 month)
average_volume_10d: Mapped[int | None]  # 10-day average volume
```

**Use cases:**
- Filter stocks by market cap (large/mid/small cap)
- Identify unusual volume activity
- Calculate liquidity metrics
- Show market cap in stock cards

### Priority 3: 52-Week Range (Medium Value, Update Daily)
Useful for understanding longer-term price action:

```python
# 52-week metrics
fifty_two_week_high: Mapped[float | None]  # 52-week high
fifty_two_week_low: Mapped[float | None]  # 52-week low
fifty_two_week_change_percent: Mapped[float | None]  # % change from 52w low
```

**Use cases:**
- Show "near 52-week high/low" indicators
- Calculate relative strength
- Highlight breakout stocks

### Priority 4: Valuation Metrics (Medium Value, Update Daily)
Essential for fundamental analysis:

```python
# P/E and valuation ratios
pe_ratio: Mapped[float | None]  # Trailing P/E ratio
forward_pe: Mapped[float | None]  # Forward P/E
price_to_book: Mapped[float | None]  # P/B ratio
price_to_sales: Mapped[float | None]  # P/S ratio
peg_ratio: Mapped[float | None]  # PEG ratio
beta: Mapped[float | None]  # Stock beta (volatility)

# Earnings metrics
earnings_per_share: Mapped[float | None]  # EPS (trailing)
book_value: Mapped[float | None]  # Book value per share
```

**Use cases:**
- Value screening (low P/E, P/B)
- Growth screening (PEG ratio)
- Risk assessment (beta)
- Compare valuations across stocks

### Priority 5: Dividend Information (Lower Priority, Update Quarterly)
Important for dividend-focused investors:

```python
# Dividend metrics
dividend_rate: Mapped[float | None]  # Annual dividend rate
dividend_yield: Mapped[float | None]  # Dividend yield %
ex_dividend_date: Mapped[datetime | None]  # Ex-dividend date
payout_ratio: Mapped[float | None]  # Dividend payout ratio
```

**Use cases:**
- Dividend stock screeners
- Income portfolio tracking
- Ex-dividend alerts

### Priority 6: Analyst Coverage (Lower Priority, Update Weekly)
Useful for sentiment and price targets:

```python
# Analyst data
target_mean_price: Mapped[float | None]  # Mean analyst target
target_high_price: Mapped[float | None]  # High target
target_low_price: Mapped[float | None]  # Low target
recommendation_key: Mapped[str | None]  # buy/hold/sell
number_of_analysts: Mapped[int | None]  # Number of analysts
```

**Use cases:**
- Show analyst consensus
- Price target visualization
- Upside/downside potential

### Optional: Company Information (Static, Update Rarely)
Consider storing in a separate `Company` table:

```python
# Company metadata
company_name: Mapped[str | None]  # Full company name
sector: Mapped[str | None]  # Sector
industry: Mapped[str | None]  # Industry
country: Mapped[str | None]  # Country
website: Mapped[str | None]  # Company website
employees: Mapped[int | None]  # Number of employees
```

**Recommendation:** Create a separate `CompanyInfo` table for static data that rarely changes.

## Recommended Implementation Strategy

### Phase 1: Core Trading Data (Immediate - This PR)
Add Priority 1 & 2 fields:
- Intraday trading data (open, high, low, volume, bid/ask)
- Market cap and volume metrics

**Rationale:** High-value, frequently updated, readily available

### Phase 2: Valuation & Range (Next Sprint)
Add Priority 3 & 4 fields:
- 52-week range
- Valuation metrics (P/E, beta, EPS, etc.)

**Rationale:** Important for analysis, but can be added incrementally

### Phase 3: Dividend & Analysts (Future)
Add Priority 5 & 6 fields:
- Dividend information
- Analyst coverage

**Rationale:** Nice-to-have, lower update frequency

### Phase 4: Company Info Table (Future)
Create separate `CompanyInfo` model for static company data

**Rationale:** Separate concerns, avoid bloating StockPrice table

## Database Migration Considerations

1. **Nullable fields:** All new fields should be nullable for backward compatibility
2. **Default values:** Use `None` as default for all new fields
3. **Indexes:** Add indexes on frequently queried fields:
   - `market_cap` (for filtering)
   - `volume` (for sorting)
   - `pe_ratio` (for screening)
4. **Data backfill:** Existing records will have NULL values until next update

## API Impact

The `get_stock_price()` method should be updated to extract and return all new fields from yfinance's `info` dict.

## UI/Feature Opportunities

With expanded data, we can build:
- **Stock screeners:** Filter by market cap, P/E, volume
- **Enhanced stock cards:** Show day range, volume, market cap
- **Price target visualization:** Compare current price to analyst targets
- **Valuation heatmaps:** Compare P/E ratios across sectors
- **Unusual activity alerts:** Detect volume spikes
- **52-week high/low badges:** Highlight breakout stocks

## Storage Impact Estimate

Current row: ~100 bytes
With Priority 1 & 2: ~180 bytes (+80%)
With all priorities: ~250 bytes (+150%)

For 500 stocks: ~125 KB (negligible impact)

## Conclusion

**Immediate Recommendation:** Implement Phase 1 (Priority 1 & 2 fields)

This gives us the most valuable data for minimal complexity:
- Real-time trading insights (volume, range, bid/ask)
- Market cap for filtering and ranking
- Minimal schema changes
- High ROI for feature development

Would you like me to proceed with implementing Phase 1?
