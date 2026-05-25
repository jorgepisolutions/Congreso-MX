from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "Idx%(table_name)s%(column_0_name)s",
    "uq": "Uk%(table_name)s%(column_0_name)s",
    "ck": "Ck%(table_name)s%(constraint_name)s",
    "fk": "Fk%(table_name)s%(column_0_name)s",
    "pk": "Pk%(table_name)s",
}

DEFAULT_TABLE_KWARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


# Base declarativa para todos los modelos. La naming_convention garantiza
# que Alembic autogenere nombres consistentes (UkX, IdxY, FkZ) en PascalCase.
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
