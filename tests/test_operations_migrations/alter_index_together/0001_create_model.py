# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from tenancy.models import Managed
from tenancy.operations import AlterIndexTogether, CreateModel


class Migration(migrations.Migration):

    operations = [
        CreateModel(
            name='AlterIndexTogether',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=10)),
            ],
            bases=(models.Model,),
            options={
                'managed': Managed('tenancy.Tenant'),
            }
        ),
        AlterIndexTogether('AlterIndexTogether', {('id', 'name')}),
    ]
