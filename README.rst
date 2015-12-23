**************
django-tenancy
**************

Handle multi-tenancy in Django with no additional global state using schemas.

.. image:: https://travis-ci.org/charettes/django-tenancy.png?branch=master
    :target: http://travis-ci.org/charettes/django-tenancy

.. image:: https://coveralls.io/repos/charettes/django-tenancy/badge.png?branch=master
   :target: https://coveralls.io/r/charettes/django-tenancy

Installation
============
Assuming you have django installed, the first step is to install
*django-tenancy*:

::

   pip install django-tenancy

Now you can import the ``tenancy`` module in your Django project.

Using django-tenancy
====================

Define a Tenant Model
---------------------

The tenant model must be a subclass of ``tenancy.models.AbstractTenant``.

For instance, your ``myapp/models.py`` might look like:

::

   from tenancy.models import AbstractTenant

   class MyTenantModel(AbstractTenant):
      name = models.CharField(max_length=50)
      # other fields
      def natural_key(self):
         return (self.name, )

**Important note**: the ``natural_key`` method must return a tuple that will
be used to prefix the model and its database table. This prefix must be unique
to the tenant.

Declare the Tenant Model
------------------------
Now that you have your tenant model, let's declare in your project in
*settings.py*:

::

   TENANCY_TENANT_MODEL = 'myapp.MyTenantModel'

Run a database synchronization to create the corresponding table:

::

   python manage.py syncdb

Define the tenant-specific models
---------------------------------
The tenant-specific models must subclass ``tenancy.models.TenantModel``.

For instance, each tenant will have projects and reports. Here is how
``myapp/models.py`` might look like:

::

   from tenancy.models import AbstractTenant, TenantModel

   class MyTenantModel(AbstractTenant):
      name = models.CharField(max_length=50)
      # other fields
      def natural_key(self):
         return (self.name, )

   class Project(TenantModel):
      name = models.CharField(max_length=50)
      description = models.CharField(max_length=300, blank=True, null=True)

   class Report(TenantModel):
      name = models.CharField(max_length=50)
      content = models.CharField(max_length=300, blank=True, null=True)

Playing with the defined models
-------------------------------
You can manipulate the tenant and tenant-specific models as any other Django
models.

Create a tenant instance
^^^^^^^^^^^^^^^^^^^^^^^^
::

   tenant = MyTenantModel.objects.create("myfirsttenant")

Get a tenant-specific model: for_tenant()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<TenantModel>.for_tenant(<AbtractTenantConcreteSubclass instance>)

``TenantModel`` comes with a method that allows you to get the specific
``AbstractTenantModel`` for a given Tenant instance. For instance:

::

   tenant_project = Project.for_tenant(tenant)

Create a tenant-specific model instance
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

   tenant_project.objects.create("myfirsttenant_project")


Python 3.5
----------

An issue with circular references between ``Model`` objects prevent garbage
collection of tenant specific models on tenant deletion.
