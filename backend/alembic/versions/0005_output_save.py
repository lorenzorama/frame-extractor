"""output save: save_to_output, output_subdir, output_index

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job",
        sa.Column("save_to_output", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("job", sa.Column("output_subdir", sa.String(), nullable=True))
    op.add_column("job", sa.Column("output_index", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("job", "output_index")
    op.drop_column("job", "output_subdir")
    op.drop_column("job", "save_to_output")
