from __future__ import unicode_literals

from django import forms
from django.forms.models import inlineformset_factory, modelformset_factory

from .models import NonTenantModel, RelatedTenantModel, SpecificModel


class SpecificModelForm(forms.ModelForm):
    class Meta:
        model = SpecificModel
        fields = ['date', 'hidden_non_tenant', 'non_tenant']


class MissingModelForm(forms.ModelForm):
    class Meta:
        fields = ['id']


class RelatedTenantModelForm(forms.ModelForm):
    class Meta:
        model = RelatedTenantModel
        fields = ['m2m']


SpecificModelFormSet = modelformset_factory(SpecificModel, SpecificModelForm)


NonTenantInlineFormSet = inlineformset_factory(
    NonTenantModel, SpecificModel, SpecificModelForm, fk_name='non_tenant'
)


RelatedInlineFormSet = inlineformset_factory(
    SpecificModel, RelatedTenantModel, RelatedTenantModelForm
)
