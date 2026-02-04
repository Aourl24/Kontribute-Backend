"""
Paystack Utility Functions
Helper functions for Paystack integration
"""

from typing import Dict, List


# Nigerian Bank Codes (Common ones)
NIGERIAN_BANKS = {
    'ACCESS_BANK': '044',
    'CITIBANK': '023',
    'ECOBANK': '050',
    'FIDELITY_BANK': '070',
    'FIRST_BANK': '011',
    'FCMB': '214',
    'GTB': '058',
    'HERITAGE_BANK': '030',
    'KEYSTONE_BANK': '082',
    'POLARIS_BANK': '076',
    'PROVIDUS_BANK': '101',
    'STANBIC_IBTC': '221',
    'STANDARD_CHARTERED': '068',
    'STERLING_BANK': '232',
    'UNION_BANK': '032',
    'UBA': '033',
    'UNITY_BANK': '215',
    'WEMA_BANK': '035',
    'ZENITH_BANK': '057',
}


def get_bank_code(bank_name: str) -> str:
    """
    Get bank code from bank name
    
    Args:
        bank_name: Name of the bank
    
    Returns:
        Bank code or empty string if not found
    """
    bank_name_upper = bank_name.upper().replace(' ', '_')
    
    # Check if exact match
    if bank_name_upper in NIGERIAN_BANKS:
        return NIGERIAN_BANKS[bank_name_upper]
    
    # Check if partial match
    for key, code in NIGERIAN_BANKS.items():
        if bank_name_upper in key or key in bank_name_upper:
            return code
    
    return ''


def format_amount_for_display(amount: float) -> str:
    """
    Format amount for display with Naira symbol
    
    Args:
        amount: Amount to format
    
    Returns:
        Formatted string like "₦10,000.00"
    """
    return f"₦{amount:,.2f}"


def kobo_to_naira(kobo: int) -> float:
    """
    Convert kobo to naira
    
    Args:
        kobo: Amount in kobo
    
    Returns:
        Amount in naira
    """
    return float(kobo) / 100


def naira_to_kobo(naira: float) -> int:
    """
    Convert naira to kobo
    
    Args:
        naira: Amount in naira
    
    Returns:
        Amount in kobo
    """
    return int(float(naira) * 100)


def generate_payment_reference(prefix: str = 'KTR') -> str:
    """
    Generate a unique payment reference
    
    Args:
        prefix: Prefix for the reference
    
    Returns:
        Unique reference string
    """
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def validate_paystack_response(response: Dict) -> tuple:
    """
    Validate Paystack API response
    
    Args:
        response: Response dict from Paystack
    
    Returns:
        Tuple of (is_valid: bool, message: str, data: dict or None)
    """
    if not response:
        return False, "Empty response from Paystack", None
    
    if not response.get('status'):
        message = response.get('message', 'Unknown error from Paystack')
        return False, message, None
    
    data = response.get('data')
    return True, response.get('message', 'Success'), data


def calculate_paystack_fees(amount: float, apply_cap: bool = True) -> Dict[str, float]:
    """
    Calculate Paystack transaction fees
    Paystack charges 1.5% + ₦100 (capped at ₦2,000)
    
    Args:
        amount: Transaction amount
        apply_cap: Whether to apply the ₦2,000 cap
    
    Returns:
        Dict with amount, fees, and net_amount
    """
    # 1.5% of amount
    percentage_fee = amount * 0.015
    
    # Add flat ₦100
    total_fee = percentage_fee + 100
    
    # Apply cap if needed
    if apply_cap and total_fee > 2000:
        total_fee = 2000
    
    net_amount = amount - total_fee
    
    return {
        'amount': round(amount, 2),
        'fees': round(total_fee, 2),
        'net_amount': round(net_amount, 2)
    }


def get_paystack_channels_for_collection_type(collection_type: str) -> List[str]:
    """
    Get appropriate payment channels based on collection type
    
    Args:
        collection_type: Type of collection ('manual' or 'automatic')
    
    Returns:
        List of channel names
    """
    if collection_type == 'automatic':
        # For automatic, enable all channels
        return ['card', 'bank', 'ussd', 'bank_transfer']
    else:
        # For manual, shouldn't reach here but return empty
        return []


def create_payment_metadata(
    contributor_name: str,
    contributor_phone: str,
    collection_id: str,
    collection_title: str,
    contributor_id: str = None
) -> Dict:
    """
    Create metadata object for Paystack transaction
    
    Args:
        contributor_name: Name of contributor
        contributor_phone: Phone number
        collection_id: Collection UUID
        collection_title: Collection title
        contributor_id: Contributor UUID (if exists)
    
    Returns:
        Metadata dictionary
    """
    metadata = {
        'contributor_name': contributor_name,
        'contributor_phone': contributor_phone,
        'collection_id': str(collection_id),
        'collection_title': collection_title,
        'source': 'kontribute_app'
    }
    
    if contributor_id:
        metadata['contributor_id'] = str(contributor_id)
    
    return metadata


def parse_paystack_webhook_event(event_data: Dict) -> Dict:
    """
    Parse Paystack webhook event data
    
    Args:
        event_data: Raw webhook event data
    
    Returns:
        Parsed event dictionary with standardized fields
    """
    event = event_data.get('event', '')
    data = event_data.get('data', {})
    
    parsed = {
        'event_type': event,
        'reference': data.get('reference', ''),
        'amount': kobo_to_naira(data.get('amount', 0)),
        'status': data.get('status', ''),
        'paid_at': data.get('paid_at'),
        'customer_email': data.get('customer', {}).get('email', ''),
        'metadata': data.get('metadata', {}),
        'authorization': data.get('authorization', {}),
        'channel': data.get('channel', ''),
        'currency': data.get('currency', 'NGN'),
        'paystack_reference': data.get('reference', ''),
        'gateway_response': data.get('gateway_response', ''),
    }
    
    return parsed


def is_test_transaction(reference: str) -> bool:
    """
    Check if transaction is a test transaction
    
    Args:
        reference: Transaction reference
    
    Returns:
        Boolean indicating if it's a test transaction
    """
    test_prefixes = ['TEST', 'TST', 'DEMO']
    return any(reference.upper().startswith(prefix) for prefix in test_prefixes)


def format_phone_number(phone: str) -> str:
    """
    Format phone number to standard Nigerian format
    
    Args:
        phone: Phone number
    
    Returns:
        Formatted phone number
    """
    # Remove all non-digit characters
    phone = ''.join(filter(str.isdigit, phone))
    
    # Add +234 if not present
    if phone.startswith('0'):
        phone = '234' + phone[1:]
    elif not phone.startswith('234'):
        phone = '234' + phone
    
    return '+' + phone


def get_payment_method_display_name(channel: str) -> str:
    """
    Get display name for payment channel
    
    Args:
        channel: Paystack channel name
    
    Returns:
        User-friendly display name
    """
    channel_names = {
        'card': 'Debit/Credit Card',
        'bank': 'Bank Account',
        'ussd': 'USSD',
        'bank_transfer': 'Bank Transfer',
        'qr': 'QR Code',
        'mobile_money': 'Mobile Money',
    }
    
    return channel_names.get(channel, channel.title())
