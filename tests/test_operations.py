from __future__ import unicode_literals

import contextlib
import unittest

import django
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test.utils import override_settings
from django.utils.six import StringIO

from tenancy.models import Tenant, db_schema_table
from tenancy.utils import patch_connection_introspection

from .utils import TenancyTestCase


class TestTenantSchemaOperations(TenancyTestCase):
    def tearDown(self):
        super(TestTenantSchemaOperations, self).tearDown()
        # Make sure all migrations are considered unapplied.
        MigrationRecorder(connection).flush()

    def get_tenant_table_name(self, tenant, table_name):
        return table_name if connection.vendor == 'postgresql' else db_schema_table(tenant, table_name)

    @contextlib.contextmanager
    def tenant_connection_context(self, tenant):
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("SET search_path = %s" % tenant.db_schema)
            try:
                yield cursor
            finally:
                if connection.vendor == 'postgresql':
                    cursor.execute('RESET search_path')

    def get_tenant_table_names(self, tenant):
        with self.tenant_connection_context(tenant):
            table_names = connection.introspection.table_names()
        return table_names

    def get_tenant_table_columns(self, tenant, table_name):
        tenant_table_name = self.get_tenant_table_name(tenant, table_name)
        with self.tenant_connection_context(tenant) as cursor:
            columns = connection.introspection.get_table_description(cursor, tenant_table_name)
        return columns

    def get_tenant_table_column_names(self, tenant, table_name):
        return {
            column[0] for column in self.get_tenant_table_columns(tenant, table_name)
        }

    def get_tenant_table_constraints(self, tenant, table_name):
        tenant_table_name = self.get_tenant_table_name(tenant, table_name)
        with self.tenant_connection_context(tenant) as cursor, patch_connection_introspection(connection):
            constraints = connection.introspection.get_constraints(cursor, tenant_table_name)
        return constraints

    def get_column_constraints(self, constraints, column):
        return {
            name: details for name, details in constraints.items() if details['columns'] == [column]
        }

    def assertTenantTableExists(self, tenant, table_name):
        table_name = self.get_tenant_table_name(tenant, table_name)
        table_names = self.get_tenant_table_names(tenant)
        msg = "Table '%s' doesn't exist, existing table_names are: %s"
        self.assertIn(table_name, table_names, msg % (table_name, ', '.join(table_names)))

    def assertTenantTableDoesntExists(self, tenant, table_name):
        table_name = self.get_tenant_table_name(tenant, table_name)
        table_names = self.get_tenant_table_names(tenant)
        self.assertNotIn(table_name, table_names, "Table '%s' exists." % table_name)

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.create_model'})
    def test_create_model(self):
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_createmodel')
        call_command('migrate', 'tests', 'zero', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableDoesntExists(tenant, 'tests_createmodel')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.delete_model'})
    def test_delete_model(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_deletemodel')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableDoesntExists(tenant, 'tests_deletemodel')
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_deletemodel')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.rename_model'})
    def test_rename_model(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_renamemodel')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableDoesntExists(tenant, 'tests_renamemodel')
            self.assertTenantTableExists(tenant, 'tests_renamedmodel')
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_renamemodel')
            self.assertTenantTableDoesntExists(tenant, 'tests_renamedmodel')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.alter_model_table'})
    def test_alter_model_table(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_altermodeltable')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableDoesntExists(tenant, 'tests_altermodeltable')
            self.assertTenantTableExists(tenant, 'renamed')
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_altermodeltable')
            self.assertTenantTableDoesntExists(tenant, 'renamed')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.alter_unique_together'})
    def test_alter_unique_together(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        expected_constraint = {
            'index': connection.vendor != 'postgresql',
            'primary_key': False,
            # The get_constraints() method doesn't correctly set `foreign_key`
            # to `False` on PostgreSQL.
            'foreign_key': None if connection.vendor == 'postgresql' else False,
            'unique': True,
            'check': False,
            'columns': ['id', 'name'],
        }
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alteruniquetogether')
            for constraint in self.get_tenant_table_constraints(tenant, 'tests_alteruniquetogether').values():
                if constraint == expected_constraint:
                    break
            else:
                self.fail('Missing unique constraint.')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            for constraint in self.get_tenant_table_constraints(tenant, 'tests_alteruniquetogether').values():
                self.assertNotEqual(constraint, expected_constraint)
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alteruniquetogether')
            for constraint in self.get_tenant_table_constraints(tenant, 'tests_alteruniquetogether').values():
                if constraint == expected_constraint:
                    break
            else:
                self.fail('Missing unique constraint.')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.alter_index_together'})
    def test_alter_index_together(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        expected_index = {
            'index': True,
            'primary_key': False,
            # The get_constraints() method doesn't correctly set `foreign_key`
            # to `False` on PostgreSQL.
            'foreign_key': None if connection.vendor == 'postgresql' else False,
            'unique': False,
            'check': False,
            'columns': ['id', 'name'],
        }
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alterindextogether')
            for index in self.get_tenant_table_constraints(tenant, 'tests_alterindextogether').values():
                if index == expected_index:
                    break
            else:
                self.fail('Missing index.')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            for constraint in self.get_tenant_table_constraints(tenant, 'tests_alterindextogether').values():
                self.assertNotEqual(constraint, expected_index)
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alterindextogether')
            for index in self.get_tenant_table_constraints(tenant, 'tests_alterindextogether').values():
                if index == expected_index:
                    break
            else:
                self.fail('Missing index.')

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.add_field'})
    def test_add_field(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_addfield')
            self.assertEqual(len(self.get_tenant_table_columns(tenant, 'tests_addfield')), 1)
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_addfield'), {
                'id',
                'charfield',
                'textfield',
                'positiveintegerfield',
                'foreign_key_id',
            })
            constraints = self.get_tenant_table_constraints(tenant, 'tests_addfield')
            self.assertEqual(list(self.get_column_constraints(constraints, 'charfield').values()), [{
                'index': connection.vendor != 'postgresql',
                'primary_key': False,
                # The get_constraints() method doesn't correctly set `foreign_key`
                # to `False` on PostgreSQL.
                'foreign_key': None if connection.vendor == 'postgresql' else False,
                'unique': True,
                'check': False,
                'columns': ['charfield'],
            }])
            self.assertEqual(list(self.get_column_constraints(constraints, 'textfield').values()), [{
                'index': True,
                'primary_key': False,
                # The get_constraints() method doesn't correctly set `foreign_key`
                # to `False` on PostgreSQL.
                'foreign_key': None if connection.vendor == 'postgresql' else False,
                'unique': False,
                'check': False,
                'columns': ['textfield'],
            }])
            if connection.vendor == 'postgresql':
                self.assertEqual(list(self.get_column_constraints(constraints, 'positiveintegerfield').values()), [{
                    'index': False,
                    'primary_key': False,
                    # The get_constraints() method doesn't correctly set `foreign_key`
                    # to `False` on PostgreSQL.
                    'foreign_key': None if connection.vendor == 'postgresql' else False,
                    'unique': False,
                    'check': True,
                    'columns': ['positiveintegerfield'],
                }])
            foreign_key_constraints = list(self.get_column_constraints(constraints, 'foreign_key_id').values())
            expected_index = {
                'index': True,
                'primary_key': False,
                # The get_constraints() method doesn't correctly set `foreign_key`
                # to `False` on PostgreSQL.
                'foreign_key': None if connection.vendor == 'postgresql' else False,
                'unique': False,
                'check': False,
                'columns': ['foreign_key_id'],
            }
            for constraint in foreign_key_constraints:
                if constraint == expected_index:
                    break
            else:
                self.fail('Missing fk index.')
            if connection.vendor == 'postgresql':
                expected_fk = {
                    'index': False,
                    'primary_key': False,
                    'foreign_key': ('tests_addfield', 'id'),
                    'unique': False,
                    'check': False,
                    'columns': ['foreign_key_id'],
                }
                for constraint in foreign_key_constraints:
                    if constraint == expected_fk:
                        break
                else:
                    self.fail('Missing fk.')
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_addfield')
            self.assertEqual(len(self.get_tenant_table_columns(tenant, 'tests_addfield')), 1)

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.alter_field'})
    def test_alter_field(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        tenant_constraints = {}
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alterfield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_alterfield'), {
                'id', 'charfield', 'integerfield', 'foreign_key_id'
            })
            tenant_constraints[tenant.natural_key()] = self.get_tenant_table_constraints(tenant, 'tests_alterfield')
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alterfield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_alterfield'), {
                'id', 'charfield', 'integerfield', 'foreign_key_id'
            })
            constraints = self.get_tenant_table_constraints(tenant, 'tests_alterfield')
            charfield_constraints = list(self.get_column_constraints(constraints, 'charfield').values())
            self.assertIn({
                'index': connection.vendor != 'postgresql',
                'primary_key': False,
                # The get_constraints() method doesn't correctly set `foreign_key`
                # to `False` on PostgreSQL.
                'foreign_key': None if connection.vendor == 'postgresql' else False,
                'unique': True,
                'check': False,
                'columns': ['charfield'],
            }, charfield_constraints)
            if connection.vendor == 'postgresql' and django.VERSION >= (1, 8):
                self.assertIn({
                    'index': True,
                    'primary_key': False,
                    # The get_constraints() method doesn't correctly set `foreign_key`
                    # to `False` on PostgreSQL.
                    'foreign_key': None if connection.vendor == 'postgresql' else False,
                    'unique': False,
                    'check': False,
                    'columns': ['charfield'],
                }, charfield_constraints)
            if connection.vendor == 'postgresql':
                self.assertEqual(list(self.get_column_constraints(constraints, 'integerfield').values()), [{
                    'index': False,
                    'primary_key': False,
                    # The get_constraints() method doesn't correctly set `foreign_key`
                    # to `False` on PostgreSQL.
                    'foreign_key': None if connection.vendor == 'postgresql' else False,
                    'unique': False,
                    'check': True,
                    'columns': ['integerfield'],
                }])
            foreign_key_constraints = list(self.get_column_constraints(constraints, 'foreign_key_id').values())
            expected_index = {
                'index': True,
                'primary_key': False,
                # The get_constraints() method doesn't correctly set `foreign_key`
                # to `False` on PostgreSQL.
                'foreign_key': None if connection.vendor == 'postgresql' else False,
                'unique': False,
                'check': False,
                'columns': ['foreign_key_id'],
            }
            for constraint in foreign_key_constraints:
                if constraint == expected_index:
                    break
            else:
                self.fail('Missing fk index.')
            if connection.vendor == 'postgresql':
                expected_fk = {
                    'index': False,
                    'primary_key': False,
                    'foreign_key': ('tests_alterfield', 'id'),
                    'unique': False,
                    'check': False,
                    'columns': ['foreign_key_id'],
                }
                for constraint in foreign_key_constraints:
                    if constraint == expected_fk:
                        break
                else:
                    self.fail('Missing fk.')
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_alterfield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_alterfield'), {
                'id', 'charfield', 'integerfield', 'foreign_key_id'
            })
            self.assertEqual(
                self.get_tenant_table_constraints(tenant, 'tests_alterfield'),
                tenant_constraints[tenant.natural_key()],
            )

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.remove_field'})
    def test_remove_field(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_removefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_removefield'), {
                'id', 'charfield', 'foreign_key_id'
            })
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_removefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_removefield'), {'id'})
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_removefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_removefield'), {
                'id', 'charfield', 'foreign_key_id'
            })

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.rename_field'})
    def test_rename_field(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_renamefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_renamefield'), {
                'id', 'charfield', 'foreign_key_id'
            })
        call_command('migrate', 'tests', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_renamefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_renamefield'), {
                'id', 'renamed_charfield', 'renamed_foreign_key_id'
            })
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            self.assertTenantTableExists(tenant, 'tests_renamefield')
            self.assertEqual(self.get_tenant_table_column_names(tenant, 'tests_renamefield'), {
                'id', 'charfield', 'foreign_key_id'
            })

    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.run_python'})
    def test_run_python(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runpython')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (0,))
        call_command('migrate', 'tests', '0002', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runpython')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (1,))
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runpython')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (0,))

    @unittest.skipIf(connection.vendor == 'sqlite', 'Cannot use RunSQL on SQLite.')
    @override_settings(MIGRATION_MODULES={'tests': 'tests.test_operations_migrations.run_sql'})
    def test_run_sql(self):
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runsql')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (0,))
        call_command('migrate', 'tests', '0002', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runsql')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (1,))
        call_command('migrate', 'tests', '0001', interactive=False, stdout=StringIO())
        for tenant in Tenant.objects.all():
            table_name = self.get_tenant_table_name(tenant, 'tests_runsql')
            with self.tenant_connection_context(tenant) as cursor:
                cursor.execute("SELECT COUNT(*) FROM %s" % table_name)
                self.assertEqual(cursor.fetchone(), (0,))
