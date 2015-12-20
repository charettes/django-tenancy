from __future__ import unicode_literals

from contextlib import contextmanager
from itertools import chain

from django.apps import apps
from django.db import models

from .compat import (
    clear_opts_related_cache, get_remote_field, get_remote_field_accessor_name,
    get_remote_field_model,
)


def get_model(app_label, model_name, **kwargs):
    try:
        return apps.get_registered_model(app_label, model_name)
    except LookupError:
        pass


@contextmanager
def apps_lock():
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
    app_label, model_name = opts.app_label, opts.model_name
    with apps_lock():
        try:
            model_class = apps.app_configs[app_label].models.pop(model_name)
        except KeyError:
            if not quiet:
                raise ValueError("%r is not cached" % model_class)
        apps.clear_cache()
        unreference_model(model_class)
    return model_class


def get_foward_fields(opts):
    return chain(
        opts.fields,
        opts.many_to_many
    )


def unreference_model(model):
    disconnect_signals(model)
    for field in get_foward_fields(model._meta):
        remote_field = get_remote_field(field)
        if field.model is model and remote_field:
            remote_field_model = get_remote_field_model(field)
            if isinstance(remote_field_model, models.base.ModelBase):
                clear_opts_related_cache(remote_field_model)
                rel_is_hidden = remote_field.is_hidden()
                # An accessor is added to related classes if they are not
                # hidden. However o2o fields *always* add an accessor
                # even if the relationship is hidden.
                o2o = isinstance(field, models.OneToOneField)
                if not rel_is_hidden or o2o:
                    try:
                        delattr(remote_field_model, get_remote_field_accessor_name(field))
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
