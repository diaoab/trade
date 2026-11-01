from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.config.settings import DATABASE_URL
from api.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Une URL passee par le code (tests) l'emporte sur celle des reglages.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline():

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite ne sait pas modifier une colonne en place : Alembic
            # recree alors la table.
            render_as_batch=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
