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


# TODO: Remove when support for django < 1.5 is dropped
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


def receivers_for_model(model):
    # TODO: Remove when support for django < 1.6 is dropped
    sender = model if django.VERSION >= (1, 6) else _make_id(model)
    for signal in model_sender_signals:
        for receiver in signal._live_receivers(sender):
            yield signal, receiver


def disconnect_signals(model):
    for signal, receiver in receivers_for_model(model):
        signal.disconnect(receiver, sender=model)


# TODO: Remove when support for django < 1.6 is dropped
_model_name_attr = 'model_name' if django.VERSION >= (1, 6) else 'module_name'
def model_name_from_opts(opts):
    """
    `Options.module_name` was renamed to `model_name` in Django 1.6.
    """
    return getattr(opts, _model_name_attr)


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
