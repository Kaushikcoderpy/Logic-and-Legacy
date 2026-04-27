# Logic & Legacy: Advanced Postgres Mechanics
# Demonstrates 1:1, 1:N, M:N Relationships, Parameterized Queries to stop SQL injection,
# and Event-Driven Triggers for Audit Logging.

import asyncio
import asyncpg

DB_DSN = "postgresql://postgres:supersecret@localhost:5432/logic_legacy_db"

async def initialize_schema_and_triggers(pool):
    """
    Sets up relational tables and an Audit Trigger.
    """
    async with pool.acquire() as conn:
        print("[SYSTEM] Building Relational Schema...")
        
        # 1. ONE-TO-MANY (1:N)
        # A company can have many employees, but an employee belongs to one company.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                company_id INT REFERENCES companies(id) ON DELETE CASCADE,
                name VARCHAR(100) NOT NULL,
                salary INT NOT NULL
            );
        """)

        # 2. MANY-TO-MANY (M:N)
        # Employees can have many skills, and skills belong to many employees.
        # This REQUIRES a Junction Table.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id SERIAL PRIMARY KEY,
                skill_name VARCHAR(50) UNIQUE NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS employee_skills (
                employee_id INT REFERENCES employees(id) ON DELETE CASCADE,
                skill_id INT REFERENCES skills(id) ON DELETE CASCADE,
                PRIMARY KEY (employee_id, skill_id) -- Composite Primary Key
            );
        """)

        # 3. TRIGGERS: The Audit Log Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS salary_audit_logs (
                id SERIAL PRIMARY KEY,
                employee_id INT NOT NULL,
                old_salary INT,
                new_salary INT,
                changed_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Create the Trigger Function (The Logic)
        await conn.execute("""
            CREATE OR REPLACE FUNCTION log_salary_change()
            RETURNS TRIGGER AS $$
            BEGIN
                -- Only log if the salary actually changed
                IF NEW.salary <> OLD.salary THEN
                    INSERT INTO salary_audit_logs(employee_id, old_salary, new_salary)
                    VALUES(OLD.id, OLD.salary, NEW.salary);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Attach the Trigger to the Table (The Event Listener)
        await conn.execute("""
            DROP TRIGGER IF EXISTS salary_change_trigger ON employees;
            CREATE TRIGGER salary_change_trigger
            AFTER UPDATE ON employees
            FOR EACH ROW
            EXECUTE FUNCTION log_salary_change();
        """)
        print("[SYSTEM] Schema and Triggers initialized.")


async def execute_parameterized_queries(pool):
    """
    Demonstrates the ONLY safe way to accept user input.
    """
    async with pool.acquire() as conn:
        # Seed some data
        await conn.execute("INSERT INTO companies(name) VALUES ('CyberDyne') ON CONFLICT DO NOTHING;")
        company_id = await conn.fetchval("SELECT id FROM companies WHERE name = 'CyberDyne';")
        
        await conn.execute("""
            INSERT INTO employees(company_id, name, salary) 
            VALUES ($1, 'John Connor', 80000)
        """, company_id)

        # --- THE VULNERABLE WAY (String Interpolation) ---
        # If user_input was:  John Connor'; DROP TABLE employees; --
        # The database would execute the drop command.
        
        # --- THE SHIELD: Parameterized Queries ---
        # We pass data separately using $1. 
        # Postgres treats $1 strictly as a string literal, NEVER as executable code.
        user_input = "John Connor"
        print("\n[SYSTEM] Running safe parameterized query...")
        
        # In asyncpg, parameters are passed as arguments after the query string
        safe_result = await conn.fetchrow("""
            SELECT id, name, salary FROM employees WHERE name = $1;
        """, user_input)
        
        print(f"Result: {safe_result['name']} makes ${safe_result['salary']}")


async def demonstrate_trigger(pool):
    """
    Triggers the automated audit log by changing a salary.
    """
    async with pool.acquire() as conn:
        print("\n[SYSTEM] Updating salary to fire the database trigger...")
        # Give John Connor a raise
        await conn.execute("""
            UPDATE employees SET salary = 120000 WHERE name = 'John Connor';
        """)
        
        # Check the audit log. Our Python code didn't insert this—Postgres did it automatically!
        audit_records = await conn.fetch("SELECT * FROM salary_audit_logs;")
        print("[SYSTEM] Audit Log Results:")
        for record in audit_records:
            print(f"Employee {record['employee_id']} salary changed: ${record['old_salary']} -> ${record['new_salary']} at {record['changed_at']}")

async def main():
    pool = await asyncpg.create_pool(dsn=DB_DSN)
    try:
        await initialize_schema_and_triggers(pool)
        await execute_parameterized_queries(pool)
        await demonstrate_trigger(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    # asyncio.run(main())
    pass
