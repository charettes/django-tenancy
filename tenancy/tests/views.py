from __future__ import unicode_literals

from django.core import serializers
from django.db import models
from django.http import HttpResponse
from django.views.generic.base import View

from ..views import SingleTenantObjectMixin

from .models import SpecificModel


class MissingModelView(SingleTenantObjectMixin, View):
    def get(self, request, *args, **kwargs):
        self.get_queryset()


class InvalidModelView(MissingModelView):
    model = models.Model

    def get(self, request, *args, **kwargs):
        self.get_queryset()


class SingleTenantObjectView(SingleTenantObjectMixin, View):
    model = SpecificModel

    def get(self, request, *args, **kwargs):
        return HttpResponse(serializers.serialize('json', [self.get_object()]))