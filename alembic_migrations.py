# Logic & Legacy: Zero-Downtime Alembic Migration Pattern
# 
# Scenario: We have a "users" table with a "full_name" column.
# The business needs "first_name" and "last_name" instead.
# If we simply DROP full_name and ADD the new columns, the live API will crash 
# because existing Python code is still trying to read/write "full_name".
#
# This script demonstrates the Architect's 3-Phase Migration Protocol.

"""
Revision ID: a1b2c3d4e5f6
Revises: 9f8e7d6c5b4a
Create Date: 2026-04-12 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9f8e7d6c5b4a'
branch_labels = None
depends_on = None

def upgrade():
    print("[SYSTEM] Executing Zero-Downtime Schema Evolution...")
    
    # --- PHASE 1: SCHEMA EXPANSION (Additive Only) ---
    # We add the new columns. They MUST be nullable=True initially, 
    # otherwise the database will reject the migration because existing rows lack this data.
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))

    # --- PHASE 2: DATA MIGRATION (ETL within the DB) ---
    # We use raw SQL to split the existing 'full_name' strings and backfill 
    # the new columns. Doing this inside the database via op.execute() is 
    # exponentially faster than pulling records into Python and looping.
    op.execute("""
        UPDATE users 
        SET first_name = split_part(full_name, ' ', 1),
            last_name = substring(full_name from position(' ' in full_name) + 1)
        WHERE full_name IS NOT NULL AND first_name IS NULL;
    """)

    # --- PHASE 3: ENFORCING INTEGRITY ---
    # Now that all existing rows have data, it is safe to enforce the NOT NULL constraint.
    op.alter_column('users', 'first_name', nullable=False)
    op.alter_column('users', 'last_name', nullable=False)

    # ⚠️ CRITICAL ARCHITECTURAL RULE:
    # We DO NOT drop the 'full_name' column in this migration. 
    # Old versions of our application containers are currently running in production, 
    # and they still expect 'full_name' to exist. 
    # We will wait 7 days, deploy the updated Python code that only uses first/last name,
    # and then issue a SECOND migration (Revision B) to safely drop the 'full_name' column.


def downgrade():
    """
    The rollback strategy in case Phase 1-3 fails during deployment.
    """
    print("[SYSTEM] Executing Rollback...")
    # Because we didn't drop 'full_name', rolling back is perfectly safe!
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')

# =====================================================================
# --- ADVANCED ALEMBIC PATTERNS (THE SENIOR ARSENAL) ---
# =====================================================================

def upgrade_revision_b_safe_drop():
    """
    SCENARIO 2: The Safe Drop (Executed days/weeks after the first migration).
    We are now 100% sure no active Python API containers are referencing 'full_name'.
    """
    print("\n[SYSTEM] Executing Revision B: The Safe Drop...")
    op.drop_column('users', 'full_name')

def downgrade_revision_b():
    # Rolling back a drop requires recreating the column (data is lost though!)
    op.add_column('users', sa.Column('full_name', sa.String(200), nullable=True))

# ---

def upgrade_concurrent_index():
    """
    SCENARIO 3: Creating an Index without locking the table (Zero-Downtime).
    Standard CREATE INDEX locks the Postgres table for writes. On a 50GB table, 
    your API will throw timeouts. Postgres supports CONCURRENTLY, but it cannot 
    run inside a standard Alembic transaction.
    """
    print("\n[SYSTEM] Building Concurrent Index...")
    
    # CRITICAL: We must step outside the default Alembic transaction block!
    with op.get_context().autocommit_block():
        op.create_index(
            'idx_users_last_name',
            'users',
            ['last_name'],
            postgresql_concurrently=True # The magic zero-downtime flag
        )

# ---

def upgrade_enum_type():
    """
    SCENARIO 4: Adding a Postgres ENUM type safely.
    Autogenerate struggles natively with Postgres ENUMs. You must define 
    and create the type explicitly before attaching it to a column.
    """
    print("\n[SYSTEM] Creating and Binding Postgres ENUM...")
    from sqlalchemy.dialects import postgresql
    
    # 1. Define the type explicitly
    status_enum = postgresql.ENUM('active', 'suspended', 'banned', name='user_status_enum')
    
    # 2. Create the type in the database BEFORE adding the column
    status_enum.create(op.get_bind())
    
    # 3. Add the column using the new type and a safe server_default
    op.add_column('users', sa.Column(
        'status', 
        status_enum, 
        server_default='active', 
        nullable=False
    ))

def downgrade_enum_type():
    op.drop_column('users', 'status')
    # We must also drop the ENUM type from Postgres to keep the DB clean
    op.execute("DROP TYPE user_status_enum;")

# ---

def upgrade_batch_mode_sqlite():
    """
    SCENARIO 5: Batch Operations (Mandatory for SQLite & Massive Table Refactors).
    SQLite does not support DROP COLUMN or ALTER COLUMN natively. 
    Alembic uses "Batch Mode" to create a brand new temporary table, copy the data 
    over, drop the old table, and rename the new one behind the scenes.
    """
    print("\n[SYSTEM] Executing Batch Alter Table...")
    
    # batch_alter_table handles the complex table recreation transparently
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Change a column type safely
        batch_op.alter_column('age', type_=sa.Integer(), existing_type=sa.String())
        # Drop an obsolete field
        batch_op.drop_column('obsolete_field')
        # Create an index via batch
        batch_op.create_index('idx_users_age', ['age'])

# ---

def upgrade_bulk_data_backfill():
    """
    SCENARIO 6: Bulk Data Injection via SQLAlchemy Core.
    Sometimes you need to seed system configurations or default rows during a migration.
    """
    print("\n[SYSTEM] Seeding System Configurations...")
    
    # We define a lightweight table representation just for this migration
    config_table = sa.table('configurations',
        sa.column('key', sa.String),
        sa.column('value', sa.String)
    )
    
    # Fast, bulk insert
    op.bulk_insert(config_table, [
        {'key': 'maintenance_mode', 'value': 'false'},
        {'key': 'max_login_attempts', 'value': '5'},
        {'key': 'default_user_role', 'value': 'reader'}
    ])
