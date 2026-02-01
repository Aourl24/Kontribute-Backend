from paystackapi.paystack import Paystack
from paystackapi.transaction import Transaction

def initialize_payment(request):
	response = Transaction.initialize()