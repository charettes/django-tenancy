# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from tenancy.operations import AddField


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        AddField('AddField', 'charfield', models.CharField(max_length=100, default='', unique=True)),
        AddField('AddField', 'textfield', models.TextField(db_index=True)),
        AddField('AddField', 'positiveintegerfield', models.PositiveIntegerField(default=0)),
        AddField('AddField', 'foreign_key', models.ForeignKey('tests.AddField', null=True, on_delete=models.CASCADE)),
    ]
