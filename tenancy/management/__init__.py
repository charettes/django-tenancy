from __future__ import unicode_literals

import logging
import re

from django.contrib.contenttypes.models import ContentType
from django.db import connections, router

from .. import signals
from ..compat import get_remote_field


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

    signals.pre_models_creation.send(
        sender=tenant_class, tenant=tenant, using=using
    )

    with connection.schema_editor() as editor:
        for model in tenant.models:
            # Has the side effect of creating the required `ContentType`.
            ContentType.objects.get_for_model(model)
            # Avoid further processing we're dealing with an unmanaged model or
            # one proxying another.
            opts = model._meta
            if not opts.managed or opts.proxy or opts.auto_created:
                continue
            if not router.allow_migrate(connection.alias, model):
                continue
            logger.debug(
                "Processing %s.%s model" % (opts.app_label, opts.object_name)
            )
            if connection.vendor == 'postgresql':
                table_name = "%s.%s" % (
                    schema, model._for_tenant_model._meta.db_table
                )
            else:
                table_name = opts.db_table
            logger.info("Creating table %s ..." % table_name)
            for m2m in opts.many_to_many:
                through_opts = get_remote_field(m2m).through._meta
                if through_opts.auto_created:
                    logger.info("Creating table %s ..." % through_opts.db_table)
            editor.create_model(model)
            if connection.vendor == 'postgresql' and SCHEMA_AUTHORIZATION:
                quoted_tables = [quote_name(opts.db_table)] + [
                    quote_name(get_remote_field(m2m).through._meta.db_table)
                    for m2m in opts.many_to_many if through_opts.auto_created
                ]
                editor.deferred_sql.extend(
                    "ALTER TABLE %s OWNER TO %s" % (
                        quoted_table, quoted_schema
                    ) for quoted_table in quoted_tables
                )
        if connection.vendor == 'postgresql':
            altered_statements = []
            # Our "db_table" hack to allow specifying a schema interferes with
            # index and constraint creation.
            create_index_re = re.compile('CREATE INDEX %s' % re.escape("%s." % quoted_schema))
            add_constraint_re = re.compile('ADD CONSTRAINT "([^"]+)"\."([^"]+)"')
            for statement in editor.deferred_sql:
                if statement.startswith('CREATE INDEX'):
                    statement = create_index_re.sub('CREATE INDEX ', statement)
                elif 'ADD CONSTRAINT' in statement:
                    statement = add_constraint_re.sub('ADD CONSTRAINT "\g<1>_\g<2>"', statement)
                altered_statements.append(statement)
            editor.deferred_sql = altered_statements

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
        with connection.schema_editor() as editor:
            for model in tenant.models:
                opts = model._meta
                if not opts.managed or opts.proxy or opts.auto_created:
                    continue
                if not router.allow_migrate(connection.alias, model):
                    continue
                editor.delete_model(model)

    tenant._default_manager._remove_from_cache(tenant)
    ContentType.objects.clear_cache()

    signals.post_schema_deletion.send(
        sender=tenant_class, tenant=tenant, using=using
    )
