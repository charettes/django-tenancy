from __future__ import unicode_literals

from django.contrib.contenttypes.models import ContentType
from django.core.management.color import no_style
from django.db import connections, models, router, transaction
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict


class Tenant(models.Model):
    _related_names = []

    name = models.CharField(unique=True, max_length=20)

    def natural_key(self):
        return (self.name,)

    @property
    def models(self):
        return SortedDict(
            (related_name, getattr(self, related_name).model)
            for related_name in self._related_names
        )

    @property
    def db_schema(self):
        return "tenant_%s" % self.name


def allow_syncdbs(model):
    for db in connections:
        if router.allow_syncdb(db, model):
            yield db


@receiver(models.signals.post_save, sender=Tenant)
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


@receiver(models.signals.post_delete, sender=Tenant)
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


class TenantOptions(object):
    def __init__(self, base, related_name):
        self.base = base
        self.related_name = related_name


def meta(**opts):
    """
    Create a class with specified opts as attributes to be used as model
    definition options.
    """
    return type(str('Meta'), (), opts)


class TenantModelBase(models.base.ModelBase):
    tenant_model_class = None

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        Meta = attrs.setdefault('Meta', meta())
        # It's a concrete or proxy model
        if not getattr(Meta, 'abstract', False):
            Meta.abstract = True
            module = attrs.get('__module__')
            # Create an abstract base to hold attributes
            base = super_new(cls, str("Abstract%s" % name), (models.Model,), attrs)
            try:
                related_name = base.TenantMeta.related_name
            except AttributeError:
                related_name = name.lower() + 's'
            tenant_opts = TenantOptions(base, related_name)
            model = super_new(cls, name, (base,) + bases, {'__module__': module,
                                                           '_tenant_meta': tenant_opts,
                                                           'Meta': meta(managed=False)})
            # Attach a descriptor to the tenant model to access the underlying
            # model based on the tenant instance.
            def type_(tenant, **attrs):
                attrs.update(
                    tenant=tenant,
                    __module__=module,
                    _tenant_meta=tenant_opts
                )
                type_bases = tuple(
                    getattr(tenant, b._tenant_meta.related_name).model if isinstance(b, cls) else b
                    for b in bases if b is not cls.tenant_model_class
                )
                return super_new(cls, name, (base,) + type_bases, attrs)
            descriptor = TenantModelDescriptor(type_, model._meta)
            Tenant._related_names.append(related_name)
            setattr(Tenant, related_name, descriptor)
        else:
            model = super_new(cls, name, bases, attrs)
        if cls.tenant_model_class is None:
            cls.tenant_model_class = model
        return model

    def __instancecheck__(self, instance):
        return self.__subclasscheck__(instance.__class__)

    def __subclasscheck__(self, subclass):
        if isinstance(subclass, TenantModelBase):
            try:
                return subclass._tenant_meta is self._tenant_meta
            except AttributeError:
                pass


class TenantModelDescriptor(object):
    def __init__(self, type_, opts):
        self.type = type_
        self.opts = opts

    def __get__(self, instance, owner):
        if not instance:
            return self
        app_label = "tenant_%s_%s" % (instance.pk, self.opts.app_label)
        natural_key = (app_label, self.opts.module_name)
        try:
            content_type = ContentType.objects.get_by_natural_key(*natural_key)
        except ContentType.DoesNotExist:
            # We must create the content type and the model class
            content_type = model_class = None
        else:
            # Attempt to retrieve the model class from the content type.
            # At this point, the model class can be None if it's cached yet.
            model_class = content_type.model_class()
        if model_class is None:
            # The model class has not been created yet, we define it.
            # TODO: Use `db_schema` once django #6148 is fixed.
            connection = connections[instance._state.db]
            if connection.vendor == 'postgresql':
                # See https://code.djangoproject.com/ticket/6148#comment:47
                db_table_format = '%s\".\"%s'
            else:
                db_table_format = "%s_%s"
            db_table = db_table_format % (instance.db_schema, self.opts.db_table)
            model_class = self.type(
                tenant=instance,
                Meta=meta(app_label=app_label, db_table=db_table)
            )
            # Make sure to create the content type associated with this model
            # class that was just created.
            if content_type is None:
                ContentType.objects.get_for_model(model_class)
        return model_class._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True
