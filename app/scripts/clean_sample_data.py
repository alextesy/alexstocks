"""Clean up sample and test data from the database."""

import logging

from app.db.models import Article, ArticleTicker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def clean_sample_data() -> None:
    """Remove all sample and test data from the database."""
    db = SessionLocal()
    try:
        # Delete sample articles
        sample_articles = db.query(Article).filter(Article.source == "sample").all()
        if sample_articles:
            sample_article_ids = [a.id for a in sample_articles]
            # Delete article-ticker links
            db.query(ArticleTicker).filter(
                ArticleTicker.article_id.in_(sample_article_ids)
            ).delete()
            # Delete articles
            db.query(Article).filter(Article.source == "sample").delete()
            logger.info(f"Deleted {len(sample_articles)} sample articles")

        # Delete test articles
        test_articles = db.query(Article).filter(Article.source == "test").all()
        if test_articles:
            test_article_ids = [a.id for a in test_articles]
            # Delete article-ticker links
            db.query(ArticleTicker).filter(
                ArticleTicker.article_id.in_(test_article_ids)
            ).delete()
            # Delete articles
            db.query(Article).filter(Article.source == "test").delete()
            logger.info(f"Deleted {len(test_articles)} test articles")

        db.commit()
        logger.info("Sample and test data cleanup completed")

        # Show remaining data
        remaining = db.query(Article).count()
        logger.info(f"Remaining articles: {remaining}")

    except Exception as e:
        logger.error(f"Failed to clean sample data: {e}")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    """Main function for cleaning sample data."""
    logging.basicConfig(level=logging.INFO)
    clean_sample_data()


if __name__ == "__main__":
    main()
