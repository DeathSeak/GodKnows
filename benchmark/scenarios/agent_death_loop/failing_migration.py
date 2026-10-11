"""
Enterprise Alembic / PostgreSQL Database Schema Migration Script.
Simulates a distributed schema lock contention deadlock during rolling zero-downtime deployment.
"""

import sys
import time

def run_migration():
    sys.stdout.write("[INFO] Alembic migration runner v1.13.1\n")
    sys.stdout.write("[INFO] Target database: postgresql://core_migrator:***@pg-cluster-primary.internal:5432/production_app\n")
    sys.stdout.write("[INFO] Context: ContextImpl(connection=Connection(engine=Engine(PostgreSQL+asyncpg)))\n")
    sys.stdout.write("[INFO] Loading migration versions from /opt/app/migrations/versions...\n")
    sys.stdout.write("[INFO] Verified 84 existing schema revisions.\n")
    sys.stdout.write("[INFO] Acquiring global cluster migration advisory lock: pg_advisory_xact_lock(0x7F9A12DE)...\n")
    time.sleep(0.05)
    
    # Detailed failure trace
    sys.stderr.write("Traceback (most recent call last):\n")
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/alembic/runtime/migration.py", line 627, in run_migrations\n')
    sys.stderr.write('    step.migration_fn(**kw)\n')
    sys.stderr.write('  File "/opt/app/migrations/versions/20261011_089a_enterprise_billing_partitions.py", line 48, in upgrade\n')
    sys.stderr.write('    op.execute("ALTER TABLE customer_ledger_entries ADD COLUMN billing_partition_id UUID NOT NULL")\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/alembic/operations/ops.py", line 2210, in execute\n')
    sys.stderr.write('    return self.invoke(sql_text, execution_options=execution_options)\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py", line 1414, in execute\n')
    sys.stderr.write('    return meth(self, multiparams, params, _opt)\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/sqlalchemy/sql/elements.py", line 516, in _execute_on_connection\n')
    sys.stderr.write('    return connection._execute_clauseelement(self, multiparams, params, _opt)\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py", line 1638, in _execute_clauseelement\n')
    sys.stderr.write('    ret = self._execute_context(\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/sqlalchemy/engine/base.py", line 1842, in _execute_context\n')
    sys.stderr.write('    return self._exec_single_context(\n')
    sys.stderr.write('  File "/opt/venv/lib/python3.14/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py", line 782, in do_execute\n')
    sys.stderr.write('    raise asyncpg.exceptions.DeadlockDetectedError(\n')
    sys.stderr.write('asyncpg.exceptions.DeadlockDetectedError: deadlock detected\n')
    sys.stderr.write('DETAIL:  Process 48192 waits for ExclusiveLock on relation 189204 (customer_ledger_entries); blocked by process 47210.\n')
    sys.stderr.write('Process 47210 waits for RowShareLock on relation 189204; blocked by process 48192.\n')
    sys.stderr.write('HINT:  See server log for query details.\n')
    sys.stderr.write('STATEMENT:  ALTER TABLE customer_ledger_entries ADD COLUMN billing_partition_id UUID NOT NULL DEFAULT gen_random_uuid();\n')
    sys.stderr.write('ERROR [alembic.runtime.migration] Migration failed for revision 20261011_089a: deadlock detected while acquiring table ExclusiveLock.\n')
    sys.stderr.write('FATAL: Rolling back transaction. Schema left at revision 20261010_088f_audit_log_indexes. Migration aborted.\n')
    sys.exit(1)

if __name__ == "__main__":
    run_migration()
