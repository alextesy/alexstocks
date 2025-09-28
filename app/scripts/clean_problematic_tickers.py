"""Remove problematic ticker symbols that are common English words/stop words."""

import logging
from typing import List, Set

from app.db.models import ArticleTicker, Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Common English words that should not be ticker symbols in our context
ENGLISH_STOP_WORDS = {
    # Common words
    'A', 'AN', 'AND', 'ARE', 'AS', 'AT', 'BE', 'BY', 'FOR', 'FROM',
    'HAS', 'HE', 'IN', 'IS', 'IT', 'ITS', 'OF', 'ON', 'THAT', 'THE',
    'TO', 'WAS', 'WILL', 'WITH', 'YOU', 'YOUR', 'THEY', 'THEM', 'THEIR',
    'THIS', 'THAT', 'THESE', 'THOSE', 'WHO', 'WHAT', 'WHERE', 'WHEN',
    'WHY', 'HOW', 'CAN', 'COULD', 'WOULD', 'SHOULD', 'MAY', 'MIGHT',
    'MUST', 'SHALL', 'DO', 'DOES', 'DID', 'HAVE', 'HAD', 'BEEN', 'BEING',
    'BUT', 'OR', 'SO', 'IF', 'THEN', 'ELSE', 'THAN', 'ONLY', 'ALSO',
    'JUST', 'EVEN', 'STILL', 'ALREADY', 'YET', 'NEVER', 'ALWAYS',
    'SOMETIMES', 'OFTEN', 'USUALLY', 'VERY', 'TOO', 'MUCH', 'MANY',
    'MORE', 'MOST', 'LESS', 'LEAST', 'ALL', 'SOME', 'ANY', 'EVERY',
    'EACH', 'BOTH', 'EITHER', 'NEITHER', 'OTHER', 'ANOTHER', 'SUCH',
    'SAME', 'DIFFERENT', 'NEW', 'OLD', 'FIRST', 'LAST', 'NEXT', 'BEST',
    'BETTER', 'GOOD', 'BAD', 'GREAT', 'SMALL', 'BIG', 'LARGE', 'LONG',
    'SHORT', 'HIGH', 'LOW', 'LITTLE', 'FEW', 'SEVERAL', 'MANY', 'MOST',
    
    # Action words that could appear in financial context
    'GET', 'GOT', 'GIVE', 'TAKE', 'MAKE', 'MADE', 'COME', 'CAME', 'GO',
    'WENT', 'KNOW', 'KNEW', 'THINK', 'THOUGHT', 'SEE', 'SAW', 'LOOK',
    'FIND', 'FOUND', 'WORK', 'WORKED', 'PLAY', 'PLAYED', 'TURN', 'TURNED',
    'PUT', 'SET', 'USE', 'USED', 'CALL', 'CALLED', 'ASK', 'ASKED',
    'TELL', 'TOLD', 'HELP', 'HELPED', 'MOVE', 'MOVED', 'TRY', 'TRIED',
    'KEEP', 'KEPT', 'START', 'STARTED', 'STOP', 'STOPPED', 'BRING',
    'BROUGHT', 'SHOW', 'SHOWED', 'FEEL', 'FELT', 'LEAVE', 'LEFT',
    'HEAR', 'HEARD', 'LET', 'MEET', 'MET', 'RUN', 'RAN', 'WALK', 'WALKED',
    'SIT', 'SAT', 'STAND', 'STOOD', 'WIN', 'WON', 'LOSE', 'LOST',
    'SEND', 'SENT', 'BUILD', 'BUILT', 'STAY', 'STAYED', 'FALL', 'FELL',
    'CUT', 'HOLD', 'HELD', 'BREAK', 'BROKE', 'REACH', 'REACHED',
    
    # Time and place words
    'NOW', 'TODAY', 'TOMORROW', 'YESTERDAY', 'SOON', 'LATE', 'EARLY',
    'HERE', 'THERE', 'WHERE', 'EVERYWHERE', 'SOMEWHERE', 'NOWHERE',
    'UP', 'DOWN', 'OVER', 'UNDER', 'ABOVE', 'BELOW', 'INSIDE', 'OUTSIDE',
    'NEAR', 'FAR', 'CLOSE', 'AWAY', 'BACK', 'FRONT', 'AROUND', 'THROUGH',
    'ACROSS', 'BETWEEN', 'AMONG', 'DURING', 'BEFORE', 'AFTER', 'SINCE',
    'UNTIL', 'WHILE', 'WITHIN', 'WITHOUT', 'BEYOND', 'TOWARD', 'TOWARDS',
    
    # Question words and responses
    'YES', 'NO', 'OK', 'OKAY', 'WELL', 'SURE', 'MAYBE', 'PERHAPS',
    'PROBABLY', 'DEFINITELY', 'CERTAINLY', 'ABSOLUTELY', 'EXACTLY',
    'REALLY', 'ACTUALLY', 'INDEED', 'QUITE', 'RATHER', 'PRETTY',
    'ENOUGH', 'ALMOST', 'NEARLY', 'HARDLY', 'BARELY', 'SIMPLY',
    'CLEARLY', 'OBVIOUSLY', 'APPARENTLY', 'UNFORTUNATELY', 'HOPEFULLY',
    
    # Numbers and quantities (written out)
    'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT',
    'NINE', 'TEN', 'HUNDRED', 'THOUSAND', 'MILLION', 'BILLION',
    
    # Common exclamations
    'OH', 'AH', 'WOW', 'HEY', 'HI', 'HELLO', 'BYE', 'GOODBYE', 'THANKS',
    'PLEASE', 'SORRY', 'EXCUSE', 'PARDON',
    
    # Other common problematic words seen in financial discussions
    'MONEY', 'CASH', 'BANK', 'LOAN', 'DEBT', 'FUND', 'FUNDS', 'STOCK',
    'STOCKS', 'SHARE', 'SHARES', 'PRICE', 'COST', 'VALUE', 'WORTH',
    'PROFIT', 'LOSS', 'GAIN', 'TRADE', 'TRADING', 'MARKET', 'MARKETS',
    'INVEST', 'INVESTOR', 'COMPANY', 'BUSINESS', 'FINANCIAL', 'ECONOMY',
    'SELL', 'SELLING', 'BUY', 'BUYING', 'LONG', 'SHORT', 'BULL', 'BEAR',
    'PORTFOLIO', 'DIVIDEND', 'EARNINGS', 'REVENUE', 'GROWTH', 'RETURN',
    
    # Social media and internet slang
    'LOL', 'OMG', 'WTF', 'LMAO', 'ROFL', 'IMO', 'IMHO', 'TBH', 'FWIW',
    'BTW', 'FYI', 'ASAP', 'FAQ', 'DIY', 'CEO', 'CFO', 'CTO', 'HR',
    
    # Days of week, months (abbreviated)
    'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN',
    'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
    
    # Common abbreviations that might be tickers
    'USA', 'CEO', 'CFO', 'CTO', 'COO', 'CIO', 'CMO', 'HR', 'IT', 'PR',
    'IPO', 'SEC', 'FDA', 'EPA', 'IRS', 'FBI', 'CIA', 'NSA', 'DOJ',
    'NATO', 'UN', 'EU', 'UK', 'US', 'TV', 'PC', 'AI', 'VR', 'AR',
    'GPS', 'USB', 'CPU', 'GPU', 'RAM', 'SSD', 'HDD', 'OS', 'APP',
    'PDF', 'URL', 'HTML', 'CSS', 'SQL', 'API', 'SDK', 'IDE',
    
    # Units and measurements
    'MM', 'CM', 'KM', 'KG', 'LB', 'OZ', 'FT', 'IN', 'YD', 'MI',
    'HR', 'MIN', 'SEC', 'AM', 'PM', 'EST', 'PST', 'GMT', 'UTC',
    
    # Colors (sometimes used as tickers)
    'RED', 'BLUE', 'GREEN', 'YELLOW', 'BLACK', 'WHITE', 'GRAY', 'GREY',
    'PINK', 'PURPLE', 'ORANGE', 'BROWN', 'GOLD', 'SILVER',
    
    # Direction and position words
    'NORTH', 'SOUTH', 'EAST', 'WEST', 'LEFT', 'RIGHT', 'CENTER', 'MIDDLE',
    'TOP', 'BOTTOM', 'SIDE', 'CORNER', 'EDGE', 'END', 'BEGIN', 'START',
    
    # Size and comparison
    'HUGE', 'TINY', 'GIANT', 'MINI', 'MICRO', 'MEGA', 'SUPER', 'ULTRA',
    'MAXIMUM', 'MINIMUM', 'AVERAGE', 'NORMAL', 'STANDARD', 'BASIC',
    'PREMIUM', 'DELUXE', 'SPECIAL', 'REGULAR', 'EXTRA', 'PLUS',
    
    # Internet/tech terms that might be problematic
    'LINK', 'CLICK', 'BROWSE', 'SEARCH', 'FIND', 'SAVE', 'LOAD', 'DOWNLOAD',
    'UPLOAD', 'SHARE', 'LIKE', 'FOLLOW', 'SUBSCRIBE', 'COMMENT', 'POST',
    'EMAIL', 'TEXT', 'MESSAGE', 'CHAT', 'CALL', 'VIDEO', 'PHOTO', 'IMAGE',
    
    # Emotions and reactions
    'LOVE', 'HATE', 'LIKE', 'DISLIKE', 'HAPPY', 'SAD', 'ANGRY', 'MAD',
    'EXCITED', 'BORED', 'TIRED', 'CONFUSED', 'SURPRISED', 'SHOCKED',
    'WORRIED', 'SCARED', 'CALM', 'RELAXED', 'STRESSED', 'NERVOUS'
}

# Additional single-letter tickers that are too ambiguous
AMBIGUOUS_SINGLE_LETTERS = {
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
}

# Keep some important single-letter tickers (adjust as needed)
IMPORTANT_SINGLE_LETTERS = {
    'V',   # Visa - too important to remove
    'T',   # AT&T - major telecom
    'F',   # Ford - major automaker
    'C',   # Citigroup - major bank
    'X',   # United States Steel
}

# Important words that are also legitimate company tickers (don't remove these)
IMPORTANT_WORD_TICKERS = {
    'COST',  # Costco - S&P 500
    'LOW',   # Lowe's - S&P 500  
    'ALL',   # Allstate - S&P 500
    'ARE',   # Alexandria Real Estate - S&P 500
    'NOW',   # ServiceNow - major tech company
    'APP',   # AppLovin - major mobile advertising
    'WORK',  # Slack/Salesforce - major enterprise software
    'SHOP',  # Shopify - major e-commerce
    'TEAM',  # Atlassian - major software
    'LOVE',  # Lovesac - furniture company
    'PLAY',  # Dave & Buster's - entertainment
    'HOPE',  # Hope Bancorp - bank
    'SAFE',  # Safehold - REIT
    'GROW',  # U.S. Global Investors - investment company
    'CALM',  # Cal-Maine Foods - food producer
    'HEAR',  # Turtle Beach - gaming accessories
    'REAL',  # The RealReal - luxury consignment
    'TRUE',  # TrueCar - automotive
    'GOOD',  # Gladstone Commercial - REIT
    'WELL',  # Welltower - healthcare REIT
    'FAST',  # Fastenal - industrial supplies
    'FREE',  # Whole Earth Brands - food company
    'NICE',  # NICE Ltd. - software
    'SMART', # SmartFinancial - bank
    'SAVE',  # Spirit Airlines - airline
    'WIN',   # Windstream Holdings - telecom
    'GOLD',  # Barrick Gold - mining (though this might conflict)
    'CASH',  # Meta Financial Group - financial
}

# Two-letter combinations that are too common
COMMON_TWO_LETTER = {
    'AM', 'PM', 'TV', 'PC', 'AI', 'IT', 'OR', 'AN', 'AS', 'AT', 'BE',
    'BY', 'DO', 'GO', 'HE', 'IF', 'IN', 'IS', 'IT', 'MY', 'NO', 'OF',
    'ON', 'OR', 'SO', 'TO', 'UP', 'US', 'WE'
}

class TickerCleaner:
    """Clean problematic tickers from the database."""
    
    def __init__(self):
        self.db = SessionLocal()
        self.removed_tickers = []
        self.kept_tickers = []
    
    def identify_problematic_tickers(self) -> List[str]:
        """Identify tickers that are problematic common words."""
        problematic = []
        
        # Get all ticker symbols
        all_tickers = self.db.query(Ticker.symbol).all()
        
        for (symbol,) in all_tickers:
            symbol_upper = symbol.upper()
            
            # Skip important word tickers
            if symbol_upper in IMPORTANT_WORD_TICKERS:
                continue
            
            # Check against stop words
            if symbol_upper in ENGLISH_STOP_WORDS:
                problematic.append(symbol)
                continue
            
            # Check single letters (except important ones)
            if (len(symbol) == 1 and 
                symbol_upper in AMBIGUOUS_SINGLE_LETTERS and 
                symbol_upper not in IMPORTANT_SINGLE_LETTERS):
                problematic.append(symbol)
                continue
            
            # Check common two-letter words
            if len(symbol) == 2 and symbol_upper in COMMON_TWO_LETTER:
                problematic.append(symbol)
                continue
        
        return problematic
    
    def analyze_ticker_usage(self, symbols: List[str]) -> dict:
        """Analyze how many articles each ticker is linked to."""
        usage_stats = {}
        
        for symbol in symbols:
            # Count article links
            link_count = (
                self.db.query(ArticleTicker)
                .filter(ArticleTicker.ticker == symbol)
                .count()
            )
            
            # Get ticker info
            ticker = self.db.query(Ticker).filter(Ticker.symbol == symbol).first()
            
            usage_stats[symbol] = {
                'link_count': link_count,
                'name': ticker.name if ticker else 'Unknown',
                'exchange': ticker.exchange if ticker else 'Unknown',
                'is_sp500': ticker.is_sp500 if ticker else False,
                'sources': ticker.sources if ticker else []
            }
        
        return usage_stats
    
    def remove_problematic_tickers(self, symbols_to_remove: List[str], confirm: bool = True) -> dict:
        """Remove problematic tickers from the database."""
        if confirm:
            print(f"\nWARNING: This will remove {len(symbols_to_remove)} tickers and all their article links!")
            print("Tickers to remove:", ', '.join(sorted(symbols_to_remove[:20])))
            if len(symbols_to_remove) > 20:
                print(f"... and {len(symbols_to_remove) - 20} more")
            
            response = input("\nProceed with removal? (y/N): ").strip().lower()
            if response != 'y':
                print("Removal cancelled.")
                return {'removed': 0, 'errors': []}
        
        removed_count = 0
        errors = []
        
        for symbol in symbols_to_remove:
            try:
                # Remove article links first
                article_links = (
                    self.db.query(ArticleTicker)
                    .filter(ArticleTicker.ticker == symbol)
                    .all()
                )
                
                for link in article_links:
                    self.db.delete(link)
                
                # Remove ticker
                ticker = self.db.query(Ticker).filter(Ticker.symbol == symbol).first()
                if ticker:
                    self.db.delete(ticker)
                    removed_count += 1
                    self.removed_tickers.append(symbol)
                
                # Commit after each ticker to avoid large transactions
                self.db.commit()
                
            except Exception as e:
                error_msg = f"Failed to remove {symbol}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
                self.db.rollback()
        
        return {'removed': removed_count, 'errors': errors}
    
    def print_analysis(self, problematic_tickers: List[str], usage_stats: dict):
        """Print analysis of problematic tickers."""
        print(f"\n{'='*80}")
        print("PROBLEMATIC TICKER ANALYSIS")
        print(f"{'='*80}")
        
        print(f"Total problematic tickers found: {len(problematic_tickers)}")
        
        # Sort by usage (most linked first)
        sorted_tickers = sorted(
            problematic_tickers,
            key=lambda x: usage_stats.get(x, {}).get('link_count', 0),
            reverse=True
        )
        
        # Show top used problematic tickers
        print(f"\nTop 20 most-linked problematic tickers:")
        print(f"{'Symbol':<8} {'Links':<8} {'S&P500':<8} {'Name':<40}")
        print("-" * 80)
        
        for symbol in sorted_tickers[:20]:
            stats = usage_stats.get(symbol, {})
            sp500_flag = "✓" if stats.get('is_sp500', False) else ""
            name = stats.get('name', 'Unknown')[:38]
            links = stats.get('link_count', 0)
            
            print(f"{symbol:<8} {links:<8} {sp500_flag:<8} {name:<40}")
        
        # Show summary by categories
        stop_words = [s for s in problematic_tickers if s.upper() in ENGLISH_STOP_WORDS]
        single_letters = [s for s in problematic_tickers if len(s) == 1]
        two_letters = [s for s in problematic_tickers if len(s) == 2 and s.upper() in COMMON_TWO_LETTER]
        
        print(f"\nBreakdown:")
        print(f"  Stop words: {len(stop_words)}")
        print(f"  Single letters: {len(single_letters)}")
        print(f"  Common two-letter: {len(two_letters)}")
        
        # Calculate total impact
        total_links = sum(usage_stats.get(s, {}).get('link_count', 0) for s in problematic_tickers)
        sp500_count = sum(1 for s in problematic_tickers if usage_stats.get(s, {}).get('is_sp500', False))
        
        print(f"\nImpact:")
        print(f"  Total article links to be removed: {total_links:,}")
        print(f"  S&P 500 tickers affected: {sp500_count}")
    
    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Check for command line arguments
    remove_flag = len(sys.argv) > 1 and sys.argv[1] == '--remove'
    
    cleaner = TickerCleaner()
    
    try:
        print("Analyzing ticker database for problematic symbols...")
        
        # Find problematic tickers
        problematic_tickers = cleaner.identify_problematic_tickers()
        
        if not problematic_tickers:
            print("✅ No problematic tickers found!")
            return
        
        # Analyze usage
        usage_stats = cleaner.analyze_ticker_usage(problematic_tickers)
        
        # Print analysis
        cleaner.print_analysis(problematic_tickers, usage_stats)
        
        if remove_flag:
            print(f"\n🔄 Removing {len(problematic_tickers)} problematic tickers...")
            result = cleaner.remove_problematic_tickers(problematic_tickers, confirm=False)
            
            print(f"\n✅ Removed {result['removed']} problematic tickers")
            
            if result['errors']:
                print(f"❌ {len(result['errors'])} errors occurred:")
                for error in result['errors']:
                    print(f"  {error}")
            
            # Show final stats
            remaining_tickers = cleaner.db.query(Ticker).count()
            print(f"\nFinal ticker count: {remaining_tickers:,}")
        else:
            print(f"\nFound {len(problematic_tickers)} problematic tickers.")
            print("To remove them, run: python clean_problematic_tickers.py --remove")
    
    finally:
        cleaner.close()


if __name__ == "__main__":
    main()
