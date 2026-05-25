"""Periodos_Tipo_Permanente

Revision ID: b8b89325e6b1
Revises: 5a91aeffbe1b
Create Date: 2026-05-25 23:00:43.959593+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8b89325e6b1'
down_revision: Union[str, Sequence[str], None] = '5a91aeffbe1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE Periodos MODIFY COLUMN Tipo "
        "ENUM('Ordinario','Extraordinario','Permanente') NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE Periodos MODIFY COLUMN Tipo "
        "ENUM('Ordinario','Extraordinario') NOT NULL"
    )
