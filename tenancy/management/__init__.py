from __future__ import unicode_literals

# TODO: Remove when support for Python 2.6 is dropped
try:
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict
import logging

import django
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.core.management.color import no_style
from django.db import connections, models, router, transaction
from django.dispatch.dispatcher import receiver

from .. import signals
from ..utils import (allow_migrate, disconnect_signals, receivers_for_model,
    remove_from_app_cache)


def create_tenant_schema(tenant, using=None):
    """
    CREATE the tables associated with a tenant's models.
    """
    logger = logging.getLogger('tenancy.management.create_tenant_schema')
    tenant_class = tenant.__class__
    using = using or router.db_for_write(tenant_class, instance=tenant)
    connection = connections[using]
    quote_name = connection.ops.quote_name

    tenant_class._default_manager._add_to_cache(tenant)

    signals.pre_schema_creation.send(
        sender=tenant_class, tenant=tenant, using=using
    )

    if connection.vendor == 'postgresql':
        schema = tenant.db_schema
        quoted_schema = quote_name(schema)
        from ..settings import SCHEMA_AUTHORIZATION
        if SCHEMA_AUTHORIZATION:
            create_schema = "CREATE SCHEMA AUTHORIZATION %s"
        else:
            create_schema = "CREATE SCHEMA %s"
        logger.info("Creating schema %s ..." % schema)
        connection.cursor().execute(create_schema % quoted_schema)

    signals.post_schema_creation.send(
        sender=tenant_class, tenant=tenant, using=using
    )

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
    index_sql = OrderedDict()
    if connection.vendor == 'postgresql':
        index_prefix = "%s." % quoted_schema

    signals.pre_models_creation.send(
        sender=tenant_class, tenant=tenant, using=using
    )

    for model in tenant.models:
        opts = model._meta
        logger.debug(
            "Processing %s.%s model" % (opts.app_label, opts.object_name)
        )
        # Has the side effect of creating the required `ContentType`.
        ContentType.objects.get_for_model(model)
        # Store index required for this model to be created later on.
        index_sql[model] = connection.creation.sql_indexes_for_model(
            model, style
        )
        if connection.vendor == 'postgresql':
            table_name = "%s.%s" % (
                schema, model._for_tenant_model._meta.db_table
            )
            for i, statement in enumerate(index_sql[model]):
                index_sql[model][i] = statement.replace(index_prefix, '', 1)
        else:
            table_name = opts.db_table
        quoted_table_name = quote_name(opts.db_table)
        for db in allow_migrate(model):
            logger.info("Creating table %s ..." % table_name)
            connection = connections[db]
            sql, references = connection.creation.sql_create_model(
                model, style, seen_models
            )
            seen_models[db].add(model)
            created_models[db].add(model)
            for refto, refs in references.items():
                pending_references[db].setdefault(refto, []).extend(refs)
                if refto in seen_models[db]:
                    sql.extend(
                        connection.creation.sql_for_pending_references(
                            refto, style, pending_references[db]
                        )
                    )
            sql.extend(
                connection.creation.sql_for_pending_references(
                    model, style, pending_references[db]
                )
            )
            if connection.vendor == 'postgresql' and SCHEMA_AUTHORIZATION:
                sql.append(
                    "ALTER TABLE %s OWNER TO %s" % (
                        quoted_table_name, quoted_schema
                    )
                )
            cursor = connection.cursor()
            for statement in sql:
                cursor.execute(statement)

    logger.info('Installing indexes ...')
    for model, statements in index_sql.items():
        if statements:
            for db in allow_migrate(model):
                connection = connections[db]
                sid = transaction.savepoint(db)
                cursor = connection.cursor()
                try:
                    for statement in statements:
                        cursor.execute(statement)
                except Exception:
                    opts = model._meta
                    logger.exception(
                        "Failed to install index for %s.%s model." % (
                            opts.app_label, opts.object_name
                        )
                    )
                    transaction.savepoint_rollback(sid, db)
                else:
                    transaction.savepoint_commit(sid, db)

    signals.post_models_creation.send(
        sender=tenant_class, tenant=tenant, using=using
    )


def drop_tenant_schema(tenant, using=None):
    """
    DROP the tables associated with a tenant's models.
    """
    tenant_class = tenant.__class__
    using = using or router.db_for_write(tenant_class, instance=tenant)
    connection = connections[using]
    quote_name = connection.ops.quote_name

    signals.pre_schema_deletion.send(
        sender=tenant_class, tenant=tenant, using=using
    )

    ContentType.objects.filter(
        pk__in=[
            ct.pk for ct in ContentType.objects.get_for_models(
                *tenant.models, for_concrete_models=False
            ).values()
        ]
    ).delete()

    if connection.vendor == 'postgresql':
        connection.cursor().execute(
            "DROP SCHEMA %s CASCADE" % quote_name(tenant.db_schema)
        )
    else:
        for model in tenant.models:
            opts = model._meta
            if not opts.managed or opts.proxy:
                continue
            table_name = quote_name(opts.db_table)
            for db in allow_migrate(model):
                connections[db].cursor().execute("DROP TABLE %s" % table_name)

    tenant._default_manager._remove_from_cache(tenant)
    ContentType.objects.clear_cache()

    # TODO: Remove when support for Django 1.5 is dropped
    if django.VERSION < (1, 6):
        transaction.commit_unless_managed()

    signals.post_schema_deletion.send(
        sender=tenant_class, tenant=tenant, using=using
    )
