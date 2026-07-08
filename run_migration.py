#!/usr/bin/env python3
"""
Database Migration Runner

Runs SQL migration files against the database.
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration(migration_file: str):
    """
    Run a SQL migration file.
    
    Args:
        migration_file: Path to the SQL migration file
    """
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Read migration file
    if not os.path.exists(migration_file):
        print(f"ERROR: Migration file not found: {migration_file}")
        sys.exit(1)
    
    with open(migration_file, 'r') as f:
        migration_sql = f.read()
    
    print(f"Running migration: {migration_file}")
    print("-" * 60)

    # Connect to database and run migration
    conn = None
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False

        with conn.cursor() as cursor:
            # Execute migration
            cursor.execute(migration_sql)

            # Commit transaction
            conn.commit()
            print("✓ Migration completed successfully")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Run specific migration file
        migration_file = sys.argv[1]
        run_migration(migration_file)
    else:
        # Run all migrations in order
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        
        if not os.path.exists(migrations_dir):
            print(f"ERROR: Migrations directory not found: {migrations_dir}")
            sys.exit(1)
        
        # Get all .sql files sorted by name
        migration_files = sorted([
            f for f in os.listdir(migrations_dir) 
            if f.endswith('.sql')
        ])
        
        if not migration_files:
            print("No migration files found")
            return
        
        print(f"Found {len(migration_files)} migration(s)")
        print()
        
        for migration_file in migration_files:
            migration_path = os.path.join(migrations_dir, migration_file)
            run_migration(migration_path)
            print()
        
        print("All migrations completed successfully!")

if __name__ == '__main__':
    main()
