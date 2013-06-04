from __future__ import unicode_literals
import sys

import django
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

from ..models import TenantModel
from ..utils import model_sender_signals

from .managers import ManagerOtherSubclass, ManagerSubclass


class NonTenantModel(models.Model):
    class Meta:
        app_label = 'tenancy'


class AbstractNonTenant(models.Model):
    hidden_non_tenant = models.ForeignKey(NonTenantModel, null=True)

    class Meta:
        abstract = True


class AbstractTenantModel(TenantModel):
    date = models.DateField(null=True)

    class Meta:
        abstract = True


class TenantModelMixin(object):
    pass


class SpecificModel(AbstractTenantModel, AbstractNonTenant, TenantModelMixin):
    non_tenant = models.ForeignKey(
        NonTenantModel,
        related_name="%(class)ss",
        null=True
    )

    objects = ManagerSubclass()
    custom_objects = ManagerOtherSubclass()

    class Meta:
        app_label = 'tenancy'
        db_table = 'custom_db_table'

    class TenantMeta:
        related_name = 'specificmodels'

    def save(self, *args, **kwargs):
        return super(SpecificModel, self).save(*args, **kwargs)


class SpecificModelProxy(SpecificModel):
    objects = ManagerOtherSubclass()
    proxied_objects = ManagerSubclass()

    class Meta:
        proxy = True

    class TenantMeta:
        related_name = 'specific_model_proxies'


class SpecificModelProxySubclass(SpecificModelProxy):
    class Meta:
        proxy = True


class SpecificModelSubclass(SpecificModel):
    objects = ManagerOtherSubclass()

    class TenantMeta:
        related_name = 'specific_models_subclasses'


class SpecificModelSubclassProxy(SpecificModelSubclass):
    class Meta:
        proxy = True


class RelatedSpecificModel(TenantModel):
    class TenantMeta:
        related_name = 'related_specific_models'


class AbstractSpecificModelSubclass(TenantModel):
    fk = models.ForeignKey(SpecificModel, related_name='fks', null=True)

    class Meta:
        abstract = True


class RelatedTenantModel(AbstractSpecificModelSubclass):
    m2m_ = models.ManyToManyField(SpecificModel, name=str('m2m'), related_name='m2ms')
    m2m_to_undefined = models.ManyToManyField('SignalTenantModel')
    m2m_through = models.ManyToManyField(SpecificModel, related_name='m2ms_through',
                                         through='M2MSpecific')
    m2m_recursive = models.ManyToManyField('self')
    m2m_non_tenant = models.ManyToManyField(
        NonTenantModel,
        related_name="%(class)ss"
    )

    class TenantMeta:
        related_name = 'related_tenant_models'


class M2MSpecific(TenantModel):
    related = models.ForeignKey('RelatedTenantModel')
    specific = models.ForeignKey(SpecificModel)

    class Meta:
        if django.VERSION >= (1, 5):
            index_together = (
                ('related', 'specific'),
            )

    class TenantMeta:
        related_name = 'm2m_specifics'


class RelatedTenantModelSubclass(RelatedTenantModel):
    def __init__(self, *args, **kwargs):
        super(RelatedTenantModelSubclass, self).__init__(*args, **kwargs)


class SignalTenantModel(TenantModel):
    class TenantMeta:
        related_name = 'signal_models'

    _logs = {}

    @classmethod
    def logs(cls):
        return cls._logs.setdefault(cls.tenant, [])

    @classmethod
    def log(cls, signal):
        cls.logs().append(signal)


def add_to_dispatched(signal, sender, **kwargs):
    sender.log(signal)

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
        app_label = 'tenancy'

    class TenantMeta:
        related_name = 'users'


try:
    from ..mutant.models import MutableTenantModel
except ImportError:
    pass
else:
    if sys.version_info >= (2, 7):
        class MutableModel(MutableTenantModel):
            field = models.BooleanField()

            class Meta:
                ordering = ('-id',)

            class TenantMeta:
                related_name = 'mutable_models'

        class MutableModelSubclass(MutableModel):
            non_mutable_fk = models.ForeignKey(SpecificModel)

        class NonMutableModel(TenantModel):
            mutable_fk = models.ForeignKey(MutableModel)
