"""
Paystack Service Class
Handles all Paystack API interactions for the Kontribute app
"""

import requests
from django.conf import settings
from typing import Dict, Optional
import hashlib
import hmac


class PaystackService:
    """
    Service class for Paystack payment integration
    """
    
    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        self.public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
        self.base_url = 'https://api.paystack.co'
        
        if not self.secret_key:
            raise ValueError("PAYSTACK_SECRET_KEY not found in settings")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for Paystack API"""
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def initialize_transaction(
        self, 
        email: str, 
        amount: float,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict] = None,
        channels: Optional[list] = None,
        subaccount: Optional[str] = None
    ) -> Dict:
        """
        Initialize a Paystack transaction
        
        Args:
            email: Customer's email
            amount: Amount in Naira (will be converted to kobo)
            reference: Unique transaction reference
            callback_url: URL to redirect after payment
            metadata: Additional transaction metadata
            channels: Payment channels to enable ['card', 'bank', 'ussd', 'qr', 'mobile_money', 'bank_transfer']
            subaccount: Paystack subaccount code (for split payments)
        
        Returns:
            Dict containing response from Paystack
        """
        url = f'{self.base_url}/transaction/initialize'
        
        # Convert amount to kobo (Paystack uses kobo)
        amount_in_kobo = int(float(amount) * 100)
        
        payload = {
            'email': email,
            'amount': amount_in_kobo,
            'reference': reference,
            'callback_url': callback_url,
        }
        
        if metadata:
            payload['metadata'] = metadata
        
        if channels:
            payload['channels'] = channels
        else:
            # Default channels for automatic payment
            payload['channels'] = ['card', 'bank', 'ussd', 'bank_transfer']
        
        if subaccount:
            payload['subaccount'] = subaccount
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Paystack API Error: {str(e)}'
            }
    
    def verify_transaction(self, reference: str) -> Dict:
        """
        Verify a transaction using its reference
        
        Args:
            reference: Transaction reference to verify
        
        Returns:
            Dict containing verification response
        """
        url = f'{self.base_url}/transaction/verify/{reference}'
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Verification Error: {str(e)}'
            }
    
    def create_subaccount(
        self,
        business_name: str,
        bank_code: str,
        account_number: str,
        percentage_charge: float = 0
    ) -> Dict:
        """
        Create a Paystack subaccount for split payments
        
        Args:
            business_name: Name of the business/organizer
            bank_code: Bank code (e.g., '058' for GTBank)
            account_number: Account number
            percentage_charge: Percentage of transaction to go to subaccount (0-100)
        
        Returns:
            Dict containing subaccount details
        """
        url = f'{self.base_url}/subaccount'
        
        payload = {
            'business_name': business_name,
            'settlement_bank': bank_code,
            'account_number': account_number,
            'percentage_charge': percentage_charge
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Subaccount Creation Error: {str(e)}'
            }
    
    def list_banks(self) -> Dict:
        """
        Get list of Nigerian banks supported by Paystack
        
        Returns:
            Dict containing list of banks
        """
        url = f'{self.base_url}/bank'
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Bank List Error: {str(e)}'
            }
    
    def resolve_account_number(self, account_number: str, bank_code: str) -> Dict:
        """
        Resolve/verify account number and get account name
        
        Args:
            account_number: Account number to verify
            bank_code: Bank code
        
        Returns:
            Dict containing account details
        """
        url = f'{self.base_url}/bank/resolve'
        params = {
            'account_number': account_number,
            'bank_code': bank_code
        }
        
        try:
            response = requests.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Account Resolution Error: {str(e)}'
            }
    
    def initiate_transfer(
        self,
        amount: float,
        recipient_code: str,
        reason: str,
        reference: str
    ) -> Dict:
        """
        Initiate a transfer to a recipient
        
        Args:
            amount: Amount to transfer in Naira
            recipient_code: Paystack recipient code
            reason: Transfer reason/description
            reference: Unique transfer reference
        
        Returns:
            Dict containing transfer response
        """
        url = f'{self.base_url}/transfer'
        
        # Convert to kobo
        amount_in_kobo = int(float(amount) * 100)
        
        payload = {
            'source': 'balance',
            'amount': amount_in_kobo,
            'recipient': recipient_code,
            'reason': reason,
            'reference': reference
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Transfer Error: {str(e)}'
            }
    
    def create_transfer_recipient(
        self,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str = 'NGN'
    ) -> Dict:
        """
        Create a transfer recipient
        
        Args:
            name: Recipient's name
            account_number: Recipient's account number
            bank_code: Bank code
            currency: Currency (default: NGN)
        
        Returns:
            Dict containing recipient details including recipient_code
        """
        url = f'{self.base_url}/transferrecipient'
        
        payload = {
            'type': 'nuban',
            'name': name,
            'account_number': account_number,
            'bank_code': bank_code,
            'currency': currency
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Recipient Creation Error: {str(e)}'
            }
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Paystack webhook signature
        
        Args:
            payload: Raw request body as bytes
            signature: X-Paystack-Signature header value
        
        Returns:
            Boolean indicating if signature is valid
        """
        hash_obj = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        )
        computed_signature = hash_obj.hexdigest()
        return hmac.compare_digest(computed_signature, signature)
    
    def get_transaction(self, transaction_id: int) -> Dict:
        """
        Get transaction details by ID
        
        Args:
            transaction_id: Paystack transaction ID
        
        Returns:
            Dict containing transaction details
        """
        url = f'{self.base_url}/transaction/{transaction_id}'
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Transaction Fetch Error: {str(e)}'
            }
    
    def charge_authorization(
        self,
        email: str,
        amount: float,
        authorization_code: str,
        reference: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Charge a saved authorization (for recurring payments)
        
        Args:
            email: Customer email
            amount: Amount in Naira
            authorization_code: Paystack authorization code
            reference: Unique reference
            metadata: Additional metadata
        
        Returns:
            Dict containing charge response
        """
        url = f'{self.base_url}/transaction/charge_authorization'
        
        amount_in_kobo = int(float(amount) * 100)
        
        payload = {
            'email': email,
            'amount': amount_in_kobo,
            'authorization_code': authorization_code,
            'reference': reference
        }
        
        if metadata:
            payload['metadata'] = metadata
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'status': False,
                'message': f'Charge Error: {str(e)}'
            }
