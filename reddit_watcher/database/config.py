from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
from reddit_watcher.omniconf import config

Base = declarative_base()


def get_engine(db_path=None):
    """Create an SQLAlchemy engine for SQLite."""
    db_path = db_path or config.DB_FILE
    Path(db_path).parent.mkdir(exist_ok=True, parents=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_session(engine):
    """Return a new SQLAlchemy session."""
    Session = sessionmaker(bind=engine)
    return Session()
