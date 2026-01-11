from django.contrib import admin
from django.urls import path
from . import views
app_name = 'kontribute'

urlpatterns = [
    # Collection endpoints
    path('collections/', views.create_collections, name='create-collection'),
    path('collections/<slug:slug>/', views.get_collection, name='get-collection'),
    path('collections/<slug:slug>/dashboard/', views.get_dashboard, name='dashboard'),
    
    # Contribution endpoints
    path('collections/<slug:slug>/contribute/', views.make_contribution, name='contribute'),
    path('collections/<slug:slug>/confirm-payment/', views.confirm_payment, name='confirm-payment'),
    
    # Action endpoints
    path('collections/<slug:slug>/remind/', views.send_reminders, name='send-reminders'),
    path('collections/<slug:slug>/withdraw/', views.request_withdrawal, name='withdraw'),
    
    # Webhook
    path('webhooks/paystack/', views.paystack_webhook, name='paystack-webhook'),
    
    # Receipt
    path('receipts/<uuid:contributor_id>/', views.get_receipt, name='get-receipt'),
]
