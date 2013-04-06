from __future__ import unicode_literals
import imp
from contextlib import contextmanager

import django
from django.db import connections, models, router
from django.db.models.loading import cache as app_cache
from django.dispatch.dispatcher import _make_id


def allow_syncdbs(model):
    for db in connections:
        if router.allow_syncdb(db, model):
            yield db


# TODO: Remove when support for 1.4 is dropped
if django.VERSION >= (1, 5):  #pragma: no cover
    @contextmanager
    def app_cache_lock():
        try:
            imp.acquire_lock()
            yield
        finally:
            imp.release_lock()
else:  #pragma: no cover
    def app_cache_lock():
        return app_cache.write_lock


def remove_from_app_cache(model_class):
    opts = model_class._meta
    app_label, model_name = opts.app_label, opts.object_name.lower()
    with app_cache_lock():
        app_models = app_cache.app_models.get(app_label, False)
        if app_models:
            model = app_models.pop(model_name, False)
            if model:
                app_cache._get_models_cache.clear()
                return model


model_sender_signals = (
    models.signals.pre_init,
    models.signals.post_init,
    models.signals.pre_save,
    models.signals.post_save,
    models.signals.pre_delete,
    models.signals.post_delete,
)


# TODO: Remove when support for 1.5 is dropped
def receivers_for_model(model):
    sender = model if django.VERSION >= (1, 6) else _make_id(model)
    for signal in model_sender_signals:
        for receiver in signal._live_receivers(sender):
            yield signal, receiver


def disconnect_signals(model):
    for signal, receiver in receivers_for_model(model):
        signal.disconnect(receiver, sender=model)


# TODO: Remove when support for 1.5 is dropped
if django.VERSION >= (1, 6):
    def model_name(opts):
        return opts.model_name
else:
    def model_name(opts):
        return opts.module_name


# TODO: Remove when support for 1.4 is dropped
if django.VERSION >= (1, 5):
    subclass_exception = models.base.subclass_exception
else:
    def unpickle_inner_exception(klass, exception_name):
        # Get the exception class from the class it is attached to:
        exception = getattr(klass, exception_name)
        return exception.__new__(exception)

    def subclass_exception(name, parents, module, attached_to):
        class_dict = {'__module__': module}
        if attached_to is not None:
            def __reduce__(self):
                # Exceptions are special - they've got state that isn't
                # in self.__dict__. We assume it is all in self.args.
                return (unpickle_inner_exception, (attached_to, name), self.args)

            def __setstate__(self, args):
                self.args = args

            class_dict.update(
                __reduce__=__reduce__,
                __setstate__=__setstate__
            )

        return type(name, parents, class_dict)


_opts_related_cache_attrs = ('_related_objects_cache', '_related_objects_proxy_cache',
                             '_related_many_to_many_cache', '_name_map')
def clear_opts_related_cache(model_class):
    """ 
    Clear the specified model opts related cache
    """
    opts = model_class._meta
    for attr in _opts_related_cache_attrs:
        try:
            delattr(opts, attr)
        except AttributeError:
            pass
