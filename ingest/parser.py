"""GDELT GKG and Export CSV parser for mapping to Article model."""

import csv
import logging
from datetime import UTC, datetime

from app.db.models import Article
from app.services.sentiment import get_sentiment_service

logger = logging.getLogger(__name__)

# GDELT GKG CSV column mapping (based on GDELT 2.0 format)
GDELT_GKG_COLUMNS = [
    "GKGRECORDID",  # 0: Unique identifier
    "DATE",  # 1: Date in YYYYMMDDHHMMSS format
    "SourceCollectionIdentifier",  # 2: Source collection
    "SourceCommonName",  # 3: Source name
    "DocumentIdentifier",  # 4: URL
    "Counts",  # 5: Count information
    "V2Counts",  # 6: V2 count information
    "Themes",  # 7: Themes
    "V2Themes",  # 8: V2 themes
    "Locations",  # 9: Locations
    "V2Locations",  # 10: V2 locations
    "Persons",  # 11: Persons
    "V2Persons",  # 12: V2 persons
    "Organizations",  # 13: Organizations
    "V2Organizations",  # 14: V2 organizations
    "V2Tone",  # 15: Tone information
    "V2EnhancedDates",  # 16: Enhanced dates
    "V2GCAM",  # 17: GCAM information
    "V2SharingImage",  # 18: Sharing image
    "V2RelatedImages",  # 19: Related images
    "V2SocialImageEmbeds",  # 20: Social image embeds
    "V2SocialVideoEmbeds",  # 21: Social video embeds
    "V2Quotations",  # 22: Quotations
    "V2AllNames",  # 23: All names
    "V2Amounts",  # 24: Amounts
    "V2TranslationInfo",  # 25: Translation info
    "V2ExtrasXML",  # 26: Extras XML
]


def parse_gdelt_date(date_str: str) -> datetime:
    """Parse GDELT date string to datetime object.

    Args:
        date_str: Date in YYYYMMDDHHMMSS format

    Returns:
        datetime object in UTC timezone
    """
    try:
        # GDELT dates are in YYYYMMDDHHMMSS format
        return datetime.strptime(date_str, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError as e:
        logger.warning(f"Failed to parse date '{date_str}': {e}")
        return datetime.now(UTC)


def extract_url(document_id: str) -> str | None:
    """Extract URL from document identifier.

    Args:
        document_id: Document identifier from GDELT

    Returns:
        URL if valid, None otherwise
    """
    if not document_id or document_id == "#":
        return None

    # GDELT document identifiers are typically URLs
    if document_id.startswith(("http://", "https://")):
        return document_id

    return None


def extract_title_from_url(url: str) -> str:
    """Extract a basic title from URL.

    Args:
        url: Article URL

    Returns:
        Basic title derived from URL
    """
    if not url:
        return "Untitled"

    # Extract domain and path for basic title
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.strip("/").replace("/", " - ")

        if path:
            return f"{domain}: {path}"
        else:
            return domain
    except Exception:
        return "Untitled"


def parse_gdelt_gkg_row(row: list[str]) -> Article | None:
    """Parse a single GDELT GKG CSV row into an Article model.

    Args:
        row: CSV row as list of strings

    Returns:
        Article model instance or None if parsing fails
    """
    if len(row) < len(GDELT_GKG_COLUMNS):
        logger.warning(f"Row has {len(row)} columns, expected {len(GDELT_GKG_COLUMNS)}")
        return None

    try:
        # Extract key fields
        gkg_record_id = row[0]
        date_str = row[1]
        document_id = row[4]

        # Parse date
        published_at = parse_gdelt_date(date_str)

        # Extract URL
        url = extract_url(document_id)
        if not url:
            logger.debug(f"No valid URL for record {gkg_record_id}")
            return None

        # Create basic title from URL
        title = extract_title_from_url(url)

        # Analyze sentiment of the title
        sentiment_service = get_sentiment_service()
        try:
            sentiment = sentiment_service.analyze_sentiment(title)
        except Exception as e:
            logger.warning(f"Failed to analyze sentiment for title '{title}': {e}")
            sentiment = None

        # Create Article instance
        article = Article(
            source="gdelt",
            url=url,
            published_at=published_at,
            title=title,
            text=None,  # GDELT GKG doesn't contain full text
            lang=None,  # Language detection would need additional processing
            sentiment=sentiment,
        )

        return article

    except Exception as e:
        logger.error(f"Failed to parse GDELT row: {e}")
        return None


def parse_gdelt_gkg_csv(csv_content: str) -> list[Article]:
    """Parse GDELT GKG CSV content into Article models.

    Args:
        csv_content: Raw CSV content as string

    Returns:
        List of Article model instances
    """
    articles = []

    try:
        # Parse CSV content
        csv_reader = csv.reader(csv_content.splitlines())

        # Skip header if present
        first_row = next(csv_reader, None)
        if first_row and first_row[0] == "GKGRECORDID":
            logger.debug("Skipping CSV header")
        else:
            # If first row is not header, process it
            if first_row:
                article = parse_gdelt_gkg_row(first_row)
                if article:
                    articles.append(article)

        # Process remaining rows
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                article = parse_gdelt_gkg_row(row)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.warning(f"Failed to parse row {row_num}: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to parse GDELT CSV: {e}")
        return []

    logger.info(f"Parsed {len(articles)} articles from GDELT CSV")
    return articles


def parse_gdelt_gkg_file(file_path: str) -> list[Article]:
    """Parse GDELT GKG CSV file into Article models.

    Args:
        file_path: Path to GDELT GKG CSV file

    Returns:
        List of Article model instances
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return parse_gdelt_gkg_csv(content)
    except Exception as e:
        logger.error(f"Failed to read GDELT file {file_path}: {e}")
        return []


def parse_gdelt_export_csv(csv_content: str) -> list[Article]:
    """Parse GDELT export CSV content into Article models.

    Args:
        csv_content: GDELT export CSV content as string

    Returns:
        List of Article model instances
    """
    articles = []
    
    try:
        # GDELT export format has different columns than GKG
        # We'll extract basic information and create articles
        lines = csv_content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            try:
                # Split by tab (GDELT export uses tab separation)
                fields = line.split('\t')
                
                if len(fields) < 15:  # Minimum required fields
                    continue
                
                # Extract basic fields from GDELT export format
                # Format: GlobalEventID, Day, MonthYear, Year, FractionDate, Actor1Code, Actor1Name, etc.
                global_event_id = fields[0] if len(fields) > 0 else ""
                day = fields[1] if len(fields) > 1 else ""
                month_year = fields[2] if len(fields) > 2 else ""
                year = fields[3] if len(fields) > 3 else ""
                
                # Extract actor information for better titles
                actor1_code = fields[5] if len(fields) > 5 else ""
                actor1_name = fields[6] if len(fields) > 6 else ""
                actor2_code = fields[15] if len(fields) > 15 else ""
                actor2_name = fields[16] if len(fields) > 16 else ""
                event_code = fields[26] if len(fields) > 26 else ""  # Event code
                event_base_code = fields[27] if len(fields) > 27 else ""  # Event base code
                event_root_code = fields[28] if len(fields) > 28 else ""  # Event root code
                action_geo_country_code = fields[51] if len(fields) > 51 else ""
                action_geo_country_name = fields[52] if len(fields) > 52 else ""
                
                # Extract the real source URL from the last field (field 60)
                source_url = fields[60] if len(fields) > 60 else ""
                
                # Create a more meaningful title from event data
                title_parts = []
                
                # Add actors
                if actor1_name and actor1_name.strip():
                    title_parts.append(actor1_name.strip())
                elif actor1_code and actor1_code.strip():
                    title_parts.append(actor1_code.strip())
                
                if actor2_name and actor2_name.strip():
                    title_parts.append(actor2_name.strip())
                elif actor2_code and actor2_code.strip():
                    title_parts.append(actor2_code.strip())
                
                # Add location context
                if action_geo_country_name and action_geo_country_name.strip():
                    title_parts.append(f"in {action_geo_country_name.strip()}")
                
                # Create title
                if title_parts:
                    title = " - ".join(title_parts)
                else:
                    title = f"Global Event {global_event_id}"
                
                # Use the real source URL from GDELT data
                if source_url and source_url.strip():
                    url = source_url.strip()
                else:
                    # Fallback to GDELT reference if no source URL is available
                    url = f"https://www.gdeltproject.org/data.html#eventdata-{global_event_id}"
                
                # Parse date
                try:
                    if year and month_year:
                        # Convert YYYYMM to datetime
                        year_int = int(year)
                        month_int = int(month_year) % 100
                        day_int = int(day) if day else 1
                        published_at = datetime(year_int, month_int, day_int, tzinfo=UTC)
                    else:
                        published_at = datetime.now(UTC)
                except (ValueError, TypeError):
                    published_at = datetime.now(UTC)
                
                # Create article
                article = Article(
                    source="gdelt",
                    url=url,
                    published_at=published_at,
                    title=title,
                    text=None,  # GDELT export doesn't have article text
                    lang="en",  # Default to English
                )
                
                articles.append(article)
                
            except Exception as e:
                logger.warning(f"Failed to parse line {line_num}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Failed to parse GDELT export CSV: {e}")
        return []
    
    logger.info(f"Parsed {len(articles)} articles from GDELT export CSV")
    return articles
