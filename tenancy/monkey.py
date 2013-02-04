from __future__ import unicode_literals
from functools import wraps

from django.db.models.fields.related import ForeignKey, ManyToManyField

from .models import TenantModelBase


def allow_abstract_tenant_model(wrapped):
    """
    Simply convert references to TenantModelBase instances to their respective
    string reference.
    """
    @wraps(wrapped)
    def __init__(self, to, *args, **kwargs):
        if isinstance(to, TenantModelBase):
            opts = to._meta
            to = "%s.%s" % (opts.app_label, opts.object_name)
        return wrapped(self, to, *args, **kwargs)
    return __init__


def patch_related_fields():
    """
    Monkey patch ForeignKey and ManyToManyField to allow referencing TenantModelBase
    instances.
    """
    if not patch_related_fields.applied:
        ForeignKey.__init__ = allow_abstract_tenant_model(ForeignKey.__init__)
        ManyToManyField.__init__ = allow_abstract_tenant_model(ManyToManyField.__init__)
        patch_related_fields.applied = True
patch_related_fields.applied = False