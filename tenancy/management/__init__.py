from __future__ import unicode_literals

import logging

import django
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.core.management.color import no_style
from django.db import connections, models, router, transaction
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict

from ..signals import (post_tenant_models_creation, pre_tenant_models_creation,
    pre_tenant_schema_deletion)
from ..utils import (allow_syncdbs, disconnect_signals, receivers_for_model,
    remove_from_app_cache)


def create_tenant_schema(tenant, using=None):
    """
    CREATE the tables associated with a tenant's models.
    """
    logger = logging.getLogger('tenancy.management.create_tenant_schema')
    tenant._default_manager._add_to_cache(tenant)
    using = using or router.db_for_write(tenant.__class__, instance=tenant)
    connection = connections[using]
    if connection.vendor == 'postgresql':  # pragma: no cover
        db_schema = tenant.db_schema
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
    if connection.vendor == 'postgresql':  # pragma: no cover
        index_prefix = "%s." % quoted_db_schema

    # Send pre creation signal
    sender = tenant.__class__
    pre_tenant_models_creation.send(
        sender=sender, tenant=tenant, using=using
    )

    for model in tenant.models:
        opts = model._meta
        ContentType.objects.get_for_model(model)
        for db in allow_syncdbs(model):
            connection = connections[db]
            logger.debug(
                "Processing %s.%s model" % (opts.app_label, opts.object_name)
            )
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
            cursor = connection.cursor()
            for statement in sql:
                cursor.execute(statement)
        index_sql[model] = connection.creation.sql_indexes_for_model(
            model, style
        )
        if connection.vendor == 'postgresql':  # pragma: no cover
            table_name = "%s.%s" % (
                db_schema, model._for_tenant_model._meta.db_table
            )
            for i, statement in enumerate(index_sql[model]):
                index_sql[model][i] = statement.replace(index_prefix, '', 1)
        else:  # pragma: no cover
            table_name = opts.db_table
        logger.info("Creating table %s ..." % table_name)

    # Send post creation signal
    post_tenant_models_creation.send(
        sender=sender, tenant=tenant, using=using
    )

    logger.info('Installing indexes ...')
    for model, statements in index_sql.items():
        if statements:
            for db in allow_syncdbs(model):
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


def drop_tenant_schema(tenant, using=None):
    """
    DROP the tables associated with a tenant's models.
    """
    using = using or router.db_for_write(tenant.__class__, instance=tenant)
    connection = connections[using]
    quote_name = connection.ops.quote_name

    # Send pre schema deletion signal
    pre_tenant_schema_deletion.send(
        sender=tenant.__class__, tenant=tenant, using=using
    )

    if connection.vendor == 'postgresql':  # pragma: no cover
        connection.cursor().execute(
            "DROP SCHEMA %s CASCADE" % quote_name(tenant.db_schema)
        )
    else:  # pragma: no cover
        for model in tenant.models:
            opts = model._meta
            if not opts.managed or opts.proxy:
                continue
            table_name = quote_name(opts.db_table)
            for db in allow_syncdbs(model):
                connections[db].cursor().execute("DROP TABLE %s" % table_name)
    ContentType.objects.filter(
        model__startswith=tenant.model_name_prefix.lower()
    ).delete()
    ContentType.objects.clear_cache()
    tenant._default_manager._remove_from_cache(tenant)
