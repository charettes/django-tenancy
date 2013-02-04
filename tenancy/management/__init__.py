from __future__ import unicode_literals

import django
from django.contrib.contenttypes.models import ContentType
from django.core.management.color import no_style
from django.db import connections, models, router, transaction
from django.dispatch.dispatcher import _make_id, receiver
from django.utils.datastructures import SortedDict

from .. import get_tenant_model
from ..models import TenantModelBase


def allow_syncdbs(model):
    for db in connections:
        if router.allow_syncdb(db, model):
            yield db


@receiver(models.signals.post_save, sender=get_tenant_model())
def create_tenant_schema(sender, instance, created, using, **kwargs):
    """
    CREATE the tables associated with a tenant's models.
    """
    if created:
        connection = connections[using]
        if connection.vendor == 'postgresql':
            schema = connection.ops.quote_name(instance.db_schema)
            connection.cursor().execute("CREATE SCHEMA %s" % schema)
        # Here we don't use south's API to avoid detecting things such
        # as `unique_together` and `index_together` (which are set on the
        # abstract base) and manually calling `create_index`.
        # This code is heavily inspired by the `syncdb` command and wouldn't
        # be required if we could specify models to be "synced" to the command.
        style = no_style()
        seen_models = dict(
            (db, connections[db].introspection.installed_models(tables))
            for db, tables in (
                (db, connections[db].introspection.table_names())
                for db in connections
            )
        )
        created_models = dict((db, set()) for db in connections)
        pending_references = dict((db, {}) for db in connections)
        for model in instance.models.values():
            for db in allow_syncdbs(model):
                connection = connections[db]
                sql, references = connection.creation.sql_create_model(model, style, seen_models)
                seen_models[db].add(model)
                created_models[db].add(model)
                for refto, refs in references.items():
                    pending_references[db].setdefault(refto, []).extend(refs)
                    if refto in seen_models[db]:
                        sql.extend(connection.creation.sql_for_pending_references(refto, style, pending_references[db]))
                sql.extend(connection.creation.sql_for_pending_references(model, style, pending_references[db]))
                cursor = connection.cursor()
                for statement in sql:
                    cursor.execute(statement)
        for db in connections:
            transaction.commit_unless_managed(db)


@receiver(models.signals.post_delete, sender=get_tenant_model())
def drop_tenant_schema(sender, instance, using, **kwargs):
    """
    DROP the tables associated with a tenant's models.
    """
    connection = connections[using]
    quote_name = connection.ops.quote_name
    if connection.vendor == 'postgresql':
        connection.cursor().execute(
            "DROP SCHEMA %s CASCADE" % quote_name(instance.db_schema)
        )
    else:
        for model in instance.models.values():
            table_name = quote_name(model._meta.db_table)
            for db in allow_syncdbs(model):
                connections[db].cursor().execute("DROP TABLE %s" % table_name)
    ContentType.objects.clear_cache()


model_sender_signals = (
    models.signals.pre_init,
    models.signals.post_init,
    models.signals.pre_save,
    models.signals.post_save,
    models.signals.pre_delete,
    models.signals.post_delete,
)

@receiver(models.signals.class_prepared)
def attach_signals(signal, sender, **kwargs):
    """
    Re-attach signals to tenant models
    """
    if isinstance(sender, TenantModelBase) and sender._meta.managed:
        sender_id = _make_id(sender.__bases__[0])
        for signal in model_sender_signals:
            for receiver in signal._live_receivers(sender_id):
                signal.connect(receiver, sender=sender)