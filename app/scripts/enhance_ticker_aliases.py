#!/usr/bin/env python3
"""Enhance ticker aliases with company name variations and industry terms."""

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Enhanced aliases for better matching
ENHANCED_ALIASES = {
    "V": [
        "visa",
        "visa inc",
        "visa corporation",
        "visa card",
        "visa payment",
        "visa network",
        "visa international",
        "visa worldwide",
    ],
    "MA": [
        "mastercard",
        "mastercard inc",
        "mastercard corporation",
        "mastercard payment",
        "mastercard network",
        "mastercard international",
    ],
    "AAPL": [
        "apple",
        "apple inc",
        "apple corporation",
        "apple computer",
        "iphone",
        "ipad",
        "macbook",
        "mac",
        "ios",
        "app store",
        "itunes",
    ],
    "MSFT": [
        "microsoft",
        "microsoft corporation",
        "windows",
        "office",
        "azure",
        "xbox",
        "bing",
        "linkedin",
        "github",
        "teams",
    ],
    "GOOGL": [
        "google",
        "alphabet",
        "alphabet inc",
        "alphabet corporation",
        "youtube",
        "android",
        "chrome",
        "gmail",
        "maps",
        "search",
        "ads",
    ],
    "AMZN": [
        "amazon",
        "amazon.com",
        "amazon inc",
        "amazon corporation",
        "aws",
        "prime",
        "kindle",
        "alexa",
        "echo",
    ],
    "TSLA": [
        "tesla",
        "tesla inc",
        "tesla corporation",
        "tesla motors",
        "model s",
        "model 3",
        "model x",
        "model y",
        "cybertruck",
        "autopilot",
        "supercharger",
    ],
    "META": [
        "facebook",
        "meta",
        "meta platforms",
        "meta inc",
        "instagram",
        "whatsapp",
        "oculus",
        "vr",
        "metaverse",
    ],
    "NVDA": [
        "nvidia",
        "nvidia corporation",
        "nvidia inc",
        "gpu",
        "cuda",
        "rtx",
        "gtx",
        "tensor",
        "ai",
        "gaming",
    ],
    "JPM": [
        "jp morgan",
        "jpmorgan",
        "jpmorgan chase",
        "jpmorgan chase & co",
        "chase bank",
        "investment bank",
        "jpm",
    ],
    "JNJ": [
        "johnson",
        "johnson & johnson",
        "jnj",
        "pharmaceutical",
        "healthcare",
        "medical devices",
        "consumer health",
    ],
    "WMT": [
        "walmart",
        "wal-mart",
        "walmart inc",
        "walmart corporation",
        "supercenter",
        "sam's club",
        "retail",
    ],
    "PG": [
        "procter",
        "procter & gamble",
        "p&g",
        "consumer goods",
        "household products",
        "personal care",
    ],
    "UNH": [
        "unitedhealth",
        "unitedhealth group",
        "united healthcare",
        "health insurance",
        "optum",
        "medicare",
    ],
    "HD": [
        "home depot",
        "home improvement",
        "hardware store",
        "construction materials",
        "tools",
        "appliances",
    ],
    "DIS": [
        "disney",
        "walt disney",
        "disney corporation",
        "disney world",
        "disneyland",
        "marvel",
        "star wars",
        "pixar",
        "espn",
        "abc",
    ],
    "PYPL": [
        "paypal",
        "paypal holdings",
        "paypal inc",
        "digital payment",
        "online payment",
        "venmo",
        "xoom",
    ],
    "ADBE": [
        "adobe",
        "adobe inc",
        "adobe corporation",
        "photoshop",
        "illustrator",
        "acrobat",
        "creative cloud",
        "pdf",
    ],
    "CRM": [
        "salesforce",
        "salesforce inc",
        "salesforce corporation",
        "crm",
        "cloud computing",
        "saas",
        "customer relationship",
    ],
    "NFLX": [
        "netflix",
        "netflix inc",
        "netflix corporation",
        "streaming",
        "video streaming",
        "original content",
        "subscription",
    ],
    "KO": [
        "coca cola",
        "coca-cola",
        "coke",
        "coca cola company",
        "soft drinks",
        "beverages",
        "sprite",
        "fanta",
    ],
    "PFE": [
        "pfizer",
        "pfizer inc",
        "pfizer corporation",
        "pharmaceutical",
        "vaccines",
        "medicine",
        "drugs",
    ],
    "T": [
        "at&t",
        "att",
        "at&t inc",
        "telecommunications",
        "wireless",
        "internet",
        "phone service",
        "directv",
    ],
    "INTC": [
        "intel",
        "intel corp",
        "intel corporation",
        "processors",
        "chips",
        "cpu",
        "semiconductor",
        "x86",
    ],
    "IBM": [
        "international business machines",
        "ibm corp",
        "ibm corporation",
        "enterprise",
        "cloud computing",
        "artificial intelligence",
        "watson",
    ],
    "GE": [
        "general electric",
        "general electric co",
        "ge corporation",
        "industrial",
        "aviation",
        "power",
        "healthcare",
        "renewable energy",
    ],
    "AMD": [
        "advanced micro devices",
        "amd inc",
        "amd corporation",
        "processors",
        "gpu",
        "ryzen",
        "radeon",
        "semiconductor",
    ],
    "SBUX": [
        "starbucks",
        "starbucks corp",
        "starbucks corporation",
        "coffee",
        "cafe",
        "coffee shop",
        "frappuccino",
    ],
    "NKE": [
        "nike",
        "nike inc",
        "nike corporation",
        "athletic",
        "sports",
        "shoes",
        "apparel",
        "jordan",
    ],
    "TGT": [
        "target",
        "target corp",
        "target corporation",
        "retail",
        "department store",
        "shopping",
        "red card",
    ],
    "LOW": [
        "lowes",
        "lowes cos",
        "lowes companies",
        "home improvement",
        "hardware",
        "construction",
        "tools",
    ],
    "COST": [
        "costco",
        "costco wholesale",
        "costco wholesale corp",
        "warehouse club",
        "bulk shopping",
        "membership",
    ],
    "CVS": [
        "cvs health",
        "cvs health corp",
        "cvs pharmacy",
        "pharmacy",
        "healthcare",
        "retail pharmacy",
        "minute clinic",
    ],
    "VZ": [
        "verizon",
        "verizon communications",
        "verizon wireless",
        "telecommunications",
        "wireless",
        "fios",
        "5g",
    ],
    "CMCSA": [
        "comcast",
        "comcast corp",
        "comcast corporation",
        "cable",
        "internet",
        "xfinity",
        "nbc",
        "universal",
    ],
    "ACN": [
        "accenture",
        "accenture plc",
        "consulting",
        "technology services",
        "digital transformation",
        "outsourcing",
    ],
    "WFC": [
        "wells fargo",
        "wells fargo & co",
        "wells fargo bank",
        "banking",
        "financial services",
        "mortgage",
    ],
    "RTX": [
        "raytheon",
        "raytheon technologies",
        "raytheon corp",
        "defense",
        "aerospace",
        "military",
        "pratt & whitney",
    ],
    "LMT": [
        "lockheed martin",
        "lockheed martin corp",
        "defense contractor",
        "aerospace",
        "f-35",
        "military",
        "space",
    ],
    "CAT": [
        "caterpillar",
        "caterpillar inc",
        "caterpillar corporation",
        "construction",
        "mining",
        "heavy machinery",
        "equipment",
    ],
    "HON": [
        "honeywell",
        "honeywell international",
        "honeywell inc",
        "industrial",
        "automation",
        "aerospace",
        "building technologies",
    ],
    "BMY": [
        "bristol myers",
        "bristol myers squibb",
        "bristol myers squibb co",
        "pharmaceutical",
        "cancer drugs",
        "immunotherapy",
    ],
    "COP": [
        "conocophillips",
        "conoco phillips",
        "conoco",
        "oil",
        "gas",
        "energy",
        "petroleum",
        "exploration",
    ],
    "ISRG": [
        "intuitive surgical",
        "intuitive surgical inc",
        "da vinci",
        "robotic surgery",
        "medical devices",
        "surgical robots",
    ],
    "GILD": [
        "gilead",
        "gilead sciences",
        "gilead sciences inc",
        "pharmaceutical",
        "hiv drugs",
        "hepatitis c",
        "antiviral",
    ],
    "MDT": [
        "medtronic",
        "medtronic plc",
        "medtronic inc",
        "medical devices",
        "pacemakers",
        "insulin pumps",
        "surgical instruments",
    ],
    "CI": [
        "cigna",
        "cigna corp",
        "cigna corporation",
        "health insurance",
        "pharmacy",
        "medicare",
        "healthcare",
    ],
}


def enhance_ticker_aliases(input_file: str, output_file: str) -> None:
    """Enhance ticker aliases with additional variations.

    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
    """
    enhanced_tickers = []

    with open(input_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            symbol = row["symbol"]
            name = row["name"]

            # Parse existing aliases
            try:
                existing_aliases = json.loads(row["aliases"])
            except json.JSONDecodeError:
                existing_aliases = []

            # Add enhanced aliases if available
            if symbol in ENHANCED_ALIASES:
                enhanced_aliases = ENHANCED_ALIASES[symbol]
                # Combine and deduplicate
                all_aliases = list(set(existing_aliases + enhanced_aliases))
            else:
                all_aliases = existing_aliases

            # Sort aliases for consistency
            all_aliases.sort()

            enhanced_tickers.append(
                {"symbol": symbol, "name": name, "aliases": json.dumps(all_aliases)}
            )

    # Write enhanced data
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["symbol", "name", "aliases"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enhanced_tickers)

    logger.info(f"Enhanced {len(enhanced_tickers)} tickers with improved aliases")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    input_file = Path(__file__).parent.parent.parent / "data" / "tickers_core.csv"
    output_file = input_file  # Overwrite the original file

    enhance_ticker_aliases(str(input_file), str(output_file))
