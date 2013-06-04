from __future__ import unicode_literals

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


class LazySignalConnector(object):
    """
    An object to attach signals to a model only when it's prepared.
    """

    def __init__(self, app_label, object_name):
        self.receivers = []
        self.model = None
        lazy_class_prepared(app_label, object_name, self.__connect_receivers)

    def __connect_receivers(self, model):
        self.model = model
        self.connect_receivers()

    def connect_receivers(self):
        if self.model is None:
            msg = "Can't connect receivers until `%s.%s` is prepared."
            raise RuntimeError(msg % (self.app_label, self.object_name))
        while self.receivers:
            signal, receiver, kwargs = self.receivers.pop(0)
            signal.connect(receiver, sender=self.model, **kwargs)

    def __call__(self, signal, **kwargs):
        def _decorator(receiver):
            self.receivers.append((signal, receiver, kwargs))
            if self.model:
                self.connect_receivers()
            return receiver
        return _decorator

    def disconnect(self, signal, receiver, **kwargs):
        try:
            self.receivers.remove((signal, receiver, kwargs))
        except ValueError:
            if self.model:
                signal.disconnect(receiver, sender=self.model, **kwargs)
            else:
                raise
