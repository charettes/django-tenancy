from __future__ import unicode_literals

from abc import ABCMeta
import copy
import copy_reg
from contextlib import contextmanager
import logging

import django
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DEFAULT_DB_ALIAS, models
from django.db.models.base import ModelBase, subclass_exception
from django.db.models.fields import Field
from django.db.models.fields.related import add_lazy_relation
from django.db.models.loading import get_model
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict

from . import get_tenant_model
from .management import create_tenant_schema, drop_tenant_schema
from .managers import (AbstractTenantManager, TenantManager,
    TenantModelManagerDescriptor)
from .utils import (clear_opts_related_cache, model_name, receivers_for_model,
    remove_from_app_cache)


class TenantModelsCache(object):
    def contribute_to_class(self, cls, name):
        self.name = name
        setattr(cls, name, self)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        instance = instance._default_manager.get_by_natural_key(
            *instance.natural_key()
        )
        try:
            models = instance.__dict__[self.name]
        except KeyError:
            assert instance.pk, 'Cannot create models for an unexistent tenant.'
            models = tuple(
                reference.for_tenant(instance)
                for reference in TenantModelBase.references
            )
            self.__set__(instance, models)
        return models

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value

    def __delete__(self, instance):
        for model in self.__get__(instance, owner=None):
            remove_from_app_cache(model)


class AbstractTenant(models.Model):
    objects = AbstractTenantManager()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(AbstractTenant, self).__init__(*args, **kwargs)
        if self.pk:
            self._default_manager._add_to_cache(self)

    def save(self, *args, **kwargs):
        save = super(AbstractTenant, self).save(*args, **kwargs)
        create_tenant_schema(self)
        return save

    def delete(self, *args, **kwargs):
        delete = super(AbstractTenant, self).delete(*args, **kwargs)
        drop_tenant_schema(self)
        return delete

    def natural_key(self):
        raise NotImplementedError

    models = TenantModelsCache()

    @contextmanager
    def as_global(self):
        """
        Expose this tenant as thread local object. This is required by parts
        of django relying on global states such as authentification backends.
        """
        connection = connections[DEFAULT_DB_ALIAS]
        try:
            connection.tenant = self
            yield
        finally:
            del connection.tenant

    @property
    def model_name_prefix(self):
        return "Tenant_%s" % '_'.join(self.natural_key())

    @property
    def db_schema(self):
        return "tenant_%s" % '_'.join(self.natural_key())


class Tenant(AbstractTenant):
    name = models.CharField(unique=True, max_length=20)

    objects = TenantManager()

    class Meta:
        if django.VERSION >= (1, 5):  # pragma: no cover
            swappable = 'TENANCY_TENANT_MODEL'

    def natural_key(self):
        return (self.name,)


def meta(Meta=None, **opts):
    """
    Create a class with specified opts as attributes to be used as model
    definition options.
    """
    if Meta:
        opts = dict(Meta.__dict__, **opts)
    return type(str('Meta'), (), opts)


def db_schema_table(tenant, db_table):
    connection = connections[tenant._state.db or DEFAULT_DB_ALIAS]
    if connection.vendor == 'postgresql':  # pragma: no cover
        # See https://code.djangoproject.com/ticket/6148#comment:47
        return '%s\".\"%s' % (tenant.db_schema, db_table)
    else:  # pragma: no cover
        return "%s_%s" % (tenant.db_schema, db_table)


class Reference(object):
    __slots__ = ('model', 'bases', 'Meta', 'related_names')

    def __init__(self, model, Meta, related_names=None):
        self.model = model
        self.Meta = Meta
        self.related_names = related_names

    def object_name_for_tenant(self, tenant):
        return "%s_%s" % (
            tenant.model_name_prefix,
            self.model._meta.object_name
        )

    def for_tenant(self, tenant):
        app_label = self.model._meta.app_label
        object_name = self.object_name_for_tenant(tenant)
        return "%s.%s" % (app_label, object_name)


class TenantSpecificModel(object):
    __metaclass__ = ABCMeta

    @classmethod
    def __subclasshook__(cls, subclass):
        if (isinstance(subclass, TenantModelBase) and
            isinstance(getattr(subclass, 'tenant', None),
                       get_tenant_model(False))):
            return True
        return NotImplemented


class TenantModelBase(ModelBase):
    reference = Reference
    references = SortedDict()
    tenant_model_class = None
    exceptions = ('DoesNotExist', 'MultipleObjectsReturned')

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        Meta = attrs.setdefault('Meta', meta())
        if (getattr(Meta, 'abstract', False) or
            any(issubclass(base, TenantSpecificModel) for base in bases)):
            # Abstract model definition and ones subclassing tenant specific
            # ones shouldn't get any special treatment.
            model = super_new(cls, name, bases, attrs)
            if not cls.tenant_model_class:
                cls.tenant_model_class = model
        else:
            # Store managers to replace them with a descriptor specifying they
            # can't be accessed this way.
            managers = set(
                name for name, attr in attrs.items()
                if isinstance(attr, models.Manager)
            )
            # There's always a default manager name `object`
            managers.add('objects')
            if getattr(Meta, 'proxy', False):
                model = super_new(
                    cls, name, bases,
                    dict(attrs, meta=meta(Meta, managed=False))
                )
                cls.references[model] = cls.reference(model, Meta)
            else:
                # Extract field related names prior to adding them to the model
                # in order to validate them later on.
                related_names = dict(
                    (attr.name or name, attr.rel.related_name)
                    for name, attr in attrs.items()
                    if isinstance(attr, Field) and attr.rel
                )
                for base in bases:
                    if isinstance(base, ModelBase) and base._meta.abstract:
                        for field in base._meta.local_fields:
                            if field.rel:
                                related_names[field.name] = field.rel.related_name
                        for m2m in base._meta.local_many_to_many:
                            related_names[m2m.name] = m2m.rel.related_name
                model = super_new(
                    cls, name, bases,
                    dict(attrs, Meta=meta(Meta, managed=False))
                )
                cls.references[model] = cls.reference(model, Meta, related_names)
                opts = model._meta
                # Validate related name of related fields
                for field in opts.local_fields:
                    if field.rel:
                        cls.validate_related_name(field, field.rel.to, model)
                for m2m in opts.local_many_to_many:
                    rel = m2m.rel
                    to = rel.to
                    cls.validate_related_name(m2m, to, model)
                    through = rel.through
                    if (not isinstance(through, basestring) and
                        through._meta.auto_created):
                        # Replace the automatically created intermediary model
                        # by a TenantModelBase instance.
                        remove_from_app_cache(through)
                        # Make sure to clear the referenced model cache if
                        # we have contributed to it already.
                        if not isinstance(to, basestring):
                            clear_opts_related_cache(rel.to)
                        rel.through = cls.intermediary_model_factory(m2m, model)
                    else:
                        cls.validate_through(m2m, m2m.rel.to, model)
            # Replace `ManagerDescriptor`s with `TenantModelManagerDescriptor`
            # instances
            for manager in managers:
                setattr(model, manager, TenantModelManagerDescriptor(model))
            # Extract the specified related name if it exists.
            try:
                related_name = attrs.pop('TenantMeta').related_name
            except (KeyError, AttributeError):
                pass
            else:
                # Attach a descriptor to the tenant model to access the
                # underlying model based on the tenant instance.
                tenant_model = get_tenant_model(False)
                descriptor = TenantModelDescriptor(model)
                setattr(tenant_model, related_name, descriptor)
            model._for_tenant_model = model
        return model

    @classmethod
    def validate_related_name(cls, field, rel_to, model):
        """
        Make sure that related fields pointing to non-tenant models specify
        a related name containing a %(class)s format placeholder.
        """
        if isinstance(rel_to, basestring):
            add_lazy_relation(model, field, rel_to, cls.validate_related_name)
        elif not isinstance(rel_to, cls):
            related_name = cls.references[model].related_names[field.name]
            if (related_name is not None and
                not (field.rel.is_hidden() or '%(class)s' in related_name)):
                    del cls.references[model]
                    remove_from_app_cache(model, quiet=True)
                    raise ImproperlyConfigured(
                        "Since `%s.%s` is originating from an instance "
                        "of `TenantModelBase` and not pointing to one "
                        "its `related_name` option must ends with a "
                        "'+' or contain the '%%(class)s' format "
                        "placeholder." % (model.__name__, field.name)
                    )

    @classmethod
    def validate_through(cls, field, rel_to, model):
        """
        Make sure the related fields with a specified through points to an
        instance of `TenantModelBase`.
        """
        through = field.rel.through
        if isinstance(through, basestring):
            add_lazy_relation(model, field, through, cls.validate_through)
        elif not isinstance(through, cls):
            del cls.references[model]
            remove_from_app_cache(model, quiet=True)
            raise ImproperlyConfigured(
                "Since `%s.%s` is originating from an instance of "
                "`TenantModelBase` its `through` option must also be pointing "
                "to one." % (model.__name__, field.name)
            )

    @classmethod
    def intermediary_model_factory(cls, field, from_model):
        to_model = field.rel.to
        opts = from_model._meta
        from_model_name = model_name(opts)
        if to_model == from_model:
            from_ = "from_%s" % from_model_name
            to = "to_%s" % from_model_name
            to_model = from_model
        else:
            from_ = from_model_name
            if isinstance(to_model, basestring):
                to = to_model.split('.')[-1].lower()
            else:
                to = model_name(to_model._meta)
        Meta = meta(
            db_table=field._get_m2m_db_table(opts),
            auto_created=from_model,
            app_label=opts.app_label,
            db_tablespace=opts.db_tablespace,
            unique_together=(from_, to),
            verbose_name="%(from)s-%(to)s relationship" % {'from': from_, 'to': to},
            verbose_name_plural="%(from)s-%(to)s relationships" % {'from': from_, 'to': to}
        )
        name = str("%s_%s" % (opts.object_name, field.name))
        field_opts = {'db_tablespace': field.db_tablespace}
        # Django 1.6 introduced `db_contraint`.
        if hasattr(field, 'db_constraint'):
            field_opts['db_constraint'] = field.db_constraint
        return type(name, (cls.tenant_model_class,), {
            'Meta': Meta,
            '__module__': from_model.__module__,
            from_: models.ForeignKey(
                from_model, related_name="%s+" % name, **field_opts
            ),
            to: models.ForeignKey(
                to_model, related_name="%s+" % name, **field_opts
            ),
        })

    @classmethod
    def tenant_model_bases(cls, tenant, bases):
        return tuple(
            base.for_tenant(tenant) for base in bases
            if isinstance(base, cls) and not base._meta.abstract
        )

    def abstract_tenant_model_factory(self, tenant):
        if issubclass(self, TenantSpecificModel):
            raise ValueError('Can only be called on non-tenant specific model.')
        reference = self.references[self]
        model = super(TenantModelBase, self).__new__(self.__class__,
            str("Abstract%s" % reference.object_name_for_tenant(tenant)),
            (self,) + self.tenant_model_bases(tenant, self.__bases__),
            dict(
                 __module__=self.__module__,
                 Meta=meta(
                    reference.Meta,
                    abstract=True
                ),
                tenant=tenant,
                _for_tenant_model=self
            )
        )
        opts = model._meta

        # Remove ourself from the parents chain and our descriptor
        ptr = opts.parents.pop(self)
        opts.local_fields.remove(ptr)
        delattr(model, ptr.name)

        # Rename parent ptr fields
        for parent, ptr in opts.parents.items():
            local_ptr = self._meta.parents[parent._for_tenant_model]
            ptr.name = None
            ptr.set_attributes_from_name(local_ptr.name)

        # Add the local fields of this class
        local_fields = self._meta.local_fields + self._meta.local_many_to_many
        for local_field in local_fields:
            field = copy.deepcopy(local_field)
            rel = field.rel
            if rel:
                # Make sure related fields pointing to tenant models are
                # pointing to their tenant specific counterpart.
                to = rel.to
                if isinstance(to, TenantModelBase):
                    if getattr(rel, 'parent_link', False):
                        continue
                    rel.to = self.references[to].for_tenant(tenant)
                else:
                    clear_opts_related_cache(to)
                related_name = reference.related_names[field.name]
                if related_name:
                    rel.related_name = related_name
                else:
                    rel.related_name = 'unspecified_for_tenant_model+'
                if isinstance(field, models.ManyToManyField):
                    through = field.rel.through
                    rel.through = self.references[through].for_tenant(tenant)
            field.contribute_to_class(model, field.name)

        return model

    def _prepare(self):
        super(TenantModelBase, self)._prepare()

        if issubclass(self, TenantSpecificModel):
            for_tenant_model = self._for_tenant_model

            # Attach the tenant model concrete managers since they should
            # override the ones from abstract bases.
            managers = for_tenant_model._meta.concrete_managers
            for _, mgr_name, manager in managers:
                new_manager = manager._copy_to_model(self)
                new_manager.creation_counter = manager.creation_counter
                self.add_to_class(mgr_name, new_manager)

            # Since our declaration class is not one of our parents we must
            # make sure our exceptions extend his.
            for exception in self.exceptions:
                self.add_to_class(exception, subclass_exception(str(exception),
                    (getattr(self, exception),
                     getattr(for_tenant_model, exception)),
                    self.__module__, self
                ))

    def for_tenant(self, tenant):
        """
        Returns the model for the specific tenant.
        """
        if issubclass(self, TenantSpecificModel):
            raise ValueError('Can only be called on non-tenant specific model.')
        reference = self.references[self]
        opts = self._meta
        name = reference.object_name_for_tenant(tenant)

        # Return the already cached model instead of creating a new one.
        model = get_model(
            opts.app_label, name.lower(),
            only_installed=False
        )
        if model:
            return model

        attrs = {
            '__module__': self.__module__,
            'Meta': meta(
                reference.Meta,
                # TODO: Use `db_schema` once django #6148 is fixed.
                db_table=db_schema_table(tenant, self._meta.db_table),
            )
        }

        if opts.proxy:
            attrs.update(tenant=tenant, _for_tenant_model=self)
            bases = self.tenant_model_bases(tenant, self.__bases__)
        else:
            bases = (self.abstract_tenant_model_factory(tenant),)

        model = super(TenantModelBase, self).__new__(
            TenantModelBase, str(name), bases, attrs
        )

        return model

    def __instancecheck__(self, instance):
        return self.__subclasscheck__(instance.__class__)

    def __subclasscheck__(self, subclass):
        if (self._meta.proxy and subclass._meta.proxy and
            not issubclass(self, TenantSpecificModel) and
            issubclass(subclass, TenantSpecificModel)):
            return (
                subclass._for_tenant_model is self or
                issubclass(subclass, self.for_tenant(subclass.tenant))
            )
        return super(TenantModelBase, self).__subclasscheck__(subclass)


def __unpickle_tenant_model_base(model, natural_key, abstract):
    try:
        manager = get_tenant_model()._default_manager
        tenant = manager.get_by_natural_key(*natural_key)
        tenant_model = model.for_tenant(tenant)
        if abstract:
            tenant_model = tenant_model.__bases__[0]
        return tenant_model
    except Exception:
        logger = logging.getLogger('tenancy.pickling')
        logger.exception('Failed to unpickle tenant model')


def __pickle_tenant_model_base(model):
    if issubclass(model, TenantSpecificModel):
        return (
            __unpickle_tenant_model_base,
            (model._for_tenant_model, model.tenant.natural_key(), model._meta.abstract)
        )
    return model.__name__

copy_reg.pickle(TenantModelBase, __pickle_tenant_model_base)


class TenantModelDescriptor(object):
    __slots__ = ('model',)

    def __init__(self, model):
        self.model = model

    def __get__(self, tenant, owner):
        if not tenant:
            return self
        return self.model.for_tenant(tenant)._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True


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
        remove_from_app_cache(model, quiet=True)
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
