from __future__ import unicode_literals

import django

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
