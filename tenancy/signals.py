from __future__ import unicode_literals

from django.core.signals import Signal
from django.db.models.signals import class_prepared

from .utils import get_model


def lazy_class_prepared(app_label, object_name, callback):
    """
    Lazily execute a callback upon model class preparation.
    """
    model = get_model(app_label, object_name.lower())
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

pre_schema_creation = Signal(providing_args=['tenant', 'using'])
post_schema_creation = Signal(providing_args=['tenant', 'using'])

pre_models_creation = Signal(providing_args=['tenant', 'using'])
post_models_creation = Signal(providing_args=['tenant', 'using'])

pre_schema_deletion = Signal(providing_args=['tenant', 'using'])
post_schema_deletion = Signal(providing_args=['tenant', 'using'])
