"""garantie annulation facturable

Revision ID: a6f2d9c8b4e1
Revises: e8b2d4c6f901
Create Date: 2026-05-12
"""

revision = "a6f2d9c8b4e1"
down_revision = "e8b2d4c6f901"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite stores these enums as text in this project; the new values are
    # handled at the application layer.
    pass


def downgrade():
    pass
