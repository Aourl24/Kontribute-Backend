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
from .email_function import send_organizer_notification, send_dashboard_link
from .paystack_service import PaystackService
from .paystack_utils import (
    generate_payment_reference,
    validate_paystack_response,
    create_payment_metadata,
    parse_paystack_webhook_event,
    kobo_to_naira
)
import json

website_url = "http://127.0.0.1:8000"
frontend_url = "http://localhost:3000"


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


# COLLECTION ENDPOINTS 

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
            status='active',
        )
        
        token = collection.generate_magic_token()
        response_serializer = CollectionSerializers(collection)
        
        # Send email notification to organizer
        try:
            send_dashboard_link(collection, f"{frontend_url}/{collection.slug}/dashboard")
        except Exception as email_error:
            print(f"Email notification failed: {str(email_error)}")

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


# ==================== AUTOMATIC PAYMENT ENDPOINTS (PAYSTACK) ====================

@api_view(['POST'])
def make_automatic_contribution(request, slug):
    """
    Create contributor and initialize Paystack payment - Automatic Payment Version
    
    Expected payload:
    {
        "name": "John Doe",
        "phone": "08012345678",
        "email": "john@email.com"
    }
    """
    try:
        # Get collection
        collection = get_object_or_404(Collection, slug=slug)
        
        # Verify this is an automatic collection
        if collection.type != 'automatic':
            return response(
                False,
                "This collection uses manual payment. Please use the manual payment endpoint.",
                code=status.HTTP_400_BAD_REQUEST
            )
        
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
        
        # Validate required fields
        required_fields = ['name', 'phone', 'email']
        if not collection.amount_per_person:
            required_fields.append('amount')
            
        for field in required_fields:
            if field not in request.data:
                return response(
                    False,
                    f"Missing required field: {field}",
                    code=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate email format
        email = request.data['email']
        if not email or '@' not in email:
            return response(
                False,
                "Valid email address is required for automatic payments",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        amount_to_be_paid = collection.amount_per_person if collection.amount_per_person else request.data["amount"]
        
        # Check for duplicate contribution
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
                # Return existing pending contribution with payment link
                return response(
                    True,
                    "You already have a pending contribution. Please complete payment.",
                    data={
                        'contributor_id': str(existing_contributor.id),
                        'payment_reference': existing_contributor.payment_reference,
                        'amount': float(existing_contributor.amount_owed),
                        'status': 'pending',
                        'payment_url': f"{frontend_url}/{collection.slug}/pay/{existing_contributor.payment_reference}"
                    }
                )
        
        # Generate unique payment reference
        payment_reference = generate_payment_reference('KTR')
        
        # Create contributor record
        contributor = Contributor.objects.create(
            collection=collection,
            name=request.data['name'],
            phone=request.data['phone'],
            email=email,
            amount_owed=amount_to_be_paid,
            amount_paid=0,
            payment_status='pending',
            payment_method='card',  # Will be updated based on actual payment channel
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
        
        # Initialize Paystack transaction
        try:
            paystack = PaystackService()
            
            # Create callback URL
            callback_url = f"{frontend_url}/{collection.slug}/verify/{payment_reference}"
            
            # Create metadata
            metadata = create_payment_metadata(
                contributor_name=contributor.name,
                contributor_phone=contributor.phone,
                collection_id=str(collection.id),
                collection_title=collection.title,
                contributor_id=str(contributor.id)
            )
            
            # Initialize transaction
            paystack_response = paystack.initialize_transaction(
                email=email,
                amount=float(amount_to_be_paid),
                reference=payment_reference,
                callback_url=callback_url,
                metadata=metadata,
                subaccount=collection.paystack_subaccount if collection.paystack_subaccount else None
            )
            
            # Validate response
            is_valid, message, paystack_data = validate_paystack_response(paystack_response)
            
            if not is_valid:
                # Delete contributor and transaction if Paystack init failed
                contributor.delete()
                transaction.delete()
                return response(
                    False,
                    f"Payment initialization failed: {message}",
                    code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Store Paystack reference
            contributor.paystack_reference = paystack_data.get('reference')
            contributor.save()
            
            transaction.paystack_reference = paystack_data.get('reference')
            transaction.save()
            
            # Send email notification to organizer
            try:
                send_organizer_notification(
                    collection, 
                    contributor, 
                    amount_to_be_paid, 
                    payment_reference,
                    f"{frontend_url}/{collection.slug}/dashboard"
                )
            except Exception as email_error:
                print(f"Email notification failed: {str(email_error)}")
            
            # Return payment URL
            return response(
                True,
                "Payment initialized successfully. Proceed to make payment.",
                data={
                    'contributor_id': str(contributor.id),
                    'payment_reference': payment_reference,
                    'amount': float(amount_to_be_paid),
                    'payment_url': paystack_data.get('authorization_url'),
                    'access_code': paystack_data.get('access_code'),
                    'status': 'pending'
                },
                code=status.HTTP_201_CREATED
            )
            
        except Exception as paystack_error:
            # Cleanup on error
            contributor.delete()
            transaction.delete()
            return response(
                False,
                f"Payment service error: {str(paystack_error)}",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR
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


@api_view(['GET'])
def verify_payment(request, reference):
    """
    Verify Paystack payment after redirect
    
    URL: /api/verify-payment/<reference>/
    """
    try:
        # Get contributor by reference
        contributor = get_object_or_404(Contributor, payment_reference=reference)
        collection = contributor.collection
        
        # Check if already verified
        if contributor.payment_status == 'paid':
            return response(
                True,
                "Payment already verified",
                data={
                    'status': 'paid',
                    'contributor_id': str(contributor.id),
                    'amount_paid': float(contributor.amount_paid),
                    'paid_at': contributor.paid_at.isoformat() if contributor.paid_at else None
                }
            )
        
        # Verify with Paystack
        try:
            paystack = PaystackService()
            verification_response = paystack.verify_transaction(reference)
            
            is_valid, message, verification_data = validate_paystack_response(verification_response)
            
            if not is_valid:
                return response(
                    False,
                    f"Payment verification failed: {message}",
                    code=status.HTTP_400_BAD_REQUEST
                )
            
            # Check payment status
            if verification_data.get('status') == 'success':
                # Update contributor
                contributor.payment_status = 'paid'
                contributor.amount_paid = kobo_to_naira(verification_data.get('amount', 0))
                contributor.paid_at = timezone.now()
                contributor.payment_method = verification_data.get('channel', 'card')
                contributor.verified_by = 'paystack'
                contributor.verified_at = timezone.now()
                contributor.save()
                
                # Update transaction
                transaction = Transaction.objects.filter(
                    contributor=contributor,
                    reference=reference
                ).first()
                
                if transaction:
                    transaction.status = 'success'
                    transaction.paystack_reference = verification_data.get('reference')
                    transaction.metadata = verification_data
                    transaction.save()
                
                return response(
                    True,
                    "Payment verified successfully",
                    data={
                        'status': 'paid',
                        'contributor_id': str(contributor.id),
                        'contributor_name': contributor.name,
                        'amount_paid': float(contributor.amount_paid),
                        'paid_at': contributor.paid_at.isoformat(),
                        'payment_method': contributor.payment_method,
                        'collection_title': collection.title
                    }
                )
            else:
                # Payment failed
                contributor.payment_status = 'failed'
                contributor.save()
                
                transaction = Transaction.objects.filter(
                    contributor=contributor,
                    reference=reference
                ).first()
                
                if transaction:
                    transaction.status = 'failed'
                    transaction.metadata = verification_data
                    transaction.save()
                
                return response(
                    False,
                    f"Payment failed: {verification_data.get('gateway_response', 'Unknown error')}",
                    code=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as paystack_error:
            return response(
                False,
                f"Verification error: {str(paystack_error)}",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Contributor.DoesNotExist:
        return response(
            False,
            "Payment reference not found",
            code=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return response(
            False,
            "An error occurred during verification",
            errors=str(e),
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== MANUAL PAYMENT ENDPOINTS (ORIGINAL) ====================

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
        
        # Verify this is a manual collection
        if collection.type != 'manual':
            return response(
                False,
                "This collection uses automatic payment. Please use the automatic payment endpoint.",
                code=status.HTTP_400_BAD_REQUEST
            )
        
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
        
        # Send email notification to organizer
        try:
            send_organizer_notification(collection, contributor, amount_to_be_paid, payment_reference,f"{frontend_url}/{collection.slug}/dashboard")
        except Exception as email_error:
            # Log the error but don't fail the contribution
            print(f"Email notification failed: {str(email_error)}")
        
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
                    'type': collection.type,
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


# ==================== WEBHOOK ENDPOINT (Paystack Integration) ====================

@csrf_exempt
@api_view(['POST'])
def paystack_webhook(request):
    """
    Paystack webhook handler for payment notifications
    This handles real-time payment updates from Paystack
    """
    try:
        # Get raw payload
        payload = request.body
        
        # Get signature from header
        signature = request.headers.get('X-Paystack-Signature', '')
        
        if not signature:
            return response(
                False,
                "No signature found",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify webhook signature
        paystack = PaystackService()
        if not paystack.verify_webhook_signature(payload, signature):
            return response(
                False,
                "Invalid signature",
                code=status.HTTP_401_UNAUTHORIZED
            )
        
        # Parse event data
        event_data = json.loads(payload)
        event = event_data.get('event')
        
        # Parse webhook event
        parsed_event = parse_paystack_webhook_event(event_data)
        
        # Handle charge.success event
        if event == 'charge.success':
            reference = parsed_event['reference']
            
            # Find contributor by reference
            try:
                contributor = Contributor.objects.get(payment_reference=reference)
            except Contributor.DoesNotExist:
                # Log this but return 200 to prevent Paystack retries
                print(f"Webhook: Contributor not found for reference {reference}")
                return Response({'status': 'success'}, status=status.HTTP_200_OK)
            
            # Check if not already paid
            if contributor.payment_status != 'paid':
                # Update contributor
                contributor.payment_status = 'paid'
                contributor.amount_paid = parsed_event['amount']
                contributor.paid_at = timezone.now()
                contributor.payment_method = parsed_event['channel']
                contributor.verified_by = 'paystack_webhook'
                contributor.verified_at = timezone.now()
                contributor.save()
                
                # Update transaction
                transaction = Transaction.objects.filter(
                    contributor=contributor,
                    reference=reference
                ).first()
                
                if transaction:
                    transaction.status = 'success'
                    transaction.paystack_reference = parsed_event['paystack_reference']
                    transaction.metadata = event_data.get('data', {})
                    transaction.save()
                
                print(f"Webhook: Payment confirmed for {contributor.name} - {reference}")
        
        # Handle other events if needed (transfer.success, transfer.failed, etc.)
        # Add more event handlers here as needed
        
        # Always return 200 OK to Paystack
        return Response({'status': 'success'}, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Log error but still return 200 to prevent webhook retries
        print(f"Webhook error: {str(e)}")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_200_OK)


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
                'organizer': collection.organizer_name,
                'type': collection.type
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