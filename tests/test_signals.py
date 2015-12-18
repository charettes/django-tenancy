from __future__ import unicode_literals

from django.db import models
from django.test import SimpleTestCase

from tenancy import get_tenant_model
from tenancy.signals import lazy_class_prepared
from tenancy.utils import remove_from_app_cache


def prepare_model():
    class NotPreparedYet(models.Model):
        class Meta:
            app_label = 'tenancy'
            managed = True
    remove_from_app_cache(NotPreparedYet)
    return NotPreparedYet


class LazyClassPreparedTest(SimpleTestCase):
    def setUp(self):
        self.prepared_model = None

    def callback(self, model):
        self.prepared_model = model

    def test_immediate_execution(self):
        tenant_model = get_tenant_model()
        opts = tenant_model._meta
        lazy_class_prepared(opts.app_label, opts.object_name, self.callback)

    def test_delayed_execution(self):
        lazy_class_prepared('tenancy', 'NotPreparedYet', self.callback)
        self.assertIsNone(self.prepared_model)
        prepared_model = prepare_model()
        self.assertEqual(self.prepared_model, prepared_model)
