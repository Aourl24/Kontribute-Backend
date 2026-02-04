from django.contrib import admin
from django.urls import path
from . import views
app_name = 'kontribute'

urlpatterns = [
    # Collection endpoints
    path('collections/', views.create_collections, name='create_collection'),
    path('collections/<slug:slug>/', views.get_collection, name='get_collection'),
    
    # Manual Payment endpoints (existing)
    path('collections/<slug:slug>/contribute/', views.make_contribution, name='make_contribution'),
    path('collections/<slug:slug>/confirm-payment/', views.confirm_payment, name='confirm_payment'),
    
    # Automatic Payment endpoints (NEW - Paystack)
    path('collections/<slug:slug>/contribute-auto/', views.make_automatic_contribution, name='make_automatic_contribution'),
    path('verify-payment/<str:reference>/', views.verify_payment, name='verify_payment'),
    
    # Dashboard
    path('collections/<slug:slug>/dashboard/', views.get_dashboard, name='get_dashboard'),
    
    # Reminders
    path('collections/<slug:slug>/send-reminders/', views.send_reminders, name='send_reminders'),
    
    # Withdrawal
    path('collections/<slug:slug>/withdraw/', views.request_withdrawal, name='request_withdrawal'),
    
    # Receipt
    path('receipt/<uuid:contributor_id>/', views.get_receipt, name='get_receipt'),
    
    # Paystack webhook
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
]
