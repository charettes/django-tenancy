from __future__ import unicode_literals

from contextlib import contextmanager
from functools import partial

from django.apps import apps
from django.db.backends.utils import truncate_name
from django.db.migrations import operations
from django.db.migrations.operations.base import Operation
from django.utils import six
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
        db_schema = tenant.db_schema
        if connection.vendor == 'postgresql':
            sql = "SET search_path = %s, public" % schema_editor.connection.ops.quote_name(tenant.db_schema)
            cursor.execute(sql)
            schema_editor.deferred_sql.append(sql)
        with patch_connection_introspection(connection, db_schema):
            setattr(schema_editor, 'tenant', tenant)
            try:
                yield
            finally:
                delattr(schema_editor, 'tenant')
        if connection.vendor == 'postgresql':
            sql = 'RESET search_path'
            cursor.execute(sql)
            schema_editor.deferred_sql.append(sql)

    def _create_managed_state(self, tenant_model, connection, state):
        managed = Managed("%s.%s" % (tenant_model._meta.app_label, tenant_model._meta.object_name))
        state.__dict__.pop('apps', None)
        project_state = state.clone()
        managed_models = []
        for model_key, model_state in iteritems(project_state.models):
            options = model_state.options
            if options.get('managed') == managed:
                db_table = options.get('db_table')
                if not db_table:
                    db_table = truncate_name("%s_%s" % model_key, connection.ops.max_name_length())
                options.update(
                    managed=True,
                    db_table=db_table,
                )
                managed_models.append(model_key)
        return project_state, managed_models

    def _create_tenant_state(self, tenant, connection, state, managed_models):
        if not managed_models or connection.vendor == 'postgresql':
            return state
        project_state = state.clone()
        for model_key in managed_models:
            model_state = project_state.models[model_key]
            model_state.options['db_table'] = db_schema_table(tenant, model_state.options['db_table'])
        return project_state

    def tenant_operation(self, tenant_model, operation, app_label, schema_editor, from_state, to_state):
        connection = schema_editor.connection
        global_tenant_model = apps.get_model(tenant_model._meta.app_label, tenant_model._meta.model_name)
        get_db_schema = global_tenant_model.db_schema.fget
        get_natural_key = global_tenant_model.natural_key
        if six.PY2:
            get_natural_key = get_natural_key.im_func
        tenants = list(tenant_model._base_manager.all())
        # Small optimization to avoid creating model states if not required.
        if tenants:
            managed_from = self._create_managed_state(tenant_model, connection, from_state)
            managed_to = self._create_managed_state(tenant_model, connection, to_state)
            for tenant in tenants:
                tenant.natural_key = partial(get_natural_key, tenant)
                tenant.db_schema = get_db_schema(tenant)
                tenant_from_state = self._create_tenant_state(tenant, connection, *managed_from)
                tenant_to_state = self._create_tenant_state(tenant, connection, *managed_to)
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
        return from_state.apps.get_model(managed.tenant_model)


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
        opts = self.tenant_model._meta
        return from_state.apps.get_model(opts.app_label, opts.model_name)


class RunPython(TenantSpecialOperation, operations.RunPython):
    pass


class RunSQL(TenantSpecialOperation, operations.RunSQL):
    pass
