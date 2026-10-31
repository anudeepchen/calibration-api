import os
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://calibration:calibration@localhost:5432/calibration"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
