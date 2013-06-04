from __future__ import unicode_literals
import imp
from contextlib import contextmanager

import django
from django.db import connections, models, router
from django.db.models.base import ModelBase
from django.db.models.loading import cache as app_cache
from django.dispatch.dispatcher import _make_id


def allow_syncdbs(model):
    for db in connections:
        if router.allow_syncdb(db, model):
            yield db


@contextmanager
def app_cache_lock():
    try:
        imp.acquire_lock()
        yield
    finally:
        imp.release_lock()


def remove_from_app_cache(model_class, quiet=False):
    opts = model_class._meta
    with app_cache_lock():
        app_models = app_cache.app_models.get(opts.app_label, None)
        if app_models is None:
            if quiet:
                return
            else:
                raise ValueError(
                    "No cached models for app %s" % opts.app_label
                )
        model = app_models.pop(model_name(opts), None)
        if model is None:
            if quiet:
                return
            else:
                raise ValueError("%r is not cached" % model_class)
        app_cache._get_models_cache.clear()
        disconnect_signals(model)
        for field, field_model in model._meta.get_fields_with_model():
            rel = field.rel
            if field_model is None and rel:
                to = rel.to
                if isinstance(to, ModelBase):
                    clear_opts_related_cache(to)
                    if not rel.is_hidden():
                        delattr(to, field.related.get_accessor_name())


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
if django.VERSION >= (1, 6):  # pragma: no cover
    def model_name(opts):
        return opts.model_name
else:  # pragma: no cover
    def model_name(opts):
        return opts.module_name


_opts_related_cache_attrs = (
    '_related_objects_cache',
    '_related_objects_proxy_cache',
    '_related_many_to_many_cache',
    '_name_map'
)


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
