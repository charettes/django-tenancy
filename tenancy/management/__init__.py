from __future__ import unicode_literals
import logging

import django
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.core.management.color import no_style
from django.db import connections, models, router, transaction
from django.db.models.fields.related import add_lazy_relation
from django.db.models.signals import class_prepared
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict

from ..models import TenantModelBase
from ..settings import TENANT_MODEL
from ..signals import LazySignalConnector
from ..utils import (allow_syncdbs, clear_opts_related_cache,
    disconnect_signals, receivers_for_model, remove_from_app_cache)


def get_tenant_models(tenant):
    models = []
    for model in TenantModelBase.references:
        models.append(model.for_tenant(tenant))
    return models


tenant_model_receiver = LazySignalConnector(*TENANT_MODEL.split('.'))


@tenant_model_receiver(models.signals.post_save)
def create_tenant_schema(sender, instance, created, using, **kwargs):
    """
    CREATE the tables associated with a tenant's models.
    """
    logger = logging.getLogger('tenancy.management.create_tenant_schema')
    if created:
        connection = connections[using]
        if connection.vendor == 'postgresql':  #pragma: no cover
            db_schema = instance.db_schema
            quoted_db_schema = connection.ops.quote_name(db_schema)
            connection.cursor().execute("CREATE SCHEMA %s" % quoted_db_schema)
            logger.info("Creating schema %s ..." % db_schema)
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
        index_sql = SortedDict()
        if connection.vendor == 'postgresql':  #pragma: no cover
            index_prefix = "%s." % quoted_db_schema
        for model in get_tenant_models(instance):
            opts = model._meta
            ContentType.objects.get_for_model(model)
            for db in allow_syncdbs(model):
                connection = connections[db]
                logger.debug("Processing %s.%s model" % (opts.app_label, opts.object_name))
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
            index_sql[model] = connection.creation.sql_indexes_for_model(model, style)
            if connection.vendor == 'postgresql':  #pragma: no cover
                table_name = "%s.%s"  % (db_schema, model._for_tenant_model._meta.db_table)
                for i, statement in enumerate(index_sql[model]):
                    index_sql[model][i] = statement.replace(index_prefix, '', 1)
            else:  #pragma: no cover
                table_name = opts.db_table
            logger.info("Creating table %s ..." % table_name)

        for db in connections:
            transaction.commit_unless_managed(db)

        logger.info('Installing indexes ...')
        for model, statements in index_sql.items():
            if statements:
                for db in allow_syncdbs(model):
                    connection = connections[db]
                    cursor = connection.cursor()
                    try:
                        for statement in statements:
                            cursor.execute(statement)
                    except Exception as e:
                        logger.exception(e)
                        transaction.rollback_unless_managed(using=db)
                    else:
                        transaction.commit_unless_managed(using=db)


@tenant_model_receiver(models.signals.pre_delete)
def collect_tenant_models(sender, instance, using, **kwargs):
    """
    Collect tenant models prior to tenant deletion.
    """
    instance._state._deletion_tenant_models = get_tenant_models(instance)


@tenant_model_receiver(models.signals.post_delete)
def drop_tenant_schema(sender, instance, using, **kwargs):
    """
    DROP the tables associated with a tenant's models.
    """
    connection = connections[using]
    quote_name = connection.ops.quote_name
    tenant_models = instance._state._deletion_tenant_models
    del instance._state._deletion_tenant_models
    if connection.vendor == 'postgresql':  #pragma: no cover
        connection.cursor().execute(
            "DROP SCHEMA %s CASCADE" % quote_name(instance.db_schema)
        )
    else:  #pragma: no cover
        for model in tenant_models:
            opts = model._meta
            if not opts.managed or opts.proxy:
                continue
            table_name = quote_name(opts.db_table)
            for db in allow_syncdbs(model):
                connections[db].cursor().execute("DROP TABLE %s" % table_name)
    ContentType.objects.filter(model__startswith=instance.model_name_prefix.lower()).delete()
    ContentType.objects.clear_cache()
    for model in tenant_models:
        remove_from_app_cache(model)
        disconnect_signals(model)
        related_fields = [
            field for field in model._meta.local_fields if field.rel
        ] + model._meta.local_many_to_many
        for field in related_fields:
            to = field.rel.to
            if not isinstance(to, TenantModelBase):
                clear_opts_related_cache(to)
                if not field.rel.is_hidden():
                    delattr(to, field.related.get_accessor_name())


@receiver(models.signals.class_prepared)
def attach_signals(signal, sender, **kwargs):
    """
    Re-attach signals to tenant models
    """
    if isinstance(sender, TenantModelBase) and sender._meta.managed:
        for signal, receiver in receivers_for_model(sender._for_tenant_model):
            signal.connect(receiver, sender=sender)


def validate_not_to_tenant_model(field, to, model):
    """
    Make sure the `to` relationship is not pointing to an instance of
    `TenantModelBase`.
    """
    if isinstance(to, basestring):
        add_lazy_relation(model, field, to, validate_not_to_tenant_model)
    elif isinstance(to, TenantModelBase):
        remove_from_app_cache(model)
        raise ImproperlyConfigured(
            "`%s.%s`'s `to` option` can't point to an instance of "
            "`TenantModelBase` since it's not one itself." % (
                model.__name__, field.name
            )
        )


@receiver(models.signals.class_prepared)
def validate_relationships(signal, sender, **kwargs):
    """
    Non-tenant models can't have relationships pointing to tenant models.
    """
    if not isinstance(sender, TenantModelBase):
        opts = sender._meta
        # Don't validate auto-intermediary models since they are created
        # before their origin model (from) and cloak the actual, user-defined
        # improper configuration.
        if not opts.auto_created:
            for field in opts.local_fields:
                if field.rel:
                    validate_not_to_tenant_model(field, field.rel.to, sender)
            for m2m in opts.local_many_to_many:
                validate_not_to_tenant_model(m2m, m2m.rel.to, sender)
