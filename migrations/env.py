from alembic import context
import os

from inventory.db import database_engine, metadata, required

engine = database_engine(os.environ.get("DATABASE_URL_UNPOOLED") or required("DATABASE_URL"))
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
