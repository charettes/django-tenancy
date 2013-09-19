from __future__ import unicode_literals

import sys
# TODO: Remove when support for Python 2.6 is dropped
if sys.version_info >= (2, 7):
    from unittest import skipUnless
else:
    from django.utils.unittest import skipUnless

from django.db import connection, connections, router, transaction
from django.db.utils import DatabaseError
from django.core.management import call_command
from django.core.management.base import CommandError
# TODO: Remove when support for Django 1.5 is dropped
try:
    from django.db.transaction import atomic
except ImportError:
    from django.db.transaction import commit_on_success as atomic
from django.test.testcases import TransactionTestCase
from django.utils.six import StringIO

from ..models import Tenant, TenantModelBase
from ..signals import pre_schema_creation, post_schema_deletion
from ..utils import allow_migrate

from .utils import (mock_inputs, setup_custom_tenant_user, skipIfCustomTenant,
    TenancyTestCase)


@skipIfCustomTenant
class CreateTenantCommandTest(TransactionTestCase):
    def test_too_many_fields(self):
        args = ('name', 'useless')
        expected_message = (
            "Number of args exceeds the number of fields for model tenancy.Tenant.\n"
            "Got %s when defined fields are ('name',)." % repr(args)
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            call_command('createtenant', *args)

    def test_full_clean_failure(self):
        expected_message = (
            'Invalid value for field "name": This field cannot be blank.'
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            call_command('createtenant')

    def test_success(self):
        call_command('createtenant', 'tenant', verbosity=0)
        Tenant.objects.get(name='tenant').delete()

    def test_verbosity(self):
        stdout = StringIO()
        call_command('createtenant', 'tenant', stdout=stdout, verbosity=3)
        tenant = Tenant.objects.get(name='tenant')
        stdout.seek(0)
        connection = connections[tenant._state.db]
        if connection.vendor == 'postgresql':
            self.assertIn(tenant.db_schema, stdout.readline())
        for model in TenantModelBase.references:
            self.assertIn(model._meta.object_name, stdout.readline())
            self.assertIn(model._meta.db_table, stdout.readline())
        self.assertIn('Installing indexes ...', stdout.readline())
        tenant.delete()

    @setup_custom_tenant_user
    @mock_inputs((
        ('\nYou just created a new tenant,', 'yes'),
        ('Email', 'bleh@teant.test.ca'),
        ('Password', '1234')
    ))
    def test_superuser_creation_prompt(self):
        stdout = StringIO()
        call_command('createtenant', 'tenant', stdout=stdout, interactive=True)
        stdout.seek(0)
        self.assertIn('Superuser created successfully.', stdout.read())
        Tenant.objects.get(name='tenant').delete()

    @setup_custom_tenant_user
    @mock_inputs((
        ('\nYou just created a new tenant,', 'no'),
    ))
    def test_superuser_creation_prompt(self):
        stdout = StringIO()
        call_command('createtenant', 'tenant', stdout=stdout, interactive=True)
        stdout.seek(0)
        self.assertNotIn('Superuser created successfully.', stdout.read())
        Tenant.objects.get(name='tenant').delete()


@skipUnless(
    connection.vendor == 'postgresql',
    'Schema authorization is only supported on PostgreSQL.'
)
class SchemaAuthorizationTest(TenancyTestCase):
    def setUp(self):
        pre_schema_creation.connect(self.create_tenant_role, sender=Tenant)
        with self.settings(TENANCY_SCHEMA_AUTHORIZATION=True):
            super(SchemaAuthorizationTest, self).setUp()
        pre_schema_creation.disconnect(self.create_tenant_role, sender=Tenant)

    def tearDown(self):
        post_schema_deletion.connect(self.drop_tenant_role, sender=Tenant)
        super(SchemaAuthorizationTest, self).tearDown()
        post_schema_deletion.disconnect(self.drop_tenant_role, sender=Tenant)

    @atomic
    def create_tenant_role(self, tenant, using, **kwargs):
        connection = connections[using]
        connection.cursor().execute(
            "CREATE ROLE %s" % connection.ops.quote_name(tenant.db_schema)
        )

    @atomic
    def drop_tenant_role(self, tenant, using, **kwargs):
        connection = connections[using]
        connection.cursor().execute(
            "DROP ROLE %s" % connection.ops.quote_name(tenant.db_schema)
        )

    def test_owner(self):
        """
        Make sure schema and table owner is correctly assigned.
        """
        for db in allow_migrate(Tenant):
            connection = connections[db]
            cursor = connection.cursor()
            for tenant in Tenant.objects.all():
                schema = tenant.db_schema
                cursor.execute(
                    "SELECT rolname FROM pg_namespace "
                    "INNER JOIN pg_roles ON pg_namespace.nspowner = pg_roles.oid "
                    "WHERE nspname = %s",
                    [schema]
                )
                schema_owner, = cursor.cursor.fetchone()
                self.assertEqual(schema_owner, schema)
                cursor.execute(
                    "SELECT tableowner FROM pg_tables WHERE schemaname = %s",
                    [schema]
                )
                for table_owner, in cursor.cursor.fetchall():
                    self.assertEqual(table_owner, schema)

    def test_permission_denied(self):
        """
        Make sure schemas are restricted to their associated role.
        """
        db = router.db_for_read(Tenant)
        connection = connections[db]
        quote_name = connection.ops.quote_name
        cursor = connection.cursor()
        for tenant in Tenant.objects.all():
            sid = transaction.savepoint(db)
            other_tenant = Tenant.objects.exclude(pk=tenant.pk).get()
            cursor.execute("SET ROLE %s" % quote_name(other_tenant.db_schema))
            with self.assertRaisesMessage(DatabaseError, 'permission denied'):
                tenant.specificmodels.count()
            transaction.savepoint_rollback(sid, db)
            cursor.execute('RESET ROLE')
            transaction.commit(db)
