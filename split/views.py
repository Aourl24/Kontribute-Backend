from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Q
from .serializers import (
    CollectionSerializers, 
    ContributorSerializer,
    TransactionSeriliazer
)
from django.utils.text import slugify
import uuid
from .models import Collection, Contributor, Transaction

website_url = "http://127.0.0.1:8000"
website_url = "http://10.42.134.92:8000"

def response(status_bool, message, data=None, code=None, errors=None, **others):
    """Helper function for consistent API responses"""
    if code == None:
        status_code = status.HTTP_200_OK if status_bool == True else status.HTTP_400_BAD_REQUEST
    else:
        status_code = code
    
    return Response({
        'status': "success" if status_bool == True else "failed",
        'message': message,
        'errors': errors,
        'data': data,
        **others
    }, status=status_code)


# ==================== COLLECTION ENDPOINTS ====================

@api_view(['POST'])
def create_collections(request):
    """Create a new collection"""
    try:
        serializers = CollectionSerializers(data=request.data)
        
        if not serializers.is_valid():
            return response(False, "The data are not valid", errors=serializers.errors)
        
        validated_data = serializers.validated_data
        base_slug = slugify(validated_data['title'])
        unique_slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        
        # Calculate total amount
        total_amount_conditions = [
            validated_data.get('amount_per_person'),
            validated_data.get('number_of_people')
        ]
        if all(total_amount_conditions):
            validated_data["total_amount"] = (
                validated_data['amount_per_person'] * 
                validated_data['number_of_people']
            )
        
        collection = Collection.objects.create(
            **validated_data,
            slug=unique_slug,
            status='active'
        )
        
        response_serializer = CollectionSerializers(collection)
        
        return response(
            True, 
            "Collection Created Successfully",
            data=response_serializer.data,
            code=status.HTTP_201_CREATED,
            collection_url=f"{website_url}/collections/{collection.slug}"
        )
        
    except Exception as e:
        return response(
            False, 
            "An error occurred while creating the collection",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])   
def get_collection(request, slug):
    """Get collection details by slug"""
    try:
        collection = get_object_or_404(Collection, slug=slug)
        serializers = CollectionSerializers(collection)
        
        # Get contribution stats
        total_collected = collection.contributors.filter(
            payment_status='paid'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        paid_count = collection.contributors.filter(payment_status='paid').count()
        pending_count = collection.contributors.filter(payment_status='pending').count()
        if collection.total_amount:
          completion_percentage = round( (total_collected / collection.total_amount * 100) if collection.total_amount > 0 else 0, 2)
        else:
          completion_percentage = 100
        
        return response(
            True,
            "Collection retrieved successfully",
            data={
                **serializers.data,
                'stats': {
                    'total_collected': float(total_collected),
                    'paid_count': paid_count,
                    'pending_count': pending_count,
                    'total_contributors': paid_count + pending_count,
                    'completion_percentage': completion_percentage
                }
            }
        )
    except Exception as e:
        return response(
            False,
            "Error fetching Collection",
            errors=str(e),
            code=status.HTTP_404_NOT_FOUND
        )


# ==================== CONTRIBUTION ENDPOINTS ====================

@api_view(["POST"])
def make_contribution(request, slug):
    """
    Create a contributor - Manual Payment Version
    
    Expected payload:
    {
        "name": "John Doe",
        "phone": "08012345678",
        "email": "john@email.com" (optional)
    }
    """
    try:
        # Get collection
        collection = get_object_or_404(Collection, slug=slug)
        
        # Check if collection is still active
        if collection.status != 'active':
            return response(
                False,
                "This collection is no longer accepting contributions",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if deadline passed
        if collection.deadline and collection.deadline < timezone.now():
            return response(
                False,
                "This collection deadline has passed",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate input data
        required_fields = ['name', 'phone']
        if not collection.amount_per_person:
          required_fields.append("amount")
          
        for field in required_fields:
            if field not in request.data:
                return response(
                    False,
                    f"Missing required field: {field}",
                    code=status.HTTP_400_BAD_REQUEST
                )
        
        amount_to_be_paid = collection.amount_per_person if collection.amount_per_person else request.data["amount"]
        # Check for duplicate contribution (same phone number)
        existing_contributor = Contributor.objects.filter(
            collection=collection,
            phone=request.data['phone']
        ).first()
        
        if existing_contributor:
            if existing_contributor.payment_status == 'paid':
                return response(
                    False,
                    "This phone number has already contributed to this collection",
                    code=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Return existing pending contribution
                return response(
                    True,
                    "You already have a pending contribution. Please complete payment.",
                    data={
                        'contributor_id': str(existing_contributor.id),
                        'payment_reference': existing_contributor.payment_reference,
                        'bank_details': {
                            'bank_name': collection.organizer_bank_name,
                            'account_number': collection.organizer_account_number,
                            'account_name': collection.organizer_account_name
                        },
                        'amount': existing_contributor.amount_owed,
                        'status': 'pending'
                    }
                )
        
        # Create contributor record
        payment_reference = f"KTR-{uuid.uuid4().hex[:8].upper()}"
        
        print(amount_to_be_paid)
        contributor = Contributor.objects.create(
            collection=collection,
            name=request.data['name'],
            phone=request.data['phone'],
            email=request.data.get('email', ''),
            amount_owed=amount_to_be_paid,
            amount_paid=0,
            payment_status='pending',
            payment_method='bank_transfer',
            payment_reference=payment_reference
        )
        
        # Create transaction record
        transaction = Transaction.objects.create(
            collection=collection,
            contributor=contributor,
            transaction_type='payment',
            amount=amount_to_be_paid,
            status='pending',
            reference=payment_reference
        )
        print("about to take off")
        
        # Return payment instructions
        return response(
            True,
            "Contributor added successfully. Please complete payment.",
            data={
                'contributor_id': str(contributor.id),
                'payment_reference': payment_reference,
                'bank_details': {
                    'bank_name': collection.organizer_bank_name or 'Not provided',
                    'account_number': collection.organizer_account_number or 'Not provided',
                    'account_name': collection.organizer_account_name or 'Not provided'
                },
                'amount': float(amount_to_be_paid),
                'instructions': [
                    f"1. Transfer exactly ₦{amount_to_be_paid} to the account above",
                    f"2. Use reference: {payment_reference}",
                    "3. Keep your bank receipt/reference",
                    "4. Confirmation may take a few minutes"
                ]
            },
            code=status.HTTP_201_CREATED
        )
        
    except Collection.DoesNotExist:
        return response(
            False,
            "Collection not found",
            code=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return response(
            False,
            "An error occurred while processing your contribution",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def confirm_payment(request, slug):
    """
    Confirm manual payment by organizer
    
    Expected payload:
    {
        "contributor_id": "uuid-here",
        "payment_proof": "Bank reference or note"
    }
    """
    try:
        collection = get_object_or_404(Collection, slug=slug)
        
        # Get contributor
        contributor_id = request.data.get('contributor_id')
        if not contributor_id:
            return response(
                False,
                "Contributor ID is required",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        contributor = get_object_or_404(
            Contributor, 
            id=contributor_id,
            collection=collection
        )
        
        # Check if already paid
        if contributor.payment_status == 'paid':
            return response(
                False,
                "This contribution has already been confirmed",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # Update contributor
        contributor.payment_status = 'paid'
        contributor.amount_paid = contributor.amount_owed
        contributor.paid_at = timezone.now()
        contributor.payment_proof = request.data.get('payment_proof', '')
        contributor.verified_by = request.data.get('verified_by', 'organizer')
        contributor.verified_at = timezone.now()
        contributor.save()
        
        # Update transaction
        transaction = Transaction.objects.filter(
            contributor=contributor,
            status='pending'
        ).first()
        
        if transaction:
            transaction.status = 'success'
            transaction.save()
        
        return response(
            True,
            "Payment confirmed successfully",
            data={
                'contributor_id': str(contributor.id),
                'name': contributor.name,
                'amount_paid': float(contributor.amount_paid),
                'paid_at': contributor.paid_at.isoformat()
            }
        )
        
    except Exception as e:
        return response(
            False,
            "An error occurred while confirming payment",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== DASHBOARD ENDPOINT ====================

@api_view(['GET'])
def get_dashboard(request, slug):
    """
    Get organizer dashboard with all contributors and stats
    """
    try:
        collection = get_object_or_404(Collection, slug=slug)
        
        # Get all contributors
        contributors = collection.contributors.all().order_by('-created_at')
        
        # Separate paid and pending
        paid_contributors = contributors.filter(payment_status='paid')
        pending_contributors = contributors.filter(payment_status='pending')
        
        # Calculate stats
        total_collected = paid_contributors.aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        # Serialize contributors
        paid_data = ContributorSerializer(paid_contributors, many=True).data
        pending_data = ContributorSerializer(pending_contributors, many=True).data
        
        return response(
            True,
            "Dashboard data retrieved successfully",
            data={
                'collection': {
                    'id': str(collection.id),
                    'title': collection.title,
                    'slug': collection.slug,
                    'total_amount': float(collection.total_amount),
                    'amount_per_person': float(collection.amount_per_person) if collection.amount_per_person else "Flexible amount",
                    'number_of_people': collection.number_of_people,
                    'status': collection.status,
                    'deadline': collection.deadline.isoformat() if collection.deadline else None,
                    'created_at': collection.created_at.isoformat()
                },
                'stats': {
                    'total_collected': float(total_collected),
                    'total_target': float(collection.total_amount),
                    'paid_count': paid_contributors.count(),
                    'pending_count': pending_contributors.count(),
                    'total_contributors': contributors.count(),
                    'completion_percentage': round(
                        (total_collected / collection.total_amount * 100) 
                        if collection.total_amount > 0 else 0, 
                        2
                    )
                },
                'contributors': {
                    'paid': paid_data,
                    'pending': pending_data
                }
            }
        )
        
    except Exception as e:
        return response(
            False,
            "Error retrieving dashboard data",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== REMINDER ENDPOINT ====================

@api_view(['POST'])
def send_reminders(request, slug):
    """
    Send payment reminders to pending contributors
    
    Expected payload (optional):
    {
        "contributor_ids": ["uuid1", "uuid2"]  // If empty, reminds all pending
    }
    """
    try:
        collection = get_object_or_404(Collection, slug=slug)
        
        # Get contributor IDs to remind
        contributor_ids = request.data.get('contributor_ids', [])
        
        if contributor_ids:
            # Remind specific contributors
            pending_contributors = Contributor.objects.filter(
                id__in=contributor_ids,
                collection=collection,
                payment_status='pending'
            )
        else:
            # Remind all pending contributors
            pending_contributors = collection.contributors.filter(
                payment_status='pending'
            )
        
        if not pending_contributors.exists():
            return response(
                False,
                "No pending contributors to remind",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Implement actual SMS/Email sending here
        # For now, just return success
        
        reminded_count = pending_contributors.count()
        reminded_list = [
            {
                'name': c.name,
                'phone': c.phone,
                'amount_owed': float(c.amount_owed)
            }
            for c in pending_contributors
        ]
        
        return response(
            True,
            f"Reminders sent to {reminded_count} contributor(s)",
            data={
                'reminded_count': reminded_count,
                'contributors': reminded_list
            }
        )
        
    except Exception as e:
        return response(
            False,
            "Error sending reminders",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== WITHDRAWAL ENDPOINT ====================

@api_view(['POST'])
def request_withdrawal(request, slug):
    """
    Request withdrawal (for future implementation)
    Currently just marks collection as closed
    
    Expected payload:
    {
        "bank_name": "GTBank",
        "account_number": "0123456789",
        "account_name": "John Doe"
    }
    """
    try:
        collection = get_object_or_404(Collection, slug=slug)
        
        # Check if collection has any paid contributions
        paid_count = collection.contributors.filter(payment_status='paid').count()
        
        if paid_count == 0:
            return response(
                False,
                "No confirmed payments to withdraw",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate total to withdraw
        total_collected = collection.contributors.filter(
            payment_status='paid'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Update collection status
        collection.status = 'closed'
        collection.save()
        
        # For manual system, just return confirmation
        # In future with Paystack, you'd initiate actual transfer here
        
        return response(
            True,
            "Withdrawal request submitted. Collection is now closed.",
            data={
                'collection_id': str(collection.id),
                'total_amount': float(total_collected),
                'paid_contributors': paid_count,
                'status': 'Collection closed - contact organizer for withdrawal details',
                'message': 'For manual payments, organizer already received funds directly.'
            }
        )
        
    except Exception as e:
        return response(
            False,
            "Error processing withdrawal request",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== WEBHOOK ENDPOINT (For Future Paystack Integration) ====================

@csrf_exempt
@api_view(['POST'])
def paystack_webhook(request):
    """
    Paystack webhook handler (for future use)
    """
    # TODO: Implement Paystack webhook verification and processing
    return response(
        True,
        "Webhook received (not yet implemented)",
        code=status.HTTP_200_OK
    )


# ==================== RECEIPT ENDPOINT ====================

@api_view(['GET'])
def get_receipt(request, contributor_id):
    """
    Get receipt for a contribution
    """
    try:
        contributor = get_object_or_404(Contributor, id=contributor_id)
        
        if contributor.payment_status != 'paid':
            return response(
                False,
                "Receipt not available. Payment not confirmed yet.",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        collection = contributor.collection
        
        receipt_data = {
            'receipt_id': str(contributor.id),
            'reference': contributor.payment_reference,
            'date': contributor.paid_at.isoformat() if contributor.paid_at else None,
            'contributor': {
                'name': contributor.name,
                'phone': contributor.phone,
                'email': contributor.email
            },
            'collection': {
                'title': collection.title,
                'organizer': collection.organizer_name
            },
            'payment': {
                'amount': float(contributor.amount_paid),
                'method': contributor.payment_method,
                'status': contributor.payment_status
            }
        }
        
        # TODO: Generate actual PDF here
        # For now, return JSON data
        
        return response(
            True,
            "Receipt retrieved successfully",
            data=receipt_data
        )
        
    except Exception as e:
        return response(
            False,
            "Error retrieving receipt",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )