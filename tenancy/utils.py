from __future__ import unicode_literals

from contextlib import contextmanager
from itertools import chain

import django
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, models, router
from django.db.models.base import ModelBase


# TODO: Remove `allow_syncdb` alternative when support for 1.6 is dropped
if django.VERSION >= (1, 7):
    def allow_migrate(model):
        for db in connections:
            if router.allow_migrate(db, model):
                yield db
else:
    def allow_migrate(model):
        for db in connections:
            if router.allow_syncdb(db, model):
                yield db


if django.VERSION >= (1, 7):
    from django.apps import apps

    def get_model(app_label, model_name, **kwargs):
        try:
            return apps.get_registered_model(app_label, model_name)
        except LookupError:
            pass
else:
    from django.db.models.loading import get_model  # NOQA


if django.VERSION >= (1, 7):
    @contextmanager
    def _apps_lock():
        # The registry lock is not re-entrant so we must avoid acquiring it
        # during the initialization phase in order to prevent deadlocks.
        if apps.ready:
            with apps._lock:
                yield
        else:
            yield

    def remove_from_app_cache(model_class, quiet=False):
        opts = model_class._meta
        apps = opts.apps
        with _apps_lock():
            try:
                app_config = apps.get_app_config(opts.app_label)
            except ImproperlyConfigured:
                if quiet:
                    return
                else:
                    raise ValueError(
                        "No cached models for app %s" % opts.app_label
                    )
            try:
                model = app_config.models.pop(opts.model_name)
            except LookupError:
                if quiet:
                    return
                else:
                    raise ValueError("%r is not cached" % model_class)
            apps.clear_cache()
            unreference_model(model)
else:
    import imp

    @contextmanager
    def _imp_lock():
        try:
            imp.acquire_lock()
            yield
        finally:
            imp.release_lock()

    def remove_from_app_cache(model_class, quiet=False):
        from django.db.models.loading import cache as app_cache
        opts = model_class._meta
        with _imp_lock():
            app_models = app_cache.app_models.get(opts.app_label, None)
            if app_models is None:
                if quiet:
                    return
                else:
                    raise ValueError(
                        "No cached models for app %s" % opts.app_label
                    )
            model = app_models.pop(opts.model_name, None)
            if model is None:
                if quiet:
                    return
                else:
                    raise ValueError("%r is not cached" % model_class)
            app_cache._get_models_cache.clear()
            unreference_model(model)


def unreference_model(model):
    opts = model._meta
    disconnect_signals(model)
    for field, field_model in chain(opts.get_fields_with_model(),
                                    opts.get_m2m_with_model()):
        rel = field.rel
        if field_model is None and rel:
            to = rel.to
            if isinstance(to, ModelBase):
                clear_opts_related_cache(to)
                rel_is_hidden = rel.is_hidden()
                # An accessor is added to related classes if they are not
                # hidden. However o2o fields *always* add an accessor
                # even if the relationship is hidden.
                o2o = isinstance(field, models.OneToOneField)
                if not rel_is_hidden or o2o:
                    try:
                        delattr(to, field.related.get_accessor_name())
                    except AttributeError:
                        # Hidden related names are not respected for o2o
                        # thus a tenant models with a o2o pointing to
                        # a non-tenant one would have a class for multiple
                        # tenant thus the attribute might be attempted
                        # to be deleted multiple times.
                        if not (o2o and rel_is_hidden):
                            raise


model_sender_signals = (
    models.signals.pre_init,
    models.signals.post_init,
    models.signals.pre_save,
    models.signals.post_save,
    models.signals.pre_delete,
    models.signals.post_delete,
    models.signals.m2m_changed,
)


def receivers_for_model(model):
    for signal in model_sender_signals:
        for receiver in signal._live_receivers(model):
            yield signal, receiver


def disconnect_signals(model):
    for signal, receiver in receivers_for_model(model):
        signal.disconnect(receiver, sender=model)


_opts_related_cache_attrs = [
    '_related_objects_cache',
    '_related_objects_proxy_cache',
    '_related_many_to_many_cache',
    '_name_map',
]


def clear_opts_related_cache(model_class):
    """
    Clear the specified model and its children opts related cache.
    """
    opts = model_class._meta
    children = [
        related_object.model
        for related_object in opts.get_all_related_objects()
        if related_object.field.rel.parent_link
    ]
    for attr in _opts_related_cache_attrs:
        try:
            delattr(opts, attr)
        except AttributeError:
            pass
    for child in children:
        clear_opts_related_cache(child)
