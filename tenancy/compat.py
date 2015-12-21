from __future__ import unicode_literals

from operator import attrgetter

import django

get_related_model = attrgetter('related_model' if django.VERSION >= (1, 8) else 'model')


if django.VERSION >= (1, 8):
    def get_remote_field_accessor_name(field):
        return get_remote_field(field).get_accessor_name()

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

    def contribute_to_related_class(model, field):
        field.contribute_to_related_class(model, get_remote_field(field))
else:
    def get_remote_field_accessor_name(field):
        return field.related.get_accessor_name()

    def get_reverse_fields(opts):
        return opts.get_all_related_objects(include_hidden=True)

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
        if not opts.apps.ready:
            return
        if hasattr(model_class, '_related_objects_cache'):
            children = [
                related_object.model
                for related_object in opts.get_all_related_objects()
                if related_object.field.rel.parent_link
            ]
        else:
            children = []
        for attr in _opts_related_cache_attrs:
            try:
                delattr(opts, attr)
            except AttributeError:
                pass
        for child in children:
            clear_opts_related_cache(child)

    def contribute_to_related_class(model, field):
        field.contribute_to_related_class(model, field.related)


if django.VERSION >= (1, 9):
    def get_remote_field(field):
        return field.remote_field

    def get_remote_field_model(field):
        return field.remote_field.model

    def set_remote_field_model(field, model):
        field.remote_field.model = model

    def get_related_descriptor_field(descriptor):
        return descriptor.field

    from django.db.models.fields.related import lazy_related_operation  # noqa
else:
    def get_remote_field(field):
        return getattr(field, 'rel', None)

    def get_remote_field_model(field):
        return field.rel.to

    def set_remote_field_model(field, model):
        field.rel.to = model

    def get_related_descriptor_field(descriptor):
        return descriptor.related.field

    from django.db.models.fields.related import add_lazy_relation

    def lazy_related_operation(function, model, related_model, field):
        def operation(field, related, local):
            return function(local, related, field)
        add_lazy_relation(model, field, related_model, operation)
