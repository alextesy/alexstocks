"""Add stock price tables to database."""

import sys

sys.path.append('.')


from app.db.models import Base
from app.db.session import engine


def add_stock_price_tables():
    """Add stock price tables to the database."""
    print("Adding stock price tables...")

    # Create the new tables
    Base.metadata.create_all(bind=engine)

    print("Stock price tables added successfully!")
    print("Tables created:")
    print("- stock_price: Current stock prices")
    print("- stock_price_history: Historical price data for charts")
    print("- stock_data_collection: Track collection runs")

if __name__ == "__main__":
    add_stock_price_tables()

