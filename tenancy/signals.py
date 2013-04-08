from __future__ import unicode_literals

from django.db.models.loading import get_model
from django.db.models.signals import class_prepared
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import SortedDict


class LazyClassPrepared(object):
    """
    An object to execute a particular callback once on model post-prepration.
    """

    def __init__(self, app_label, object_name, callback):
        self.app_label = app_label
        self.object_name = object_name
        model = get_model(
            app_label, object_name.lower(),
            seed_cache=False, only_installed=True
        )
        if model:
            callback(model)
        else:
            class_prepared.connect(self.__class_prepared_receiver)

    def __class_prepared_receiver(self, sender, **kwargs):
        opts = sender._meta
        if (opts.app_label == self.app_label and
            opts.object_name == self.object_name):
            class_prepared.disconnect(self.__class_prepared_receiver)
            self.callback(sender)


class LazySignalConnector(LazyClassPrepared):
    """
    An object to attach signals to a model only when it's prepared.
    """

    def __init__(self, app_label, object_name):
        self.receivers = SortedDict()
        super(LazySignalConnector, self).__init__(
            app_label, object_name, self.__connect_receivers
        )

    def __connect_receivers(self, sender):
        self.model = sender
        self.connect_receivers()

    def connect_receivers(self):
        if self.model is None:
            msg = "Can't connect receivers until `%s.%s` is prepared."
            raise RuntimeError(msg % (self.app_label, self.object_name))
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
