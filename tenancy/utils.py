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


class SchemaConstraints(object):
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, cursor, table_name):
        """
        Retrieve any constraints or keys (unique, pk, fk, check, index) across
        one or more columns. Also retrieve the definition of expression-based
        indexes.
        """
        constraints = {}
        # Loop over the key table, collecting things as constraints. The column
        # array must return column names in the same order in which they were
        # created.
        # The subquery containing generate_series can be replaced with
        # "WITH ORDINALITY" when support for PostgreSQL 9.3 is dropped.
        cursor.execute("""
            SELECT
                c.conname,
                array(
                    SELECT attname
                    FROM (
                        SELECT unnest(c.conkey) AS colid,
                               generate_series(1, array_length(c.conkey, 1)) AS arridx
                    ) AS cols
                    JOIN pg_attribute AS ca ON cols.colid = ca.attnum
                    WHERE ca.attrelid = c.conrelid
                    ORDER BY cols.arridx
                ),
                c.contype,
                (SELECT fkc.relname || '.' || fka.attname
                FROM pg_attribute AS fka
                JOIN pg_class AS fkc ON fka.attrelid = fkc.oid
                WHERE fka.attrelid = c.confrelid AND fka.attnum = c.confkey[1])
            FROM pg_constraint AS c
            JOIN pg_class AS cl ON c.conrelid = cl.oid
            JOIN pg_namespace AS ns ON cl.relnamespace = ns.oid
            WHERE ns.nspname = %s AND cl.relname = %s
        """, [self.schema, table_name])
        for constraint, columns, kind, used_cols in cursor.fetchall():
            constraints[constraint] = {
                "columns": columns,
                "primary_key": kind == "p",
                "unique": kind in ["p", "u"],
                "foreign_key": tuple(used_cols.split(".", 1)) if kind == "f" else None,
                "check": kind == "c",
                "index": False,
                "definition": None,
            }
        # Now get indexes
        cursor.execute("""
            SELECT
                indexname, array_agg(attname), indisunique, indisprimary,
                array_agg(ordering), amname, exprdef
            FROM (
                SELECT
                    c2.relname as indexname, idx.*, attr.attname, am.amname,
                    CASE
                        WHEN idx.indexprs IS NOT NULL THEN
                            pg_get_indexdef(idx.indexrelid)
                    END AS exprdef,
                    CASE
                        WHEN am.amcanorder THEN
                            CASE (option & 1)
                                WHEN 1 THEN 'DESC' ELSE 'ASC'
                            END
                    END as ordering
                FROM (
                    SELECT
                        *, unnest(i.indkey) as key, unnest(i.indoption) as option
                    FROM pg_index i
                ) idx
                LEFT JOIN pg_class c ON idx.indrelid = c.oid
                LEFT JOIN pg_class c2 ON idx.indexrelid = c2.oid
                LEFT JOIN pg_am am ON c2.relam = am.oid
                LEFT JOIN pg_attribute attr ON attr.attrelid = c.oid AND attr.attnum = idx.key
                LEFT JOIN pg_catalog.pg_namespace ns ON c.relnamespace = ns.oid
                WHERE ns.nspname = %s AND c.relname = %s
            ) s2
            GROUP BY indexname, indisunique, indisprimary, amname, exprdef;
        """, [self.schema, table_name])
        for index, columns, unique, primary, orders, type_, definition in cursor.fetchall():
            if index not in constraints:
                constraints[index] = {
                    "columns": columns if columns != [None] else [],
                    "orders": orders if orders != [None] else [],
                    "primary_key": primary,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": type_,
                    "definition": definition,
                }
        return constraints


@contextmanager
def patch_connection_introspection(connection, schema):
    if connection.vendor == 'postgresql':
        get_constraints = connection.introspection.get_constraints
        connection.introspection.get_constraints = SchemaConstraints(schema)
    try:
        yield
    finally:
        if connection.vendor == 'postgresql':
            connection.introspection.get_constraints = get_constraints
