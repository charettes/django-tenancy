from __future__ import unicode_literals

import imp
from contextlib import contextmanager

from django.db.models.loading import cache as app_cache


if hasattr(app_cache, 'write_lock'):
    # TODO: Remove when support for django < 1.5 is dropped
    def app_cache_lock():
        return app_cache.write_lock
else:
    # django >= 1.5 use imp.lock instead
    @contextmanager
    def app_cache_lock():
        try:
            imp.acquire_lock()
            yield
        finally:
            imp.release_lock()


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