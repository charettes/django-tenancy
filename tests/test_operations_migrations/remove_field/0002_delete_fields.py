# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tenancy.operations import RemoveField


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        RemoveField('RemoveField', 'charfield'),
        RemoveField('RemoveField', 'foreign_key'),
    ]
