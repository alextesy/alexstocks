"""Context analyzer for determining ticker relevance in articles."""

import logging
import re

logger = logging.getLogger(__name__)

# Negative keywords that suggest the ticker mention is NOT about the company
NEGATIVE_KEYWORDS = {
    "V": [
        "visa application", "visa requirements", "visa process", "visa status",
        "visa interview", "visa office", "immigration", "passport", "travel visa",
        "student visa", "work visa", "tourist visa", "visa waiver", "visa extension",
        "visa renewal", "visa denial", "visa approval", "embassy", "consulate"
    ],
    "MA": [
        "master's degree", "master degree", "master program", "master thesis",
        "master student", "master class", "master chef", "master craftsman",
        "master builder", "master plan", "master key", "master switch"
    ],
    "T": [
        "at&t store", "at&t customer service", "at&t bill", "at&t account",
        "at&t phone", "at&t internet", "at&t wireless", "at&t plan",
        "at&t service", "at&t support", "at&t coverage", "at&t network"
    ],
    "GE": [
        "general election", "general manager", "general public", "general assembly",
        "general strike", "general store", "general hospital", "general practice",
        "general knowledge", "general purpose", "general rule", "general consensus"
    ],
    "CAT": [
        "cat food", "cat litter", "cat toy", "cat bed", "cat carrier", "cat tree",
        "cat behavior", "cat health", "cat care", "cat breed", "cat adoption",
        "cat rescue", "cat shelter", "cat owner", "cat lover", "pet cat"
    ],
    "HD": [
        "hd tv", "hd video", "hd quality", "hd resolution", "hd display",
        "hd screen", "hd monitor", "hd camera", "hd recording", "hd streaming",
        "hd content", "hd format", "hd ready", "hd compatible"
    ],
    "LOW": [
        "low price", "low cost", "low budget", "low income", "low quality",
        "low risk", "low maintenance", "low profile", "low key", "low impact",
        "low priority", "low demand", "low supply", "low stock", "low inventory"
    ],
    "COST": [
        "cost effective", "cost benefit", "cost analysis", "cost reduction",
        "cost savings", "cost cutting", "cost control", "cost management",
        "cost structure", "cost basis", "cost center", "cost accounting"
    ],
    "CVS": [
        "cvs pharmacy", "cvs store", "cvs location", "cvs hours", "cvs coupon",
        "cvs card", "cvs receipt", "cvs app", "cvs caremark", "cvs minute clinic"
    ],
    "VZ": [
        "verizon store", "verizon customer service", "verizon bill", "verizon account",
        "verizon phone", "verizon internet", "verizon wireless", "verizon plan",
        "verizon service", "verizon support", "verizon coverage", "verizon network"
    ],
    "CMCSA": [
        "comcast store", "comcast customer service", "comcast bill", "comcast account",
        "comcast internet", "comcast cable", "comcast xfinity", "comcast service",
        "comcast support", "comcast coverage", "comcast network", "comcast plan"
    ],
    "WFC": [
        "wells fargo store", "wells fargo customer service", "wells fargo account",
        "wells fargo bank", "wells fargo mortgage", "wells fargo credit card",
        "wells fargo loan", "wells fargo atm", "wells fargo branch", "wells fargo online"
    ],
    "RTX": [
        "rtx graphics", "rtx card", "rtx gpu", "rtx ray tracing", "rtx technology",
        "rtx support", "rtx enabled", "rtx features", "rtx performance", "rtx gaming"
    ],
    "LMT": [
        "lockheed martin store", "lockheed martin customer service", "lockheed martin account",
        "lockheed martin employee", "lockheed martin job", "lockheed martin career",
        "lockheed martin hiring", "lockheed martin office", "lockheed martin location"
    ],
    "HON": [
        "honeywell store", "honeywell customer service", "honeywell account",
        "honeywell product", "honeywell service", "honeywell support",
        "honeywell thermostat", "honeywell security", "honeywell automation"
    ],
    "BMY": [
        "bristol myers store", "bristol myers customer service", "bristol myers account",
        "bristol myers product", "bristol myers service", "bristol myers support",
        "bristol myers drug", "bristol myers medication", "bristol myers treatment"
    ],
    "COP": [
        "conocophillips store", "conocophillips customer service", "conocophillips account",
        "conocophillips employee", "conocophillips job", "conocophillips career",
        "conocophillips hiring", "conocophillips office", "conocophillips location"
    ],
    "ISRG": [
        "intuitive surgical store", "intuitive surgical customer service", "intuitive surgical account",
        "intuitive surgical product", "intuitive surgical service", "intuitive surgical support",
        "intuitive surgical device", "intuitive surgical system", "intuitive surgical training"
    ],
    "GILD": [
        "gilead store", "gilead customer service", "gilead account",
        "gilead product", "gilead service", "gilead support",
        "gilead drug", "gilead medication", "gilead treatment"
    ],
    "MDT": [
        "medtronic store", "medtronic customer service", "medtronic account",
        "medtronic product", "medtronic service", "medtronic support",
        "medtronic device", "medtronic system", "medtronic training"
    ],
    "CI": [
        "cigna store", "cigna customer service", "cigna account",
        "cigna product", "cigna service", "cigna support",
        "cigna insurance", "cigna plan", "cigna coverage"
    ]
}

# Positive keywords that suggest the ticker mention IS about the company
POSITIVE_KEYWORDS = {
    "V": [
        "visa inc", "visa corporation", "visa stock", "visa earnings", "visa revenue",
        "visa profit", "visa dividend", "visa share", "visa market", "visa financial",
        "visa quarterly", "visa annual", "visa ceo", "visa executive", "visa board",
        "visa investor", "visa analyst", "visa rating", "visa target", "visa price"
    ],
    "MA": [
        "mastercard inc", "mastercard corporation", "mastercard stock", "mastercard earnings",
        "mastercard revenue", "mastercard profit", "mastercard dividend", "mastercard share",
        "mastercard market", "mastercard financial", "mastercard quarterly", "mastercard annual",
        "mastercard ceo", "mastercard executive", "mastercard board", "mastercard investor",
        "mastercard analyst", "mastercard rating", "mastercard target", "mastercard price"
    ],
    "AAPL": [
        "apple inc", "apple corporation", "apple stock", "apple earnings", "apple revenue",
        "apple profit", "apple dividend", "apple share", "apple market", "apple financial",
        "apple quarterly", "apple annual", "apple ceo", "apple executive", "apple board",
        "apple investor", "apple analyst", "apple rating", "apple target", "apple price"
    ],
    "MSFT": [
        "microsoft corporation", "microsoft stock", "microsoft earnings", "microsoft revenue",
        "microsoft profit", "microsoft dividend", "microsoft share", "microsoft market",
        "microsoft financial", "microsoft quarterly", "microsoft annual", "microsoft ceo",
        "microsoft executive", "microsoft board", "microsoft investor", "microsoft analyst",
        "microsoft rating", "microsoft target", "microsoft price"
    ],
    "GOOGL": [
        "google stock", "alphabet stock", "alphabet inc", "alphabet corporation",
        "alphabet earnings", "alphabet revenue", "alphabet profit", "alphabet dividend",
        "alphabet share", "alphabet market", "alphabet financial", "alphabet quarterly",
        "alphabet annual", "alphabet ceo", "alphabet executive", "alphabet board",
        "alphabet investor", "alphabet analyst", "alphabet rating", "alphabet target",
        "alphabet price"
    ],
    "AMZN": [
        "amazon stock", "amazon inc", "amazon corporation", "amazon earnings",
        "amazon revenue", "amazon profit", "amazon dividend", "amazon share",
        "amazon market", "amazon financial", "amazon quarterly", "amazon annual",
        "amazon ceo", "amazon executive", "amazon board", "amazon investor",
        "amazon analyst", "amazon rating", "amazon target", "amazon price"
    ],
    "TSLA": [
        "tesla stock", "tesla inc", "tesla corporation", "tesla earnings",
        "tesla revenue", "tesla profit", "tesla dividend", "tesla share",
        "tesla market", "tesla financial", "tesla quarterly", "tesla annual",
        "tesla ceo", "tesla executive", "tesla board", "tesla investor",
        "tesla analyst", "tesla rating", "tesla target", "tesla price"
    ],
    "META": [
        "meta stock", "meta platforms", "meta inc", "meta corporation", "meta earnings",
        "meta revenue", "meta profit", "meta dividend", "meta share", "meta market",
        "meta financial", "meta quarterly", "meta annual", "meta ceo", "meta executive",
        "meta board", "meta investor", "meta analyst", "meta rating", "meta target",
        "meta price"
    ],
    "NVDA": [
        "nvidia stock", "nvidia corporation", "nvidia inc", "nvidia earnings",
        "nvidia revenue", "nvidia profit", "nvidia dividend", "nvidia share",
        "nvidia market", "nvidia financial", "nvidia quarterly", "nvidia annual",
        "nvidia ceo", "nvidia executive", "nvidia board", "nvidia investor",
        "nvidia analyst", "nvidia rating", "nvidia target", "nvidia price"
    ]
}

# Financial context keywords that suggest company relevance
FINANCIAL_KEYWORDS = [
    "stock", "share", "earnings", "revenue", "profit", "loss", "dividend",
    "market", "trading", "investor", "analyst", "rating", "target", "price",
    "ceo", "executive", "board", "quarterly", "annual", "financial", "corporate",
    "merger", "acquisition", "ipo", "bankruptcy", "lawsuit", "regulation",
    "sec", "filing", "report", "guidance", "forecast", "outlook"
]

# Industry context keywords
INDUSTRY_KEYWORDS = {
    "V": ["payment", "credit card", "financial services", "banking", "fintech"],
    "MA": ["payment", "credit card", "financial services", "banking", "fintech"],
    "AAPL": ["technology", "smartphone", "computer", "software", "hardware"],
    "MSFT": ["technology", "software", "cloud", "enterprise", "productivity"],
    "GOOGL": ["technology", "search", "advertising", "cloud", "ai"],
    "AMZN": ["e-commerce", "retail", "cloud", "logistics", "technology"],
    "TSLA": ["automotive", "electric vehicle", "energy", "transportation"],
    "META": ["social media", "technology", "advertising", "vr", "metaverse"],
    "NVDA": ["technology", "gpu", "ai", "gaming", "semiconductor"],
    "JPM": ["banking", "financial services", "investment", "wealth management"],
    "JNJ": ["pharmaceutical", "healthcare", "medical", "consumer health"],
    "WMT": ["retail", "e-commerce", "consumer goods", "logistics"],
    "PG": ["consumer goods", "household", "personal care", "beauty"],
    "UNH": ["healthcare", "insurance", "medical", "health services"],
    "HD": ["retail", "home improvement", "construction", "hardware"],
    "DIS": ["entertainment", "media", "theme parks", "streaming"],
    "PYPL": ["payment", "fintech", "digital wallet", "online payment"],
    "ADBE": ["software", "creative", "design", "marketing"],
    "CRM": ["software", "saas", "enterprise", "customer relationship"],
    "NFLX": ["entertainment", "streaming", "media", "content"],
    "KO": ["beverages", "consumer goods", "food", "drinks"],
    "PFE": ["pharmaceutical", "healthcare", "vaccines", "medicine"],
    "T": ["telecommunications", "wireless", "internet", "media"],
    "INTC": ["technology", "semiconductor", "processor", "chip"],
    "IBM": ["technology", "enterprise", "cloud", "ai"],
    "GE": ["industrial", "aviation", "power", "healthcare"],
    "AMD": ["technology", "semiconductor", "processor", "gpu"],
    "SBUX": ["retail", "food", "beverages", "coffee"],
    "NKE": ["retail", "apparel", "sports", "athletic"],
    "TGT": ["retail", "consumer goods", "department store"],
    "LOW": ["retail", "home improvement", "construction", "hardware"],
    "COST": ["retail", "wholesale", "membership", "consumer goods"],
    "CVS": ["retail", "pharmacy", "healthcare", "consumer health"],
    "VZ": ["telecommunications", "wireless", "internet", "media"],
    "CMCSA": ["telecommunications", "cable", "internet", "media"],
    "ACN": ["consulting", "technology services", "outsourcing"],
    "WFC": ["banking", "financial services", "mortgage", "wealth management"],
    "RTX": ["defense", "aerospace", "military", "technology"],
    "LMT": ["defense", "aerospace", "military", "technology"],
    "CAT": ["industrial", "construction", "mining", "equipment"],
    "HON": ["industrial", "automation", "aerospace", "building technologies"],
    "BMY": ["pharmaceutical", "healthcare", "cancer", "immunotherapy"],
    "COP": ["energy", "oil", "gas", "petroleum"],
    "ISRG": ["healthcare", "medical devices", "robotic surgery"],
    "GILD": ["pharmaceutical", "healthcare", "hiv", "antiviral"],
    "MDT": ["healthcare", "medical devices", "pacemakers", "surgical"],
    "CI": ["healthcare", "insurance", "pharmacy", "health services"]
}


class ContextAnalyzer:
    """Analyzes context to determine ticker relevance in articles."""

    def __init__(self):
        """Initialize context analyzer."""
        self.negative_keywords = NEGATIVE_KEYWORDS
        self.positive_keywords = POSITIVE_KEYWORDS
        self.financial_keywords = FINANCIAL_KEYWORDS
        self.industry_keywords = INDUSTRY_KEYWORDS

    def analyze_ticker_relevance(
        self,
        ticker_symbol: str,
        text: str,
        matched_terms: list[str]
    ) -> tuple[float, list[str]]:
        """Analyze if ticker mention is relevant to the company.

        Args:
            ticker_symbol: Ticker symbol to analyze
            text: Article text content
            matched_terms: Terms that matched the ticker

        Returns:
            Tuple of (confidence_score, reasoning_terms)
        """
        text_lower = text.lower()
        confidence = 0.5  # Base confidence
        reasoning_terms = []

        # Check for negative keywords (reduce confidence more aggressively)
        negative_score = self._check_negative_keywords(ticker_symbol, text_lower)
        if negative_score > 0:
            confidence -= negative_score * 0.6  # More aggressive penalty
            reasoning_terms.append(f"negative_context_{negative_score}")

        # Check for positive keywords (increase confidence)
        positive_score = self._check_positive_keywords(ticker_symbol, text_lower)
        if positive_score > 0:
            confidence += positive_score * 0.3  # Increased weight for positive signals
            reasoning_terms.append(f"positive_context_{positive_score}")

        # Check for financial context
        financial_score = self._check_financial_context(text_lower)
        if financial_score > 0:
            confidence += financial_score * 0.15
            reasoning_terms.append(f"financial_context_{financial_score}")

        # Check for industry context
        industry_score = self._check_industry_context(ticker_symbol, text_lower)
        if industry_score > 0:
            confidence += industry_score * 0.1
            reasoning_terms.append(f"industry_context_{industry_score}")

        # Check for company name presence
        company_name_score = self._check_company_name_presence(ticker_symbol, text_lower)
        if company_name_score > 0:
            confidence += company_name_score * 0.25
            reasoning_terms.append(f"company_name_{company_name_score}")

        # Special handling for single-letter tickers (reduce false positives)
        if len(ticker_symbol) == 1:
            # Require higher confidence for single-letter tickers, but allow strong positive signals
            if confidence < 0.55 and not any("positive_context" in term for term in reasoning_terms):
                confidence = 0.0
                reasoning_terms.append("single_letter_low_confidence")

        # Ensure confidence is between 0 and 1
        confidence = max(0.0, min(1.0, confidence))

        return confidence, reasoning_terms

    def _check_negative_keywords(self, ticker_symbol: str, text: str) -> float:
        """Check for negative keywords that suggest non-company context."""
        if ticker_symbol not in self.negative_keywords:
            return 0.0

        negative_terms = self.negative_keywords[ticker_symbol]
        matches = 0

        for term in negative_terms:
            # Use word boundary matching for more precise detection
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        # Return normalized score (0-1)
        return min(1.0, matches / len(negative_terms))

    def _check_positive_keywords(self, ticker_symbol: str, text: str) -> float:
        """Check for positive keywords that suggest company context."""
        if ticker_symbol not in self.positive_keywords:
            return 0.0

        positive_terms = self.positive_keywords[ticker_symbol]
        matches = 0

        for term in positive_terms:
            if term in text:
                matches += 1

        # Return normalized score (0-1)
        return min(1.0, matches / len(positive_terms))

    def _check_financial_context(self, text: str) -> float:
        """Check for financial context keywords."""
        matches = 0

        for keyword in self.financial_keywords:
            if keyword in text:
                matches += 1

        # Return normalized score (0-1)
        return min(1.0, matches / len(self.financial_keywords))

    def _check_industry_context(self, ticker_symbol: str, text: str) -> float:
        """Check for industry-specific context keywords."""
        if ticker_symbol not in self.industry_keywords:
            return 0.0

        industry_terms = self.industry_keywords[ticker_symbol]
        matches = 0

        for term in industry_terms:
            if term in text:
                matches += 1

        # Return normalized score (0-1)
        return min(1.0, matches / len(industry_terms))

    def _check_company_name_presence(self, ticker_symbol: str, text: str) -> float:
        """Check for company name presence in text."""
        # This would need to be enhanced with actual company names
        # For now, return a base score
        return 0.0


def get_context_analyzer() -> ContextAnalyzer:
    """Get context analyzer instance."""
    return ContextAnalyzer()
