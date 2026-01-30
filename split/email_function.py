from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
import uuid

def send_organizer_notification(collection, contributor, amount, payment_reference):
    """
    Send email notification to collection organizer about new contribution
    """
    organizer_email = collection.organizer_email  # Adjust based on your model structure
    
    if not organizer_email:
        return  # Skip if organizer has no email
    
    subject = f"New Contribution Pending - {collection.title}"
    
    # Plain text message
    message = f"""
Hello,

A new contribution has been made to your collection "{collection.title}".

Contributor Details:
- Name: {contributor.name}
- Phone: {contributor.phone}
- Email: {contributor.email or 'Not provided'}
- Amount: ₦{amount}
- Payment Reference: {payment_reference}
- Status: Pending Payment

The contributor has been provided with your bank details to complete the transfer.
Please verify the payment once received.

Collection Summary:
- Total Contributors: {collection.contributors.count()}
- Target Amount: ₦{collection.total_amount}
- Amount Collected: ₦{collection.total_collected}

Best regards,
Your Collection Management System
    """
    
    # HTML message (optional but recommended)
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #4CAF50;">New Contribution Pending</h2>
            
            <p>Hello,</p>
            
            <p>A new contribution has been made to your collection <strong>"{collection.title}"</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Contributor Details:</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>Name:</strong> {contributor.name}</li>
                    <li><strong>Phone:</strong> {contributor.phone}</li>
                    <li><strong>Email:</strong> {contributor.email or 'Not provided'}</li>
                    <li><strong>Amount:</strong> ₦{amount}</li>
                    <li><strong>Payment Reference:</strong> {payment_reference}</li>
                    <li><strong>Status:</strong> <span style="color: orange;">Pending Payment</span></li>
                </ul>
            </div>
            
            <p>The contributor has been provided with your bank details to complete the transfer.<br>
            Please verify the payment once received.</p>
            
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Collection Summary:</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>Total Contributors:</strong> {collection.contributors.count()}</li>
                    <li><strong>Target Amount:</strong> ₦{collection.total_amount}</li>
                    <li><strong>Amount Collected:</strong> ₦{collection.total_collected}</li>
                </ul>
            </div>
            
            <p style="color: #666; font-size: 0.9em;">
                Best regards,<br>
                Your Collection Management System
            </p>
        </body>
    </html>
    """
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[organizer_email],
        html_message=html_message,
        fail_silently=False,
    )


def send_dashbord_link(collection,link):
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #4CAF50;">Your Collection is Created Succesfully </h2>
            
            <p>Hello,</p>
            
            <p> The dashborad Link <a href="{link}" >"{uuid.uuid4().hex[:25]}"</a>.</p>
    </body>
    </html>
    """ 

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[organizer_email],
        html_message=html_message,
        fail_silently=False,
    )       