from __future__ import unicode_literals

from django import forms

from .models import SpecificModel


class SpecificModelForm(forms.ModelForm):
    class Meta:
        model = SpecificModel


class ModelFormSubclass(forms.ModelForm):
    pass


class BaseInlineFormSetSubclass(forms.models.BaseInlineFormSet):
    pass
