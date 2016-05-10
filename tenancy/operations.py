from __future__ import unicode_literals

from contextlib import contextmanager

from django.apps import apps
from django.db.backends.utils import truncate_name
from django.db.migrations import operations
from django.db.migrations.operations.base import Operation
from django.utils.six import iteritems

from .models import Managed, db_schema_table
from .utils import patch_connection_introspection


class TenantOperation(Operation):
    def get_tenant_model(self, app_label, from_state, to_state):
        raise NotImplementedError

    @contextmanager
    def tenant_context(self, tenant, schema_editor):
        connection = schema_editor.connection
        cursor = connection.cursor()
        if connection.vendor == 'postgresql':
            sql = "SET search_path = %s, public" % tenant.db_schema
            cursor.execute(sql)
            schema_editor.deferred_sql.append(sql)
        with patch_connection_introspection(connection):
            yield
        if connection.vendor == 'postgresql':
            sql = 'RESET search_path'
            cursor.execute(sql)
            schema_editor.deferred_sql.append(sql)

    def create_tenant_project_state(self, tenant, state, connection):
        managed = Managed("%s.%s" % (tenant._meta.app_label, tenant._meta.object_name))
        project_state = state.clone()
        for (app_label, model_name), model_state in iteritems(project_state.models):
            options = model_state.options
            if options.get('managed') == managed:
                db_table = options.get('db_table')
                if not db_table:
                    db_table = truncate_name("%s_%s" % (app_label, model_name), connection.ops.max_name_length())
                if not connection.vendor == 'postgresql':
                    db_table = db_schema_table(tenant, db_table)
                options.update(
                    managed=True,
                    db_table=db_table,
                )
            project_state.reload_model(app_label, model_name)
        return project_state

    def tenant_operation(self, tenant_model, operation, app_label, schema_editor, from_state, to_state):
        connection = schema_editor.connection
        for tenant in tenant_model._base_manager.all():
            tenant_from_state = self.create_tenant_project_state(tenant, from_state, connection)
            tenant_to_state = self.create_tenant_project_state(tenant, to_state, connection)
            with self.tenant_context(tenant, schema_editor):
                operation(app_label, schema_editor, tenant_from_state, tenant_to_state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        tenant_model = self.get_tenant_model(app_label, from_state, to_state)
        operation = super(TenantOperation, self).database_forwards
        self.tenant_operation(tenant_model, operation, app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        tenant_model = self.get_tenant_model(app_label, to_state, from_state)
        operation = super(TenantOperation, self).database_backwards
        self.tenant_operation(tenant_model, operation, app_label, schema_editor, from_state, to_state)


class TenantModelOperation(TenantOperation):
    def get_operation_model_state(self, app_label, from_state, to_state):
        return to_state.models[app_label, self.name_lower]

    def get_tenant_model(self, app_label, from_state, to_state):
        model_state = self.get_operation_model_state(app_label, from_state, to_state)
        managed = model_state.options.get('managed')
        return apps.get_model(managed.tenant_model)


class CreateModel(TenantModelOperation, operations.CreateModel):
    pass


class DeleteModel(TenantModelOperation, operations.DeleteModel):
    def get_operation_model_state(self, app_label, from_state, to_state):
        return from_state.models[app_label, self.name_lower]


class RenameModel(TenantModelOperation, operations.RenameModel):
    def get_operation_model_state(self, app_label, from_state, to_state):
        return from_state.models[app_label, self.old_name_lower]

    database_backwards = operations.RenameModel.database_backwards


class AlterModelTable(TenantModelOperation, operations.AlterModelTable):
    database_backwards = operations.AlterModelTable.database_backwards


class AlterUniqueTogether(TenantModelOperation, operations.AlterUniqueTogether):
    database_backwards = operations.AlterUniqueTogether.database_backwards


class AlterIndexTogether(TenantModelOperation, operations.AlterIndexTogether):
    database_backwards = operations.AlterIndexTogether.database_backwards


class TenantModelFieldOperation(TenantModelOperation):
    def get_operation_model_state(self, app_label, from_state, to_state):
        return from_state.models[app_label, self.model_name_lower]


class AddField(TenantModelFieldOperation, operations.AddField):
    pass


class RemoveField(TenantModelFieldOperation, operations.RemoveField):
    pass


class AlterField(TenantModelFieldOperation, operations.AlterField):
    database_backwards = operations.AlterField.database_backwards


class RenameField(TenantModelFieldOperation, operations.RenameField):
    pass


class TenantSpecialOperation(TenantOperation):
    def __init__(self, tenant_model, *args, **kwargs):
        self.tenant_model = tenant_model
        super(TenantSpecialOperation, self).__init__(*args, **kwargs)

    def get_tenant_model(self, app_label, from_state, to_state):
        return self.tenant_model


class RunPython(TenantSpecialOperation, operations.RunPython):
    pass


class RunSQL(TenantSpecialOperation, operations.RunSQL):
    pass
