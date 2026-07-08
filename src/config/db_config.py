import os
from sqlalchemy import create_engine

class DatabaseConfig:
    def __init__(self):
        self.db_config = {
            "dbname": os.getenv("DATABASE_NAME"),
            "user": os.getenv("DATABASE_USER"),
            "password": os.getenv("DATABASE_PASSWORD"),
            "host": os.getenv("DATABASE_HOST"),
            "port": os.getenv("DATABASE_PORT"),
        }

    def get_engine(self):
        db_url = 'postgresql://%s:%s@%s:%s/%s' % (
            self.db_config['user'],
            self.db_config['password'],
            self.db_config['host'],
            self.db_config['port'],
            self.db_config['dbname']
        )
        return create_engine(db_url)

    def get_db_config(self):
        return self.db_config
