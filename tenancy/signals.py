from __future__ import unicode_literals

from django.db.models.loading import get_model
from django.db.models.signals import class_prepared
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict


class LazySignalConnector(object):
    """
    An object to attach signals to a model only when it's prepared.
    """

    def __init__(self, app_name, object_name):
        self.app_name = app_name
        self.object_name = object_name
        self.prepared = False
        self.receivers = SortedDict()
        self.model = get_model(
            app_name, object_name.lower(),
            seed_cache=False, only_installed=True
        )
        if self.model is None:
            class_prepared.connect(self.__class_prepared_receiver)

    def __class_prepared_receiver(self, sender, **kwargs):
        opts = sender._meta
        if (opts.app_label == opts.app_label and
            opts.object_name == self.object_name):
            class_prepared.disconnect(self.__class_prepared_receiver)
            self.model = sender
            self.connect_receivers()

    def connect_receivers(self):
        if self.model is None:
            msg = "Can't connect receivers until `%s.%s` is prepared."
            raise RuntimeError(msg % (self.app_name, self.object_name))
        while self.receivers:
            signal, receiver = self.receivers.keyOrder[0]
            kwargs = self.receivers.pop((signal, receiver))
            signal.connect(receiver, sender=self.model, **kwargs)

    def __call__(self, signal, **kwargs):
        def _decorator(receiver):
            self.receivers[(signal, receiver)] = kwargs
            if self.model:
                self.connect_receivers()
            return receiver
        return _decorator

    def disconnect(self, signal, receiver):
        try:
            self.receivers.pop((signal, receiver))
        except KeyError:
            if self.model:
                signal.disconnect(receiver, sender=self.model)