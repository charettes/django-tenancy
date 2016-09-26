# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tenancy.models import Tenant
from tenancy.operations import RunPython


def foward(apps, schema_editor):
    assert hasattr(schema_editor, 'tenant')
    apps.get_model('tests', 'RunPython').objects.create()


def backward(apps, schema_editor):
    assert hasattr(schema_editor, 'tenant')
    apps.get_model('tests', 'RunPython').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        RunPython(
            Tenant,
            foward,
            backward,
        ),
    ]
