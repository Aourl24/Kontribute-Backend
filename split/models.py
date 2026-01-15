from django.db import models
import uuid
from django.utils.text import slugify

class Collection(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('withdrawn', 'Withdrawn'),
    ]
   
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=100,blank=True)
   
    # Collection details
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2,null=True,blank=True)
    amount_per_person = models.DecimalField(max_digits=12, decimal_places=2,null=True,blank=True)
    number_of_people = models.IntegerField(null=True,blank=True)
    #target_amount = models.DecimalField(max_digits=12, decimal_places=2,null=True,blank=True)
   
    # Organizer details
    organizer_name = models.CharField(max_length=100)
    organizer_phone = models.CharField(max_length=20)
    organizer_email = models.EmailField(blank=True)
   
    # Withdrawal details
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
   
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    deadline = models.DateTimeField(null=True, blank=True)
   
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
   
    # Paystack
    paystack_subaccount = models.CharField(max_length=100, blank=True,null=True)
    
     # Add these for manual payments:
    organizer_bank_name = models.CharField(max_length=100, blank=True)
    organizer_account_number = models.CharField(max_length=20, blank=True)
    organizer_account_name = models.CharField(max_length=100, blank=True)


   
    def __str__(self):
        return self.title
   
    @property
    def total_collected(self):
        return self.contributors.filter(payment_status='paid').aggregate(
            total=models.Sum('amount_paid')
        )['total'] or 0
   
    @property
    def paid_count(self):
        return self.contributors.filter(payment_status='paid').count()


class Contributor(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
   
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='contributors')
   
    # Contributor details
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
   
    # Payment details
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
   
    # Paystack
    payment_reference = models.CharField(max_length=100, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
   
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    payment_method = models.CharField(
        max_length=20,
        default='bank_transfer',
        choices=[
            ('bank_transfer', 'Bank Transfer'),
            ('card', 'Card'),
            ('ussd', 'USSD')
        ]
    )
    payment_proof = models.TextField(blank=True)
    verified_by = models.CharField(max_length=100, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
   
    def __str__(self):
        return f"{self.name} - {self.collection.title}"


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
   
    TYPE_CHOICES = [
        ('payment', 'Payment'),
        ('withdrawal', 'Withdrawal'),
        ('refund', 'Refund'),
    ]
   
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='transactions')
    contributor = models.ForeignKey(Contributor, on_delete=models.SET_NULL, null=True, blank=True)
   
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
   
    # References
    reference = models.CharField(max_length=100, unique=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
   
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
   
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
   
    def __str__(self):
        return f"{self.transaction_type} - {self.reference}"


class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
   
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.OneToOneField(Collection, on_delete=models.CASCADE)
   
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
   
    # Bank details
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=100)
   
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
   
    # Paystack
    transfer_code = models.CharField(max_length=100, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
   
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
   
    def __str__(self):
        return f"Withdrawal - {self.collection.title}"