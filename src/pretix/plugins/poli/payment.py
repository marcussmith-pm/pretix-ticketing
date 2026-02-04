#
# This file is part of pretix.
#
# Copyright (C) 2025 pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.

import json
import logging
import uuid
from collections import OrderedDict
from decimal import Decimal

import requests
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.template.loader import get_template
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretix.base.forms import SecretKeySettingsField
from pretix.base.models import Event, Order, OrderPayment
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger('pretix.plugins.poli')

SUPPORTED_CURRENCIES = ['NZD', 'AUD']


class Poli(BasePaymentProvider):
    """
    POLi payment provider for pretix.

    POLi is a real-time online payment service for shoppers in Australia and New Zealand.
    It allows customers to pay directly from their bank accounts without needing a credit card.
    """

    identifier = 'poli'
    verbose_name = _('POLi Pay')
    payment_form_fields = OrderedDict([])

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'poli', event)

    @property
    def test_mode_message(self):
        if self.settings.get('endpoint') == 'uat':
            return _('POLi test mode is enabled. No real money will be transferred.')
        return None

    def get_base_url(self):
        """
        Get the appropriate POLi API base URL based on the endpoint setting.
        """
        endpoint = self.settings.get('endpoint', 'production')
        if endpoint == 'uat':
            return 'https://poliapi.uat3.paywithpoli.com'
        else:
            return 'https://poliapi.apac.paywithpoli.com'

    @property
    def settings_form_fields(self):
        """
        Define the settings form fields for configuring POLi in the admin panel.
        """
        fields = OrderedDict([
            ('authentication_code',
             SecretKeySettingsField(
                 label=_('Authentication Code'),
                 help_text=_('Your POLi authentication code. This can be found in your POLi merchant account settings.'),
                 required=True,
             )),
            ('merchant_code',
             forms.CharField(
                 label=_('Merchant Code'),
                 help_text=_('Your POLi merchant code provided by POLi.'),
                 required=True,
                 max_length=50,
             )),
            ('endpoint',
             forms.ChoiceField(
                 label=_('API Endpoint'),
                 initial='production',
                 choices=[
                     ('production', _('Production (Live)')),
                     ('uat', _('UAT (Test Environment)')),
                 ],
                 help_text=_('Use the UAT environment for testing before going live.'),
             )),
            ('timeout',
             forms.IntegerField(
                 label=_('Transaction Timeout'),
                 initial=900,
                 min_value=60,
                 max_value=3600,
                 help_text=_('Time in seconds before the transaction expires. Default is 900 (15 minutes).'),
                 required=False,
             )),
        ])

        d = OrderedDict(
            list(super().settings_form_fields.items()) + list(fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d

    def settings_form_clean(self, cleaned_data):
        """
        Validate the settings form data.
        """
        authentication_code = cleaned_data.get('payment_poli_authentication_code')
        merchant_code = cleaned_data.get('payment_poli_merchant_code')

        if not authentication_code:
            raise ValidationError({
                'payment_poli_authentication_code': _('Authentication code is required.')
            })

        if not merchant_code:
            raise ValidationError({
                'payment_poli_merchant_code': _('Merchant code is required.')
            })

        return cleaned_data

    def is_allowed(self, request: HttpRequest, total: Decimal = None) -> bool:
        """
        Check if POLi is allowed for this request/currency.
        """
        return super().is_allowed(request, total) and self.event.currency in SUPPORTED_CURRENCIES

    @property
    def abort_pending_allowed(self):
        """
        POLi payments that are pending can be aborted.
        """
        return True

    def payment_is_valid_session(self, request):
        """
        Check if the payment session is valid.
        """
        return request.session.get('payment_poli_token', '') != ''

    def payment_form_render(self, request) -> str:
        """
        Render the payment form shown to users during checkout.
        """
        template = get_template('pretixplugins/poli/checkout_payment_form.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        """
        Initiate a POLi transaction and return the redirect URL.

        This is called during checkout to start the payment flow.
        The OrderPayment doesn't exist yet, so we use the session.
        """
        logger.info(f'[POLi DEBUG] checkout_prepare called with total: {total}, currency: {self.event.currency}')

        # Generate a temporary reference for the transaction
        # We'll update this with the actual order code when the payment is created
        temp_ref = f"TEMP-{uuid.uuid4().hex[:12].upper()}"
        logger.info(f'[POLi DEBUG] Generated temp_ref: {temp_ref}')

        # Extract the actual amount from the total dictionary
        if isinstance(total, dict):
            amount = str(total.get('total', Decimal('0.00')))
            logger.info(f'[POLi DEBUG] Extracted amount from dict: {amount}')
        else:
            amount = str(total)
            logger.info(f'[POLi DEBUG] Amount (direct): {amount}')

        currency_code = self.event.currency
        merchant_homepage_url = build_absolute_uri(self.event, 'presale:event.index')
        # We'll use the return URL that works without order/payment context
        # The view will handle finding the correct order
        success_url = build_absolute_uri(self.event, 'presale:event.index')
        failure_url = build_absolute_uri(self.event, 'presale:event.index')
        cancellation_url = build_absolute_uri(self.event, 'presale:event.index')
        notification_url = build_absolute_uri(self.event, 'plugins:poli:webhook')

        timeout = self.settings.get('timeout', 900)
        logger.info(f'[POLi DEBUG] Timeout: {timeout}, Endpoint: {self.settings.get("endpoint", "production")}')

        payload = {
            'Amount': amount,
            'CurrencyCode': currency_code,
            'MerchantReference': temp_ref,
            'MerchantHomepageURL': merchant_homepage_url,
            'SuccessURL': success_url,
            'FailureURL': failure_url,
            'CancellationURL': cancellation_url,
            'NotificationURL': notification_url,
            'Timeout': timeout,
            'MerchantData': json.dumps({
                'temp_ref': temp_ref,
            }),
        }

        authentication_code = self.settings.get('authentication_code')
        merchant_code = self.settings.get('merchant_code')

        logger.info(f'[POLi DEBUG] Merchant code: {merchant_code}, Auth code set: {bool(authentication_code)}')

        # Create Basic Auth header
        auth_string = f"{merchant_code}:{authentication_code}"
        auth_header = f"Basic {__import__('base64').b64encode(auth_string.encode()).decode()}"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': auth_header,
        }

        base_url = self.get_base_url()
        api_url = f"{base_url}/api/v2/Transaction/Initiate"

        logger.info(f'[POLi DEBUG] Calling POLi API: {api_url}')
        logger.info(f'[POLi DEBUG] Payload: {json.dumps(payload, indent=2)}')

        try:
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            logger.info(f'[POLi DEBUG] Response status: {response.status_code}')
            logger.info(f'[POLi DEBUG] Response body: {response.text[:500]}')

            response.raise_for_status()
            data = response.json()

            if data.get('Success'):
                # Store transaction details for later use
                request.session['payment_poli_token'] = data.get('TransactionRefNo')
                request.session['payment_poli_navigate_url'] = data.get('NavigateURL')
                request.session['payment_poli_temp_ref'] = temp_ref
                logger.info(f'[POLi DEBUG] Transaction initiated successfully, NavigateURL: {data.get("NavigateURL")}')
                return data.get('NavigateURL')
            else:
                error_code = data.get('ErrorCode', 'Unknown')
                error_message = data.get('ErrorMessage', 'Unknown error')
                logger.error(f'[POLi DEBUG] InitiateTransaction failed: {error_code} - {error_message}')
                logger.error(f'[POLi DEBUG] Full response: {data}')
                return None

        except requests.RequestException as e:
            logger.error(f'[POLi DEBUG] API request failed: {str(e)}')
            logger.exception(f'[POLi DEBUG] Full exception traceback:')
            return None

    def checkout_confirm_render(self, request):
        """
        Render the confirmation page before redirecting to POLi.
        """
        template = get_template('pretixplugins/poli/checkout_payment_confirm.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def get_transaction_status(self, token):
        """
        Query POLi for the status of a transaction using the GetTransaction API.

        Returns the transaction data if successful, or None if failed.
        """
        authentication_code = self.settings.get('authentication_code')
        merchant_code = self.settings.get('merchant_code')

        # Create Basic Auth header
        auth_string = f"{merchant_code}:{authentication_code}"
        auth_header = f"Basic {__import__('base64').b64encode(auth_string.encode()).decode()}"

        headers = {
            'Authorization': auth_header,
        }

        base_url = self.get_base_url()
        api_url = f"{base_url}/api/v2/Transaction/GetTransaction"

        try:
            response = requests.get(
                api_url,
                params={'token': token},
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.exception(f'POLi GetTransaction failed: {str(e)}')
            return None

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        """
        Execute the payment by verifying it with POLi.

        This is called when the user returns from POLi or when the payment
        needs to be confirmed. We query POLi for the transaction status
        and update the payment accordingly.
        """
        token = request.session.get('payment_poli_token')
        if not token:
            raise PaymentException(
                _('No POLi transaction token found. Please try again.')
            )

        # Query POLi for transaction status
        transaction_data = self.get_transaction_status(token)

        if not transaction_data:
            raise PaymentException(
                _('We were unable to verify your payment with POLi. Please contact support.')
            )

        # Store the transaction data
        payment.info = json.dumps(transaction_data)
        payment.save(update_fields=['info'])

        # Process the transaction result
        success = self.process_transaction_result(payment, transaction_data)

        if not success:
            transaction_status = transaction_data.get('TransactionStatusCode', 'Unknown')
            if transaction_status == 'Failed':
                raise PaymentException(
                    _('Your payment failed. Please try again or choose a different payment method.')
                )
            elif transaction_status == 'Timeout':
                raise PaymentException(
                    _('Your payment timed out. Please try again.')
                )
            else:
                raise PaymentException(
                    _('We were unable to process your payment. Please try again or contact support.')
                )

        return None

    def payment_prepare(self, request, payment: OrderPayment):
        """
        Initiate a new POLi payment for an existing order.

        This is called when a user wants to pay for an existing order
        (e.g., from the order details page).
        """
        # For existing orders, we can use the actual order code
        amount = str(payment.amount)
        currency_code = self.event.currency
        merchant_reference = payment.order.code
        merchant_homepage_url = build_absolute_uri(self.event, 'presale:event.index')
        success_url = build_absolute_uri(
            self.event,
            'plugins:poli:return',
            kwargs={
                'order': payment.order.code,
                'payment': payment.pk,
                'hash': payment.order.secret
            }
        )
        failure_url = success_url
        cancellation_url = build_absolute_uri(
            self.event,
            'plugins:poli:cancel',
            kwargs={
                'order': payment.order.code,
                'payment': payment.pk,
                'hash': payment.order.secret
            }
        )
        notification_url = build_absolute_uri(self.event, 'plugins:poli:webhook')

        timeout = self.settings.get('timeout', 900)

        payload = {
            'Amount': amount,
            'CurrencyCode': currency_code,
            'MerchantReference': merchant_reference,
            'MerchantHomepageURL': merchant_homepage_url,
            'SuccessURL': success_url,
            'FailureURL': failure_url,
            'CancellationURL': cancellation_url,
            'NotificationURL': notification_url,
            'Timeout': timeout,
            'MerchantData': json.dumps({
                'order_code': payment.order.code,
                'payment_id': payment.pk,
            }),
        }

        authentication_code = self.settings.get('authentication_code')
        merchant_code = self.settings.get('merchant_code')

        # Create Basic Auth header
        auth_string = f"{merchant_code}:{authentication_code}"
        auth_header = f"Basic {__import__('base64').b64encode(auth_string.encode()).decode()}"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': auth_header,
        }

        base_url = self.get_base_url()
        api_url = f"{base_url}/api/v2/Transaction/Initiate"

        try:
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if data.get('Success'):
                # Store transaction details for later verification
                request.session['payment_poli_token'] = data.get('TransactionRefNo')
                request.session['payment_poli_payment_id'] = payment.pk

                # Store payment info with the transaction reference
                payment.info = json.dumps({
                    'transaction_ref_no': data.get('TransactionRefNo'),
                    'navigate_url': data.get('NavigateURL'),
                })
                payment.save(update_fields=['info'])

                return data.get('NavigateURL')
            else:
                error_code = data.get('ErrorCode', 'Unknown')
                error_message = data.get('ErrorMessage', 'Unknown error')
                logger.error(f'POLi InitiateTransaction failed: {error_code} - {error_message}')
                payment.order.log_action(
                    'pretix.event.order.payment.failed',
                    {
                        'local_id': payment.local_id,
                        'provider': self.identifier,
                        'error': f'{error_code}: {error_message}'
                    }
                )
                raise PaymentException(
                    _('We were unable to initiate the POLi transaction. Please try again or contact support.')
                )

        except requests.RequestException as e:
            logger.exception(f'POLi API request failed: {str(e)}')
            payment.order.log_action(
                'pretix.event.order.payment.failed',
                {
                    'local_id': payment.local_id,
                    'provider': self.identifier,
                    'error': str(e)
                }
            )
            raise PaymentException(
                _('We were unable to reach POLi. Please try again or contact support.')
            )

    def process_transaction_result(self, payment: OrderPayment, transaction_data):
        """
        Process the result of a POLi transaction.

        Updates the payment status based on the transaction status from POLi.
        """
        transaction_status = transaction_data.get('TransactionStatusCode')
        transaction_ref_no = transaction_data.get('TransactionRefNo')

        if not transaction_status:
            logger.error(f'POLi transaction missing status: {transaction_data}')
            return False

        # Update payment info with full transaction details
        payment.info = json.dumps(transaction_data)
        payment.save(update_fields=['info'])

        if transaction_status == 'Completed':
            # Transaction successful
            if payment.state != OrderPayment.PAYMENT_STATE_CONFIRMED:
                try:
                    payment.confirm()
                    logger.info(f'POLi payment confirmed: {payment.pk}, Transaction: {transaction_ref_no}')
                    return True
                except Exception as e:
                    logger.exception(f'Failed to confirm POLi payment: {str(e)}')
                    return False
            else:
                # Already confirmed
                return True

        elif transaction_status == 'Failed':
            # Transaction failed
            if payment.state not in (OrderPayment.PAYMENT_STATE_FAILED, OrderPayment.PAYMENT_STATE_CANCELED):
                payment.fail(info=transaction_data)
                logger.warning(f'POLi payment failed: {payment.pk}, Transaction: {transaction_ref_no}')
            return False

        elif transaction_status == 'Timeout':
            # Transaction timed out
            if payment.state not in (OrderPayment.PAYMENT_STATE_FAILED, OrderPayment.PAYMENT_STATE_CANCELED):
                payment.fail(info=transaction_data)
                logger.warning(f'POLi payment timed out: {payment.pk}, Transaction: {transaction_ref_no}')
            return False

        elif transaction_status == 'ReceiptNotReceived':
            # POLi couldn't confirm the final status from the bank
            # Keep as pending and manually reconcile
            payment.state = OrderPayment.PAYMENT_STATE_PENDING
            payment.save(update_fields=['state'])
            logger.warning(f'POLi payment receipt not received: {payment.pk}, Transaction: {transaction_ref_no}')
            return False

        else:
            # Unknown status
            logger.error(f'POLi unknown transaction status: {transaction_status} for payment {payment.pk}')
            return False

    def payment_pending_render(self, request, payment):
        """
        Render the pending payment page.
        """
        template = get_template('pretixplugins/poli/pending.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'order': payment.order,
            'payment': payment,
            'payment_info': payment.info_data or {},
        }
        return template.render(ctx)

    def payment_control_render(self, request, payment):
        """
        Render the payment info in the admin control panel.
        """
        template = get_template('pretixplugins/poli/control.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment.info_data or {},
            'order': payment.order,
            'payment': payment,
        }
        return template.render(ctx)

    def payment_control_render_short(self, payment):
        """
        Render a short representation of the payment for the admin UI.
        """
        if payment.info_data:
            ref_no = payment.info_data.get('TransactionRefNo')
            status = payment.info_data.get('TransactionStatus', 'Unknown')
            if ref_no:
                return f'POLi {ref_no} ({status})'
        return f'POLi ({payment.get_state_display()})'

    def matching_id(self, payment):
        """
        Get a unique identifier for this payment for reconciliation.
        """
        if payment.info_data:
            return payment.info_data.get('TransactionRefNo') or payment.info_data.get('TransactionID')
        return None

    def shred_payment_info(self, obj):
        """
        Remove sensitive payment information (GDPR compliance).
        """
        if not obj.info:
            return

        try:
            data = json.loads(obj.info)
            # Keep non-sensitive fields only
            shredded_data = {
                'TransactionRefNo': data.get('TransactionRefNo'),
                'TransactionID': data.get('TransactionID'),
                'TransactionStatusCode': data.get('TransactionStatusCode'),
                'TransactionStatus': data.get('TransactionStatus'),
                'PaymentAmount': data.get('PaymentAmount'),
                'CurrencyCode': data.get('CurrencyCode'),
                'EstablishedDateTime': data.get('EstablishedDateTime'),
                'EndDateTime': data.get('EndDateTime'),
                '_shredded': True
            }
            obj.info = json.dumps(shredded_data)
            obj.save(update_fields=['info'])
        except (json.JSONDecodeError, TypeError):
            logger.warning(f'Failed to shred payment info for payment {obj.pk}')

    def api_payment_details(self, payment):
        """
        Return payment details for the pretix API.
        """
        return {
            'transaction_ref_no': payment.info_data.get('TransactionRefNo') if payment.info_data else None,
            'transaction_id': payment.info_data.get('TransactionID') if payment.info_data else None,
            'transaction_status': payment.info_data.get('TransactionStatus') if payment.info_data else None,
            'bank_receipt': payment.info_data.get('BankReceipt') if payment.info_data else None,
            'financial_institution': payment.info_data.get('FinancialInstitutionName') if payment.info_data else None,
        }
