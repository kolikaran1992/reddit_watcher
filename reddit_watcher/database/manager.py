from sqlalchemy import inspect
from sqlalchemy import text, Table
from sqlalchemy.exc import IntegrityError
import pandas as pd
import traceback as tb
from pathlib import Path
import json

from reddit_watcher.database.config import get_engine, get_session, Base
from reddit_watcher.database.export_models_to_dict import extract_model_column_map
from reddit_watcher.omniconf import logger


class DBManager:
    def __init__(self, db_path=None):
        self.engine = get_engine(db_path)
        self.session = get_session(self.engine)

    # ---------- DATABASE MANAGEMENT ----------

    def create_db(self):
        """Create all tables."""
        Base.metadata.create_all(self.engine)
        models_dir = Path(__file__).parent.joinpath("model_dicts")
        models_dir.mkdir(exist_ok=True, parents=True)

        model_dict = extract_model_column_map(Base)

        for key, column_meta in model_dict.items():
            with open(models_dir.joinpath(f"{key}.json"), "w") as f:
                json.dump(column_meta, f, indent=2)

        logger.info("✅ Database and tables created successfully.")

    def drop_db(self):
        """Drop all tables."""
        Base.metadata.drop_all(self.engine)
        logger.info("⚠️ All tables dropped.")

    def list_tables(self):
        """List all existing tables."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    # ---------- TABLE OPERATIONS ----------

    def drop_table(self, model):
        """
        Drop a specific table corresponding to the given ORM model.

        Parameters
        ----------
        model : Declarative model class
            The SQLAlchemy ORM model class whose table should be dropped.
        """
        table_name = model.__tablename__
        inspector = inspect(self.engine)

        if table_name not in inspector.get_table_names():
            logger.info(f"⚠️ Table '{table_name}' does not exist.")
            return

        # Reflect the model's table metadata before dropping
        model.__table__.drop(self.engine)
        logger.info(f"🗑️ Dropped table '{table_name}' successfully.")

    def _exists_multi(self, model, filters: dict):
        """
        Check existence of a record using multiple fields.
        Equivalent to SELECT * FROM model WHERE all(filters) LIMIT 1
        """
        query = self.session.query(model)
        for field, value in filters.items():
            query = query.filter(getattr(model, field) == value)
        return query.first()

    # ---------------------------------------------------------
    # PUBLIC METHOD: checks existence *using only the record*
    # ---------------------------------------------------------
    def record_exists(self, record, unique_keys: list[str]):
        """
        Check whether the given record already exists, based on multiple unique fields.

        Parameters
        ----------
        record : ORM instance
        unique_keys : list[str]
            A list of column names used to check for duplicates.
        """
        Model = type(record)

        if not unique_keys:
            raise ValueError("unique_keys must be a non-empty list of column names.")

        filters = {key: getattr(record, key) for key in unique_keys}

        return self._exists_multi(Model, filters)

    # ---------------------------------------------------------
    # UPDATED INSERT: uses record_exists(record, unique_field)
    # ---------------------------------------------------------
    def insert_record(self, record, unique_keys: list[str] = None):
        """
        Insert a record only if a duplicate does NOT already exist.

        Parameters
        ----------
        record : ORM instance
        unique_keys : list[str], optional
            List of column names used to detect duplicates.
        """

        Model = type(record)

        # --- Duplicate check using multi-field match ---
        if unique_keys:
            filters = {key: getattr(record, key) for key in unique_keys}
            existing = self._exists_multi(Model, filters)

            if existing:
                key_str = ", ".join(f"{k}='{filters[k]}'" for k in filters)
                logger.info(
                    f"⚠️ Duplicate record in {Model.__tablename__} using keys: {key_str}. Skipping insert."
                )
                return existing

        # --- Safe insert ---
        try:
            self.session.add(record)
            self.session.commit()
            logger.info(f"✅ Inserted into {Model.__tablename__}")
            return record

        except IntegrityError:
            self.session.rollback()
            logger.exception(
                f"⚠️ IntegrityError inserting into {Model.__tablename__}. Insert skipped."
            )
            logger.exception(tb.format_exc())
            return None

    def delete_record(self, model, record_id):
        """Delete a record by primary key."""
        obj = self.session.get(model, record_id)
        if obj:
            self.session.delete(obj)
            self.session.commit()
            logger.info(f"🗑️ Deleted record {record_id} from {model.__tablename__}")
        else:
            logger.info(f"⚠️ Record {record_id} not found in {model.__tablename__}")

    def query_all(self, model):
        """Return all records of a model."""
        return self.session.query(model).all()

    def query_filter(self, model, **filters):
        """Filter records by given conditions."""
        return self.session.query(model).filter_by(**filters).all()

    def delete_all_from_table(self, model):
        """Delete all rows from a table."""
        deleted = self.session.query(model).delete()
        self.session.commit()
        logger.info(f"🧹 Deleted {deleted} records from {model.__tablename__}")

    def close(self):
        """Close the DB session."""
        self.session.close()

    def query_to_df(self, sql: str, params: dict = None) -> pd.DataFrame:
        """
        Execute a raw SQL query and return results as a Pandas DataFrame.

        Parameters
        ----------
        sql : str
            SQL query (can include placeholders like :param)
        params : dict, optional
            Query parameters (passed safely to SQLAlchemy)

        Returns
        -------
        pandas.DataFrame
        """
        df = pd.read_sql(text(sql), self.engine, params=params)
        return df
