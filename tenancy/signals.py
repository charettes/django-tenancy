from __future__ import unicode_literals

from django.core.signals import Signal
from django.db.models.loading import get_model
from django.db.models.signals import class_prepared


def lazy_class_prepared(app_label, object_name, callback):
    """
    Lazily execute a callback upon model class preparation.
    """
    model = get_model(
        app_label, object_name.lower(),
        seed_cache=False, only_installed=False
    )
    if model:
        callback(model)
    else:
        def receiver(sender, **kwargs):
            opts = sender._meta
            if (opts.app_label == app_label and
                opts.object_name == object_name):
                class_prepared.disconnect(receiver)
                callback(sender)
        class_prepared.connect(receiver, weak=False)


pre_tenant_models_creation = Signal(providing_args=['tenant', 'using'])
post_tenant_models_creation = Signal(providing_args=['tenant', 'using'])
pre_tenant_schema_deletion = Signal(providing_args=['tenant', 'using'])
