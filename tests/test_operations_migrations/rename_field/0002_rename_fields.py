# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tenancy.operations import RenameField


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        RenameField('RenameField', 'charfield', 'renamed_charfield'),
        RenameField('RenameField', 'foreign_key', 'renamed_foreign_key'),
    ]
