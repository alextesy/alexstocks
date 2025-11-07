# Analytics Queries

This directory contains SQL queries for data analysis and reporting on the Market Pulse database.

## Queries

### `tickers_per_day_with_more_than_10_articles.sql`
Counts how many tickers per day have more than 10 articles associated with them.

**Note:** This query excludes ETFs (tickers with "ETF" in their name).

**Usage:**
```bash
psql -d your_database -f analytics/tickers_per_day_with_more_than_10_articles.sql
```

**Output:**
- `article_date`: The date of the articles
- `tickers_with_more_than_10_articles`: Count of distinct tickers (excluding ETFs) with more than 10 articles on that date

### `etf_article_counts.sql`
Lists all ETFs with their total article counts, sorted by article count (highest first).

**Usage:**
```bash
psql -d your_database -f analytics/etf_article_counts.sql
```

**Output:**
- `symbol`: The ETF ticker symbol
- `name`: The full name of the ETF
- `total_article_count`: Total number of articles associated with this ETF

**Note:** The main query shows all ETFs (including those with 0 articles). An alternative query is provided (commented) that only shows ETFs with at least one article.

## Adding New Queries

When adding new analytics queries:
1. Use descriptive filenames that clearly indicate what the query does
2. Include comments explaining the query's purpose
3. Add a brief description to this README
4. Test queries on a development database before running on production

