-- Query to list all ETFs with their total article counts
-- Shows ETFs sorted by article count (highest first)
SELECT 
    ticker.symbol,
    ticker.name,
    COUNT(article_ticker.article_id) AS total_article_count
FROM 
    ticker
    LEFT JOIN article_ticker ON ticker.symbol = article_ticker.ticker
WHERE 
    UPPER(ticker.name) LIKE '%ETF%'
GROUP BY 
    ticker.symbol,
    ticker.name
ORDER BY 
    total_article_count DESC,
    ticker.symbol ASC;

-- Alternative: Only show ETFs that have at least one article
-- Uncomment to use this version instead
/*
SELECT 
    ticker.symbol,
    ticker.name,
    COUNT(article_ticker.article_id) AS total_article_count
FROM 
    ticker
    INNER JOIN article_ticker ON ticker.symbol = article_ticker.ticker
WHERE 
    UPPER(ticker.name) LIKE '%ETF%'
GROUP BY 
    ticker.symbol,
    ticker.name
HAVING 
    COUNT(article_ticker.article_id) > 0
ORDER BY 
    total_article_count DESC,
    ticker.symbol ASC;
*/

