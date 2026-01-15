from django.contrib import admin
from .models import Collection,Contributor
# Register your models here.
admin.site.register([Collection,Contributor])