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
if django.VERSION >= (1, 5):
    @contextmanager
    def app_cache_lock():
        try:
            imp.acquire_lock()
            yield
        finally:
            imp.release_lock()
else:
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
    sender_id = model if django.VERSION >= (1, 6) else _make_id(model)
    for signal in model_sender_signals:
        for receiver in signal._live_receivers(sender_id):
            yield signal, receiver