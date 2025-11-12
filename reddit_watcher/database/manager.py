from sqlalchemy import inspect
from reddit_watcher.database.config import get_engine, get_session, Base
from sqlalchemy import text, Table
import pandas as pd


class DBManager:
    def __init__(self, db_path=None):
        self.engine = get_engine(db_path)
        self.session = get_session(self.engine)

    # ---------- DATABASE MANAGEMENT ----------

    def create_db(self):
        """Create all tables."""
        Base.metadata.create_all(self.engine)
        print("✅ Database and tables created successfully.")

    def drop_db(self):
        """Drop all tables."""
        Base.metadata.drop_all(self.engine)
        print("⚠️ All tables dropped.")

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
            print(f"⚠️ Table '{table_name}' does not exist.")
            return

        # Reflect the model's table metadata before dropping
        model.__table__.drop(self.engine)
        print(f"🗑️ Dropped table '{table_name}' successfully.")

    def insert_record(self, record):
        """Insert a new record (ORM object)."""
        self.session.add(record)
        self.session.commit()
        print(f"✅ Inserted record into {record.__tablename__} (ID: {record.id})")

    def delete_record(self, model, record_id):
        """Delete a record by primary key."""
        obj = self.session.get(model, record_id)
        if obj:
            self.session.delete(obj)
            self.session.commit()
            print(f"🗑️ Deleted record {record_id} from {model.__tablename__}")
        else:
            print(f"⚠️ Record {record_id} not found in {model.__tablename__}")

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
        print(f"🧹 Deleted {deleted} records from {model.__tablename__}")

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
