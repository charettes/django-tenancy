from __future__ import unicode_literals

from django.db import models
from django.dispatch.dispatcher import Signal
from django.test import SimpleTestCase

from .. import get_tenant_model
from ..signals import lazy_class_prepared, LazySignalConnector
from ..utils import remove_from_app_cache


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


class LazySignalConnectorTest(SimpleTestCase):
    def setUp(self):
        self.signal = Signal()
        self.received = []

    def receiver(self, signal, sender):
        self.received.append(sender)

    def test_immediate_execution(self):
        tenant_model = get_tenant_model()
        opts = tenant_model._meta
        connector = LazySignalConnector(opts.app_label, opts.object_name)
        connector(self.signal)(self.receiver)
        self.signal.send(tenant_model)
        self.assertEqual(self.received, [tenant_model])
        connector.disconnect(self.signal, self.receiver)
        self.signal.send(tenant_model)
        self.assertEqual(self.received, [tenant_model])

    def test_delayed_execution(self):
        connector = LazySignalConnector('tenancy', 'NotPreparedYet')
        connector(self.signal)(self.receiver)
        self.signal.send(None)
        self.assertFalse(self.received)
        prepared_model = prepare_model()
        self.signal.send(prepared_model)
        self.assertEqual(self.received, [prepared_model])

    def test_delayed_disconnected(self):
        connector = LazySignalConnector('tenancy', 'NotPreparedYet')
        connector(self.signal)(self.receiver)
        connector.disconnect(self.signal, self.receiver)
        prepared_model = prepare_model()
        self.signal.send(prepared_model)
        self.assertFalse(self.received)
