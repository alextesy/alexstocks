#!/usr/bin/env python3
"""Clean up problematic ticker aliases that cause false positives."""

import logging
from typing import Set

from app.db.session import get_db
from app.db.models import Ticker

logger = logging.getLogger(__name__)

# Common English words that should not be ticker aliases
PROBLEMATIC_ALIASES: Set[str] = {
    # Single letters
    'a', 'i', 'o',
    
    # Common two-letter words
    'it', 'go', 'do', 'so', 'no', 'up', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'be', 'or', 'we', 'he', 'me', 'my', 'us', 'am', 'an', 'if', 'by', 'hi', 'ok', 'oh', 'ah', 'eh', 'uh', 'yo',
    
    # Common three-letter words
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'man', 'men', 'put', 'say', 'she', 'too', 'use', 'war', 'win', 'won', 'yes', 'yet', 'big', 'buy', 'car', 'cut', 'end', 'far', 'few', 'got', 'hit', 'hot', 'let', 'lot', 'low', 'own', 'run', 'set', 'sit', 'sun', 'top', 'try', 'why', 'bad', 'bag', 'bed', 'bit', 'box', 'bus', 'cat', 'cup', 'dog', 'ear', 'eat', 'egg', 'eye', 'fly', 'fun', 'gun', 'hat', 'job', 'key', 'kid', 'leg', 'lie', 'log', 'map', 'mix', 'net', 'oil', 'pay', 'pen', 'pie', 'pig', 'pot', 'red', 'row', 'sea', 'six', 'sky', 'son', 'tax', 'tea', 'ten', 'tie', 'toy', 'use', 'van', 'web', 'win', 'yes', 'yet', 'zip', 'zoo',
    
    # Common four-letter words
    'this', 'that', 'with', 'have', 'will', 'your', 'from', 'they', 'know', 'want', 'been', 'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well', 'were', 'what', 'year', 'work', 'back', 'call', 'came', 'each', 'even', 'find', 'give', 'hand', 'help', 'keep', 'kind', 'last', 'late', 'left', 'life', 'line', 'live', 'look', 'made', 'move', 'name', 'need', 'next', 'only', 'open', 'part', 'play', 'put', 'read', 'right', 'said', 'same', 'seem', 'show', 'side', 'tell', 'turn', 'used', 'want', 'week', 'went', 'were', 'what', 'when', 'will', 'with', 'word', 'work', 'year', 'your', 'able', 'area', 'away', 'back', 'ball', 'bank', 'base', 'beat', 'been', 'best', 'bill', 'blue', 'book', 'both', 'call', 'came', 'card', 'care', 'case', 'cash', 'city', 'cold', 'come', 'cost', 'data', 'deal', 'deep', 'door', 'down', 'draw', 'drop', 'each', 'east', 'easy', 'edge', 'else', 'even', 'ever', 'face', 'fact', 'fall', 'fast', 'feel', 'feet', 'fell', 'felt', 'find', 'fine', 'fire', 'firm', 'fish', 'five', 'flat', 'flow', 'food', 'foot', 'form', 'four', 'free', 'full', 'game', 'gave', 'girl', 'give', 'goal', 'gone', 'good', 'grew', 'grow', 'hand', 'hard', 'head', 'hear', 'heat', 'held', 'help', 'here', 'high', 'hill', 'hold', 'home', 'hope', 'hour', 'idea', 'keep', 'kept', 'kill', 'kind', 'knew', 'know', 'land', 'last', 'late', 'lead', 'left', 'less', 'life', 'lift', 'line', 'link', 'list', 'live', 'load', 'loan', 'lock', 'long', 'look', 'lost', 'love', 'made', 'mail', 'main', 'make', 'male', 'many', 'mark', 'mass', 'mind', 'mine', 'miss', 'move', 'much', 'must', 'name', 'near', 'need', 'news', 'next', 'nice', 'nine', 'none', 'nose', 'note', 'okay', 'once', 'only', 'open', 'oral', 'over', 'page', 'paid', 'pair', 'park', 'part', 'pass', 'past', 'path', 'peak', 'pick', 'plan', 'play', 'plus', 'poll', 'poor', 'port', 'post', 'pull', 'push', 'race', 'rail', 'rain', 'rank', 'rate', 'read', 'real', 'rear', 'rest', 'rich', 'ride', 'ring', 'rise', 'risk', 'road', 'rock', 'role', 'roll', 'room', 'root', 'rose', 'rule', 'rush', 'safe', 'said', 'sake', 'sale', 'salt', 'same', 'sand', 'save', 'seat', 'seed', 'seek', 'seem', 'seen', 'self', 'sell', 'send', 'sent', 'sets', 'ship', 'shop', 'shot', 'show', 'shut', 'sick', 'side', 'sign', 'silk', 'sing', 'sink', 'site', 'size', 'skin', 'slip', 'slow', 'snap', 'snow', 'soft', 'soil', 'sold', 'sole', 'some', 'song', 'soon', 'sort', 'soul', 'soup', 'sour', 'span', 'spin', 'spot', 'star', 'stay', 'step', 'stop', 'such', 'suit', 'sure', 'swim', 'tail', 'take', 'talk', 'tall', 'tank', 'tape', 'task', 'team', 'tear', 'tell', 'tend', 'term', 'test', 'text', 'than', 'that', 'them', 'then', 'they', 'thin', 'this', 'thus', 'till', 'time', 'tiny', 'tire', 'told', 'toll', 'tone', 'took', 'tool', 'toss', 'tour', 'town', 'tree', 'trip', 'true', 'tube', 'tune', 'turn', 'twin', 'type', 'unit', 'upon', 'used', 'user', 'uses', 'vary', 'vast', 'very', 'view', 'vote', 'wait', 'wake', 'walk', 'wall', 'want', 'ward', 'warm', 'warn', 'wash', 'wave', 'ways', 'weak', 'wear', 'week', 'well', 'went', 'were', 'west', 'what', 'when', 'whip', 'wide', 'wife', 'wild', 'will', 'wind', 'wine', 'wing', 'wire', 'wise', 'wish', 'with', 'wolf', 'wood', 'word', 'wore', 'work', 'worm', 'worn', 'wrap', 'yard', 'year', 'yell', 'your', 'zone'
}

# Important tickers that should keep their common word aliases
IMPORTANT_TICKERS: Set[str] = {
    'COST', 'LOW', 'V', 'T', 'GOOGL', 'GOOG', 'META', 'FB', 'AMZN', 'TSLA', 'NVDA', 'MSFT', 'AAPL'
}

def clean_problematic_aliases(dry_run: bool = True) -> None:
    """Remove problematic aliases from tickers.
    
    Args:
        dry_run: If True, only show what would be changed without making changes
    """
    db = next(get_db())
    
    changes_made = 0
    tickers_affected = 0
    
    for ticker in db.query(Ticker).all():
        original_aliases = ticker.aliases.copy()
        cleaned_aliases = []
        
        for alias in ticker.aliases:
            # Keep the alias if:
            # 1. It's not a problematic common word, OR
            # 2. The ticker is important and should keep common word aliases
            if (alias.lower() not in PROBLEMATIC_ALIASES or 
                ticker.symbol in IMPORTANT_TICKERS):
                cleaned_aliases.append(alias)
            else:
                if dry_run:
                    print(f"Would remove alias '{alias}' from {ticker.symbol} ({ticker.name})")
                changes_made += 1
        
        if len(cleaned_aliases) != len(original_aliases):
            tickers_affected += 1
            if not dry_run:
                ticker.aliases = cleaned_aliases
                db.commit()
                print(f"Cleaned {ticker.symbol}: removed {len(original_aliases) - len(cleaned_aliases)} problematic aliases")
    
    if dry_run:
        print(f"\nDRY RUN SUMMARY:")
        print(f"  Would affect {tickers_affected} tickers")
        print(f"  Would remove {changes_made} problematic aliases")
        print(f"\nTo apply changes, run with --apply flag")
    else:
        print(f"\nCLEANUP COMPLETE:")
        print(f"  Affected {tickers_affected} tickers")
        print(f"  Removed {changes_made} problematic aliases")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up problematic ticker aliases")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry run)")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    clean_problematic_aliases(dry_run=not args.apply)
