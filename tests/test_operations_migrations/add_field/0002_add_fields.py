# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from tenancy.operations import AddFied


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        AddFied('AddField', 'charfield', models.CharField(max_length=100, default='', unique=True)),
        AddFied('AddField', 'textfield', models.TextField(db_index=True)),
        AddFied('AddField', 'positiveintegerfield', models.PositiveIntegerField(default=0)),
        AddFied('AddField', 'foreign_key', models.ForeignKey('tests.AddField', null=True, on_delete=models.CASCADE)),
    ]
