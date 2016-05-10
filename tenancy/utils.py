from __future__ import unicode_literals

from contextlib import contextmanager
from itertools import chain

from django.apps import apps
from django.db import models
from django.utils.functional import cached_property

from .compat import get_remote_field, get_remote_field_model


def get_model(app_label, model_name):
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


def get_forward_fields(opts):
    return chain(
        opts.fields,
        opts.many_to_many
    )


def get_reverse_fields(opts):
    return opts._get_fields(forward=False, reverse=True, include_hidden=True)


def clear_opts_related_cache(model_class):
    opts = model_class._meta
    if not opts.apps.ready:
        return
    children = [
        related_object.related_model
        for related_object in opts.__dict__.get('related_objects', []) if related_object.parent_link
    ]
    opts._expire_cache()
    for child in children:
        clear_opts_related_cache(child)


def unreference_model(model):
    disconnect_signals(model)
    for field in get_forward_fields(model._meta):
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
                        delattr(remote_field_model, remote_field.get_accessor_name())
                    except AttributeError:
                        pass


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


def clear_cached_properties(instance):
    """
    Clear the cache from the instance properties.
    """
    cls = type(instance)
    for attr in list(instance.__dict__):
        if isinstance(getattr(cls, attr, None), cached_property):
            instance.__dict__.pop(attr)


def get_postgresql_visible_constraints(cursor, table_name):
    """
    Retrieves any constraints or keys (unique, pk, fk, check, index) across one or more columns.
    """
    constraints = {}
    # Loop over the key table, collecting things as constraints
    # This will get PKs, FKs, and uniques, but not CHECK
    cursor.execute("""
        SELECT
            kc.constraint_name,
            kc.column_name,
            c.constraint_type,
            array(SELECT table_name::text || '.' || column_name::text
                  FROM information_schema.constraint_column_usage
                  WHERE constraint_name = kc.constraint_name)
        FROM information_schema.key_column_usage AS kc
        JOIN information_schema.table_constraints AS c ON
            kc.table_schema = c.table_schema AND
            kc.table_name = c.table_name AND
            kc.constraint_name = c.constraint_name
        WHERE
            kc.table_name = %s AND
            EXISTS(
                SELECT 1
                FROM pg_class AS c
                JOIN pg_namespace AS n ON
                    c.relnamespace = n.oid
                WHERE
                    n.nspname = kc.table_schema AND
                    c.relname = kc.table_name AND
                    pg_catalog.pg_table_is_visible(c.oid)
            )
        ORDER BY kc.ordinal_position ASC
    """, [table_name])
    for constraint, column, kind, used_cols in cursor.fetchall():
        # If we're the first column, make the record
        if constraint not in constraints:
            constraints[constraint] = {
                "columns": [],
                "primary_key": kind.lower() == "primary key",
                "unique": kind.lower() in ["primary key", "unique"],
                "foreign_key": tuple(used_cols[0].split(".", 1)) if kind.lower() == "foreign key" else None,
                "check": False,
                "index": False,
            }
        # Record the details
        constraints[constraint]['columns'].append(column)
    # Now get CHECK constraint columns
    cursor.execute("""
        SELECT kc.constraint_name, kc.column_name
        FROM information_schema.constraint_column_usage AS kc
        JOIN information_schema.table_constraints AS c ON
            kc.table_schema = c.table_schema AND
            kc.table_name = c.table_name AND
            kc.constraint_name = c.constraint_name
        WHERE
            c.constraint_type = 'CHECK' AND
            kc.table_name = %s AND
            EXISTS(
                SELECT 1
                FROM pg_class AS c
                JOIN pg_namespace AS n ON
                    c.relnamespace = n.oid
                WHERE
                    n.nspname = kc.table_schema AND
                    c.relname = kc.table_name AND
                    pg_catalog.pg_table_is_visible(c.oid)
            )
    """, [table_name])
    for constraint, column in cursor.fetchall():
        # If we're the first column, make the record
        if constraint not in constraints:
            constraints[constraint] = {
                "columns": [],
                "primary_key": False,
                "unique": False,
                "foreign_key": None,
                "check": True,
                "index": False,
            }
        # Record the details
        constraints[constraint]['columns'].append(column)
    # Now get indexes
    cursor.execute("""
        SELECT
            c2.relname,
            ARRAY(
                SELECT (SELECT attname FROM pg_catalog.pg_attribute WHERE attnum = i AND attrelid = c.oid)
                FROM unnest(idx.indkey) i
            ),
            idx.indisunique,
            idx.indisprimary
        FROM pg_catalog.pg_class c, pg_catalog.pg_class c2,
            pg_catalog.pg_index idx
        WHERE c.oid = idx.indrelid
            AND idx.indexrelid = c2.oid
            AND c.relname = %s
    """, [table_name])
    for index, columns, unique, primary in cursor.fetchall():
        if index not in constraints:
            constraints[index] = {
                "columns": list(columns),
                "primary_key": primary,
                "unique": unique,
                "foreign_key": None,
                "check": False,
                "index": True,
            }
    return constraints


@contextmanager
def patch_connection_introspection(connection):
    if connection.vendor == 'postgresql':
        get_constraints = connection.introspection.get_constraints
        connection.introspection.get_constraints = get_postgresql_visible_constraints
    try:
        yield
    finally:
        if connection.vendor == 'postgresql':
            connection.introspection.get_constraints = get_constraints
