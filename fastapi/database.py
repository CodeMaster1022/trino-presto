from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database connection strings
DB1_URL = f"postgresql://{os.environ.get('DB1_USER')}:{os.environ.get('DB1_PASSWORD')}@{os.environ.get('DB1_HOST')}:{os.environ.get('DB1_PORT')}/{os.environ.get('DB1_NAME')}"
DB2_URL = f"postgresql://{os.environ.get('DB2_USER')}:{os.environ.get('DB2_PASSWORD')}@{os.environ.get('DB2_HOST')}:{os.environ.get('DB2_PORT')}/{os.environ.get('DB2_NAME')}"

# Create engines for both databases
db1_engine = create_engine(DB1_URL)
db2_engine = create_engine(DB2_URL)

# Create session factories
SessionDB1 = sessionmaker(autocommit=False, autoflush=False, bind=db1_engine)
SessionDB2 = sessionmaker(autocommit=False, autoflush=False, bind=db2_engine)

# Base class for DB1 models
Base1 = declarative_base()

# Base class for DB2 models
Base2 = declarative_base()

# Metadata objects
metadata_db1 = MetaData()
metadata_db2 = MetaData()

# Dependency to get DB sessions
def get_db1():
    db = SessionDB1()
    try:
        yield db
    finally:
        db.close()

def get_db2():
    db = SessionDB2()
    try:
        yield db
    finally:
        db.close()