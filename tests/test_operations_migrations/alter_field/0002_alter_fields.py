# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from tenancy.operations import AlterField


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        AlterField(
            'AlterField', 'charfield', models.CharField(max_length=100, unique=True),
        ),
        AlterField(
            'AlterField', 'integerfield', models.PositiveIntegerField()
        ),
        AlterField(
            'AlterField', 'foreign_key', models.ForeignKey('self', on_delete=models.CASCADE)
        ),
    ]
