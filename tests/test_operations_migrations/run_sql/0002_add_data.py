# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tenancy.models import Tenant
from tenancy.operations import RunSQL


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0001_create_model'),
    ]

    operations = [
        RunSQL(
            Tenant,
            "INSERT INTO tests_runsql (id) VALUES (1)",
            "DELETE FROM tests_runsql",
        ),
    ]
