from django.conf.urls import patterns, url

from . import views

urlpatterns = patterns('',
    url(r'^missing-model$',
        views.MissingModelView.as_view()),
    url(r'^invalid-model$',
        views.InvalidModelView.as_view()),
    url(r'^specific-model/(?P<pk>\d+)$',
        views.SingleTenantObjectView.as_view()),
)