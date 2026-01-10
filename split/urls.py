from django.contrib import admin
from django.urls import path
from .views import *

urlpatterns = [
	path("collections",create_collections)
]