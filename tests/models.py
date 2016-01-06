from __future__ import unicode_literals

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.contenttypes.fields import (
    GenericForeignKey, GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields.related import ForeignObject

from tenancy.models import Tenant, TenantModel
from tenancy.utils import model_sender_signals

from .managers import ManagerOtherSubclass, ManagerSubclass


class NonTenantModel(models.Model):
    class Meta:
        app_label = 'tests'


class AbstractNonTenant(models.Model):
    hidden_non_tenant = models.ForeignKey(NonTenantModel, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = 'tests'
        abstract = True


class AbstractTenantModel(TenantModel):
    date = models.DateField(null=True)

    class Meta:
        app_label = 'tests'
        abstract = True


class TenantModelMixin(object):
    pass


class SpecificModel(AbstractTenantModel, AbstractNonTenant, TenantModelMixin):
    non_tenant = models.ForeignKey(
        NonTenantModel,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        null=True
    )
    o2o = models.OneToOneField(NonTenantModel, on_delete=models.CASCADE, related_name="%(class)s_o2os", null=True)
    o2o_hidden = models.OneToOneField(NonTenantModel, on_delete=models.CASCADE, related_name='+', null=True)

    objects = ManagerSubclass()
    custom_objects = ManagerOtherSubclass()

    class Meta:
        app_label = 'tests'
        db_table = 'custom_db_table'

    class TenantMeta:
        related_name = 'specificmodels'

    def save(self, *args, **kwargs):
        return super(SpecificModel, self).save(*args, **kwargs)

    def test_mro(self):
        return 'SpecificModel'


class PostInitFieldsModel(TenantModel):
    """
    Model used to make sure fields (GenericForeignKey, ImageField) that are
    attaching a `(pre|post)_init` signal to their model are not preventing
    garbage collection of them.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    try:
        from PIL import Image as _  # NOQA
    except ImportError:
        pass
    else:
        image = models.ImageField(upload_to='void')

    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'postinits'

    def test_mro(self):
        return 'PostInitFieldsModel'


class GenericRelationModel(TenantModel):
    postinits = GenericRelation(PostInitFieldsModel)

    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'generic_relations'

    def test_mro(self):
        return 'GenericRelationModel'


class SpecificModelProxy(SpecificModel):
    objects = ManagerOtherSubclass()
    proxied_objects = ManagerSubclass()

    class Meta:
        app_label = 'tests'
        proxy = True

    class TenantMeta:
        related_name = 'specific_model_proxies'

    def test_mro(self):
        return 'SpecificModelProxy'


class SpecificModelProxySubclass(SpecificModelProxy):
    class Meta:
        app_label = 'tests'
        proxy = True

    def test_mro(self):
        return 'SpecificModelProxySubclass'


class SpecificModelSubclass(SpecificModel):
    objects = ManagerOtherSubclass()

    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'specific_models_subclasses'

    def test_mro(self):
        return 'SpecificModelSubclass'


class SpecificModelSubclassProxy(SpecificModelSubclass):
    class Meta:
        app_label = 'tests'
        proxy = True

    def test_mro(self):
        return 'SpecificModelSubclassProxy'


class RelatedSpecificModel(TenantModel):
    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'related_specific_models'

    def test_mro(self):
        return 'RelatedSpecificModel'


class AbstractSpecificModelSubclass(TenantModel):
    fk = models.ForeignKey(SpecificModel, on_delete=models.CASCADE, related_name='fks', null=True)

    class Meta:
        app_label = 'tests'
        abstract = True


class RelatedTenantModel(AbstractSpecificModelSubclass):
    m2m_ = models.ManyToManyField(SpecificModel, name=str('m2m'), related_name='m2ms')
    m2m_to_undefined = models.ManyToManyField('SignalTenantModel')
    m2m_through = models.ManyToManyField(
        SpecificModel, related_name='m2ms_through',
        through='M2MSpecific', through_fields=['related', 'specific'],
    )
    m2m_recursive = models.ManyToManyField('self')
    m2m_non_tenant = models.ManyToManyField(
        NonTenantModel,
        related_name="%(class)ss"
    )

    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'related_tenant_models'

    def test_mro(self):
        return 'RelatedTenantModel'


class M2MSpecific(TenantModel):
    related = models.ForeignKey('RelatedTenantModel', on_delete=models.CASCADE, null=True)
    specific = models.ForeignKey(
        SpecificModel, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_related"
    )

    class Meta:
        app_label = 'tests'
        index_together = (
            ('related', 'specific'),
        )

    class TenantMeta:
        related_name = 'm2m_specifics'

    def test_mro(self):
        return 'M2MSpecific'

ForeignObject(
    to=SpecificModel, on_delete=models.CASCADE, from_fields=['specific'], to_fields=['id'], related_name='+',
).contribute_to_class(
    M2MSpecific, 'specific_related_fk', virtual_only=True,
)


class SignalTenantModel(TenantModel):
    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'signal_models'

    _logs = {}

    @classmethod
    def logs(cls, value=None):
        return cls._logs.setdefault(getattr(cls, Tenant.ATTR_NAME), [])

    @classmethod
    def clear_logs(cls):
        cls._logs[getattr(cls, Tenant.ATTR_NAME)] = []

    @classmethod
    def log(cls, signal):
        cls.logs().append(signal)

    def test_mro(self):
        return 'SignalTenantModel'


def add_to_dispatched(signal, sender, **kwargs):
    sender.logs().append(signal)

for signal in model_sender_signals:
    signal.connect(add_to_dispatched, sender=SignalTenantModel)


class TenantUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """
        Creates and saves a User with the given username, email and password.
        """
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        return self.create_user(email, password, is_superuser=True)


class TenantUser(TenantModel, AbstractBaseUser):
    email = models.EmailField(unique=True)
    is_superuser = models.BooleanField(default=False)

    objects = TenantUserManager()

    USERNAME_FIELD = 'email'

    class Meta:
        app_label = 'tests'

    class TenantMeta:
        related_name = 'users'

    def test_mro(self):
        return 'TenantUser'


try:
    from tenancy.mutant.models import ModelDefinition, MutableTenantModel
except ImportError:
    pass
else:
    class MutableModel(MutableTenantModel):
        field = models.BooleanField(default=False)
        model_def = models.ForeignKey(ModelDefinition, on_delete=models.CASCADE, null=True)

        class Meta:
            app_label = 'tests'
            ordering = ('-id',)

        class TenantMeta:
            related_name = 'mutable_models'

        def test_mro(self):
            return 'MutableModel'

    class MutableModelSubclass(MutableModel):
        non_mutable_fk = models.ForeignKey(SpecificModel, on_delete=models.CASCADE, related_name='mutables')

        class Meta:
            app_label = 'tests'

        def test_mro(self):
            return 'MutableModelSubclass'

    class NonMutableModel(TenantModel):
        mutable_fk = models.ForeignKey(MutableModel, on_delete=models.CASCADE, related_name='non_mutables')

        class Meta:
            app_label = 'tests'

        def test_mro(self):
            return 'NonMutableModel'
