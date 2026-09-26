import os

os.environ.setdefault(
    "ORDERGUARD_DATABASE_URL", "postgresql+psycopg://localhost:5432/orderguard_test"
)
# The test suite legitimately fires far more POST /simulations requests in
# a short window than any real client should (e.g. 21 across test_api.py,
# several of them concurrent) -- raise the budget so the production rate
# limit (api/rate_limit.py) never causes test flakiness.
os.environ.setdefault("ORDERGUARD_RATE_LIMIT_MAX_REQUESTS", "1000")

import pytest  # noqa: E402

from orderguard.persistence.database import (  # noqa: E402
    create_all_tables,
    get_engine,
    get_session_factory,
)
from orderguard.persistence.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    create_all_tables()
    yield


@pytest.fixture
def db_session():
    Session = get_session_factory()
    session = Session()
    try:
        yield session
    finally:
        session.close()
        with get_engine().begin() as conn:
            table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            conn.exec_driver_sql(f"TRUNCATE {table_names} CASCADE")
