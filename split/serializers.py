from .models import *
from rest_framework.serializers import ModelSerializer, UUIDField

class CollectionSerializers(ModelSerializer):
  class Meta:
    model = Collection
    fields = "__all__"

class ContributorSerializer(ModelSerializer):
    collection_id = UUIDField(write_only=True)  # Accept collection_id in POST
    
    class Meta:
        model = Contributor
        fields = [
            'id',
            'collection_id',  # For input
            'name',
            'phone',
            'email',
            'amount_owed',
            'amount_paid',
            'payment_status',
            'payment_reference',
            'created_at',
            'paid_at'
        ]
        read_only_fields = ['id', 'payment_status', 'payment_reference', 'created_at', 'paid_at']
    
    def validate_phone(self, value):
        """Validate Nigerian phone number"""
        phone = value.replace(' ', '').replace('-', '')
        
        if phone.startswith('0') and len(phone) == 11:
            return phone
        if phone.startswith('+234') and len(phone) == 14:
            return phone
        if phone.startswith('234') and len(phone) == 13:
            return phone
        
        raise serializers.ValidationError(
            'Invalid phone number format. Use: 08012345678'
        )

    
class TransactionSeriliazer(ModelSerializer):
  class Meta:
    model = Transaction
    fields = "__all__"