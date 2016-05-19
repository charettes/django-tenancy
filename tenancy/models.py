from __future__ import unicode_literals

import copy
import logging
from abc import ABCMeta
from collections import OrderedDict
from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.db.models.base import ModelBase, subclass_exception
from django.db.models.deletion import DO_NOTHING
from django.db.models.fields import Field
from django.dispatch.dispatcher import receiver
from django.utils.deconstruct import deconstructible
from django.utils.six import itervalues, string_types, with_metaclass
from django.utils.six.moves import copyreg

from . import get_tenant_model, settings
from .compat import (
    get_remote_field, get_remote_field_model, lazy_related_operation,
    set_remote_field_model,
)
from .management import create_tenant_schema, drop_tenant_schema
from .managers import (
    AbstractTenantManager, TenantManager, TenantModelManagerDescriptor,
)
from .signals import lazy_class_prepared
from .utils import (
    clear_cached_properties, clear_opts_related_cache, disconnect_signals,
    get_model, receivers_for_model, remove_from_app_cache,
)


class TenantModels(object):
    __slots__ = ['references']

    def __init__(self, tenant):
        self.references = OrderedDict((
            (reference, reference.for_tenant(tenant))
            for reference in TenantModelBase.references
        ))

    def __getitem__(self, key):
        return self.references[key]

    def __iter__(self, **kwargs):
        return itervalues(self.references, **kwargs)


class TenantModelsDescriptor(object):
    def contribute_to_class(self, cls, name):
        self.name = name
        setattr(cls, name, self)

    def _get_instance(self, instance):
        return instance._default_manager.get_by_natural_key(
            *instance.natural_key()
        )

    def __get__(self, instance, owner):
        if instance is None:
            return self
        instance = self._get_instance(instance)
        try:
            models = instance.__dict__[self.name]
        except KeyError:
            models = TenantModels(instance)
            self.__set__(instance, models)
        return models

    def __set__(self, instance, value):
        instance = self._get_instance(instance)
        instance.__dict__[self.name] = value

    def __delete__(self, instance):
        for model in self.__get__(instance, owner=None):
            model.destroy()


class AbstractTenant(models.Model):
    ATTR_NAME = 'tenant'

    objects = AbstractTenantManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        created = not self.pk
        save = super(AbstractTenant, self).save(*args, **kwargs)
        if created:
            create_tenant_schema(self)
        return save

    def delete(self, *args, **kwargs):
        delete = super(AbstractTenant, self).delete(*args, **kwargs)
        drop_tenant_schema(self)
        return delete

    def natural_key(self):
        raise NotImplementedError

    models = TenantModelsDescriptor()

    @contextmanager
    def as_global(self):
        """
        Expose this tenant as thread local object. This is required by parts
        of django relying on global states such as authentification backends.
        """
        setattr(connection, self.ATTR_NAME, self)
        try:
            yield
        finally:
            delattr(connection, self.ATTR_NAME)

    @classmethod
    def get_global(cls):
        return getattr(connection, cls.ATTR_NAME, None)

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
        swappable = 'TENANCY_TENANT_MODEL'

    def natural_key(self):
        return (self.name,)


@deconstructible
class Managed(object):
    """
    Sentinel object used to detect tenant managed models.
    """

    def __init__(self, tenant_model):
        self.tenant_model = tenant_model

    def __bool__(self):
        # Evaluates to False in order to prevent Django from managing the model.
        return False

    # Remove when dropping support for Python 2.7
    __nonzero__ = bool

    def __eq__(self, other):
        return isinstance(other, Managed) and other.tenant_model == self.tenant_model


def meta(Meta=None, **opts):
    """
    Create a class with specified opts as attributes to be used as model
    definition options.
    """
    if Meta:
        opts = dict(Meta.__dict__, **opts)
    return type(str('Meta'), (), opts)


def db_schema_table(tenant, db_table):
    if connection.vendor == 'postgresql':
        # See https://code.djangoproject.com/ticket/6148#comment:47
        return '%s\".\"%s' % (tenant.db_schema, db_table)
    else:
        return "%s_%s" % (tenant.db_schema, db_table)


class Reference(object):
    __slots__ = ['model', 'bases', 'Meta', 'related_names']

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


class TenantSpecificModel(with_metaclass(ABCMeta)):
    @classmethod
    def __subclasshook__(cls, subclass):
        if isinstance(subclass, TenantModelBase):
            try:
                tenant_model = get_tenant_model()
            except ImproperlyConfigured:
                # If the tenant model is not configured yet we can assume
                # no specific models have been defined so far.
                return False
            tenant = getattr(subclass, tenant_model.ATTR_NAME, None)
            return isinstance(tenant, tenant_model)
        return NotImplemented


class TenantDescriptor(object):
    __slots__ = ['natural_key']

    def __init__(self, tenant):
        self.natural_key = tenant.natural_key()

    def __get__(self, model, owner):
        tenant_model = get_tenant_model()
        return tenant_model._default_manager.get_by_natural_key(*self.natural_key)


class TenantModelBase(ModelBase):
    reference = Reference
    references = OrderedDict()
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
            # There's always a default manager named `objects`.
            managers.add('objects')
            if getattr(Meta, 'proxy', False):
                model = super_new(
                    cls, name, bases,
                    dict(attrs, meta=meta(Meta, managed=Managed(settings.TENANT_MODEL)))
                )
                cls.references[model] = cls.reference(model, Meta)
            else:
                # Extract field related names prior to adding them to the model
                # in order to validate them later on.
                related_names = {}
                for attr_name, attr in attrs.items():
                    if isinstance(attr, Field):
                        remote_field = get_remote_field(attr)
                        if remote_field:
                            related_names[attr.name or attr_name] = remote_field.related_name
                for base in bases:
                    if isinstance(base, ModelBase) and base._meta.abstract:
                        for field in base._meta.local_fields:
                            remote_field = get_remote_field(field)
                            if remote_field:
                                related_names[field.name] = remote_field.related_name
                        for m2m in base._meta.local_many_to_many:
                            related_names[m2m.name] = get_remote_field(m2m).related_name
                model = super_new(
                    cls, name, bases,
                    dict(attrs, Meta=meta(Meta, managed=Managed(settings.TENANT_MODEL)))
                )
                cls.references[model] = cls.reference(model, Meta, related_names)
                opts = model._meta
                # Validate related name of related fields.
                for field in (opts.local_fields + opts.virtual_fields):
                    remote_field = get_remote_field(field)
                    if remote_field:
                        cls.validate_related_name(model, get_remote_field_model(field), field)
                        # Replace and store the current `on_delete` value to
                        # make sure non-tenant models are not collected on
                        # deletion.
                        on_delete = remote_field.on_delete
                        if on_delete is not DO_NOTHING:
                            remote_field._on_delete = on_delete
                            remote_field.on_delete = DO_NOTHING
                for m2m in opts.local_many_to_many:
                    m2m_remote_field = get_remote_field(m2m)
                    m2m_related_model = get_remote_field_model(m2m)
                    cls.validate_related_name(model, m2m_related_model, m2m)
                    through = m2m_remote_field.through
                    if (not isinstance(through, string_types) and
                            through._meta.auto_created):
                        # Replace the automatically created intermediary model
                        # by a TenantModelBase instance.
                        remove_from_app_cache(through)
                        # Make sure to clear the referenced model cache if
                        # we have contributed to it already.
                        if not isinstance(m2m_related_model, string_types):
                            clear_opts_related_cache(m2m_related_model)
                        m2m_remote_field.through = cls.intermediary_model_factory(m2m, model)
                    else:
                        cls.validate_through(model, m2m_related_model, m2m)
            # Replace `ManagerDescriptor`s with `TenantModelManagerDescriptor`
            # instances.
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
                def attach_descriptor(tenant_model):
                    descriptor = TenantModelDescriptor(model)
                    setattr(tenant_model, related_name, descriptor)
                app_label, model_name = settings.TENANT_MODEL.split('.')
                lazy_class_prepared(app_label, model_name, attach_descriptor)
            model._for_tenant_model = model
        return model

    @classmethod
    def validate_related_name(cls, model, rel_to, field):
        """
        Make sure that related fields pointing to non-tenant models specify
        a related name containing a %(class)s format placeholder.
        """
        if isinstance(rel_to, string_types):
            lazy_related_operation(cls.validate_related_name, model, rel_to, field=field)
        elif not isinstance(rel_to, TenantModelBase):
            related_name = cls.references[model].related_names[field.name]
            if (related_name is not None and
                    not (get_remote_field(field).is_hidden() or '%(class)s' in related_name)):
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
    def validate_through(cls, model, rel_to, field):
        """
        Make sure the related fields with a specified through points to an
        instance of `TenantModelBase`.
        """
        through = get_remote_field(field).through
        if isinstance(through, string_types):
            lazy_related_operation(cls.validate_through, model, through, field=field)
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
        to_model = get_remote_field_model(field)
        opts = from_model._meta
        from_model_name = opts.model_name
        if to_model == from_model:
            from_ = "from_%s" % from_model_name
            to = "to_%s" % from_model_name
            to_model = from_model
        else:
            from_ = from_model_name
            if isinstance(to_model, string_types):
                to = to_model.split('.')[-1].lower()
            else:
                to = to_model._meta.model_name
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
        if hasattr(field, 'db_constraint'):
            field_opts['db_constraint'] = field.db_constraint
        return type(name, (cls.tenant_model_class,), {
            'Meta': Meta,
            '__module__': from_model.__module__,
            from_: models.ForeignKey(
                from_model, on_delete=models.CASCADE, related_name="%s+" % name, **field_opts
            ),
            to: models.ForeignKey(
                to_model, on_delete=models.CASCADE, related_name="%s+" % name, **field_opts
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
        model = super(TenantModelBase, self).__new__(
            self.__class__,
            str("Abstract%s" % reference.object_name_for_tenant(tenant)),
            (self,) + self.tenant_model_bases(tenant, self.__bases__), {
                '__module__': self.__module__,
                'Meta': meta(
                    reference.Meta,
                    abstract=True
                ),
                tenant.ATTR_NAME: TenantDescriptor(tenant),
                '_for_tenant_model': self
            }
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
        # Add copy of the fields to cloak the inherited ones.
        fields = (
            copy.deepcopy(field) for field in (
                self._meta.local_fields +
                self._meta.local_many_to_many +
                self._meta.virtual_fields
            )
        )
        for field in fields:
            remote_field = get_remote_field(field)
            if remote_field:
                # Make sure related fields pointing to tenant models are
                # pointing to their tenant specific counterpart.
                remote_field_model = get_remote_field_model(field)
                # Clear the field's cache.
                if hasattr(field, '_related_fields'):
                    delattr(field, '_related_fields')
                clear_cached_properties(field)
                clear_cached_properties(remote_field)
                if isinstance(remote_field_model, TenantModelBase):
                    if getattr(remote_field, 'parent_link', False):
                        continue
                    set_remote_field_model(field, self.references[remote_field_model].for_tenant(tenant))
                    # If no `related_name` was specified we make sure to
                    # define one based on the non-tenant specific model name.
                    if not remote_field.related_name:
                        remote_field.related_name = "%s_set" % self._meta.model_name
                else:
                    clear_opts_related_cache(remote_field_model)
                    related_name = reference.related_names[field.name]
                    # The `related_name` was validated earlier to either end
                    # with a '+' sign or to contain %(class)s.
                    if related_name:
                        remote_field.related_name = related_name
                    else:
                        related_name = 'unspecified_for_tenant_model+'
                if isinstance(field, models.ManyToManyField):
                    through = remote_field.through
                    remote_field.through = self.references[through].for_tenant(tenant)
                # Re-assign the correct `on_delete` that was swapped for
                # `DO_NOTHING` to prevent non-tenant model collection.
                on_delete = getattr(remote_field, '_on_delete', None)
                if on_delete:
                    remote_field.on_delete = on_delete
            field.contribute_to_class(model, field.name)

        # Some virtual fields such as GenericRelation are not correctly
        # cloaked by `contribute_to_class`. Make sure to remove non-tenant
        # virtual instances from tenant specific model options.
        for virtual_field in self._meta.virtual_fields:
            if virtual_field in opts.virtual_fields:
                opts.virtual_fields.remove(virtual_field)
            if virtual_field in opts.local_fields:
                opts.local_fields.remove(virtual_field)

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
                subclass = subclass_exception(
                    str(exception),
                    (getattr(self, exception), getattr(for_tenant_model, exception)),
                    self.__module__,
                    self,
                )
                self.add_to_class(exception, subclass)

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
        model = get_model(opts.app_label, name.lower())
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
            attrs['_for_tenant_model'] = self

            # In order to make sure the non-tenant model is part of the
            # __mro__ we create an abstract model with stripped fields and
            # inject it as the first base.
            base = type(
                str("Abstract%s" % reference.object_name_for_tenant(tenant)),
                (self,), {
                    '__module__': self.__module__,
                    'Meta': meta(abstract=True),
                }
            )
            # Remove ourself from the parents chain and our descriptor
            base_opts = base._meta
            ptr = base_opts.parents.pop(opts.concrete_model)
            base_opts.local_fields.remove(ptr)
            delattr(base, ptr.name)

            bases = (base,) + self.tenant_model_bases(tenant, self.__bases__)
        else:
            bases = (self.abstract_tenant_model_factory(tenant),)

        model = super(TenantModelBase, self).__new__(
            TenantModelBase, str(name), bases, attrs
        )

        return model

    def destroy(self):
        """
        Remove all reference to this tenant model.
        """
        if not issubclass(self, TenantSpecificModel):
            raise ValueError('Can only be called on tenant specific model.')
        remove_from_app_cache(self, quiet=True)
        if not self._meta.proxy:
            # Some fields (GenericForeignKey, ImageField) attach (pre|post)_init
            # signals to their associated model even if they are abstract.
            # Since this instance was created from an abstract base generated
            # by `abstract_tenant_model_factory` we must make sure to disconnect
            # all signal receivers attached to it in order to be gc'ed.
            disconnect_signals(self.__bases__[0])


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
        tenant = getattr(model, get_tenant_model().ATTR_NAME)
        return (
            __unpickle_tenant_model_base,
            (model._for_tenant_model, tenant.natural_key(), model._meta.abstract)
        )
    return model.__name__

copyreg.pickle(TenantModelBase, __pickle_tenant_model_base)


class TenantModelDescriptor(object):
    __slots__ = ['model']

    def __init__(self, model):
        self.model = model

    def __get__(self, tenant, owner):
        if not tenant:
            return self
        return tenant.models[self.model]._default_manager


class TenantModel(with_metaclass(TenantModelBase, models.Model)):
    class Meta:
        abstract = True


@receiver(models.signals.class_prepared)
def attach_signals(signal, sender, **kwargs):
    """
    Re-attach signals to tenant models
    """
    if issubclass(sender, TenantSpecificModel):
        for signal, receiver_ in receivers_for_model(sender._for_tenant_model):
            signal.connect(receiver_, sender=sender)


def validate_not_to_tenant_model(model, to, field):
    """
    Make sure the `to` relationship is not pointing to an instance of
    `TenantModelBase`.
    """
    if isinstance(to, string_types):
        lazy_related_operation(validate_not_to_tenant_model, model, to, field=field)
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
                remote_field = get_remote_field(field)
                if remote_field:
                    validate_not_to_tenant_model(sender, get_remote_field_model(field), field)
            for m2m in opts.local_many_to_many:
                validate_not_to_tenant_model(sender, get_remote_field_model(m2m), m2m)
