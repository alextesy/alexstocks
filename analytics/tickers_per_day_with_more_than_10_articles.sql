-- Query to count how many tickers per day have more than 10 articles associated with them
-- Excludes ETFs (tickers with "ETF" in their name)
-- This is the main query you requested
WITH ticker_daily_counts AS (
    SELECT 
        DATE(article.published_at) AS article_date,
        article_ticker.ticker,
        COUNT(*) AS article_count
    FROM 
        article_ticker
        INNER JOIN article ON article_ticker.article_id = article.id
        INNER JOIN ticker ON article_ticker.ticker = ticker.symbol
    WHERE 
        UPPER(ticker.name) NOT LIKE '%ETF%'
    GROUP BY 
        DATE(article.published_at),
        article_ticker.ticker
    HAVING 
        COUNT(*) > 10
)
SELECT 
    article_date,
    COUNT(DISTINCT ticker) AS tickers_with_more_than_10_articles
FROM 
    ticker_daily_counts
GROUP BY 
    article_date
ORDER BY 
    article_date DESC;

-- Alternative query: Shows the actual tickers per day with their article counts
-- Uncomment if you want to see which specific tickers have >10 articles each day
/*
SELECT 
    DATE(article.published_at) AS article_date,
    article_ticker.ticker,
    COUNT(*) AS article_count
FROM 
    article_ticker
    INNER JOIN article ON article_ticker.article_id = article.id
    INNER JOIN ticker ON article_ticker.ticker = ticker.symbol
WHERE 
    UPPER(ticker.name) NOT LIKE '%ETF%'
GROUP BY 
    DATE(article.published_at),
    article_ticker.ticker
HAVING 
    COUNT(*) > 10
ORDER BY 
    article_date DESC,
    article_count DESC;
*/

