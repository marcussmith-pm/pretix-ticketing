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

import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from pretix.base.models import Order, OrderPayment

logger = logging.getLogger('pretix.plugins.poli')


class PoliReturnView(View):
    """
    Handle the return from POLi after payment attempt.

    POLi redirects the user back here with a token parameter.
    We then query the POLi API to get the transaction status.
    """

    def get(self, request, *args, **kwargs):
        """
        Handle GET request when user returns from POLi.
        """
        token = request.GET.get('token')
        order_code = kwargs.get('order')
        payment_id = kwargs.get('payment')
        hash_value = kwargs.get('hash')

        if not token:
            messages.error(request, _('No payment token received from POLi.'))
            return redirect(reverse('presale:event.orders', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
                'code': order_code
            }) + '?' + urlencode({'hash': hash_value, 'error': 'poli_no_token'}))

        try:
            order = Order.objects.get(code=order_code, event=request.event)
            if order.secret != hash_value:
                raise PermissionDenied()

            payment = order.payments.get(pk=payment_id)

            # Get transaction status from POLi
            provider = payment.payment_provider
            transaction_data = provider.get_transaction_status(token)

            if not transaction_data:
                messages.error(
                    request,
                    _('We were unable to verify your payment with POLi. Please contact support.')
                )
                return redirect(reverse('presale:event.order', kwargs={
                    'event': request.event.slug,
                    'organizer': request.organizer.slug,
                    'code': order_code,
                    'hash': hash_value
                }) + '?opened')

            # Process the transaction result
            provider.process_transaction_result(payment, transaction_data)

            # Redirect to order confirmation page
            if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                messages.success(request, _('Your payment has been completed successfully!'))
            elif payment.state == OrderPayment.PAYMENT_STATE_PENDING:
                messages.warning(
                    request,
                    _('Your payment is being processed. We will notify you when it is complete.')
                )
            else:
                messages.error(
                    request,
                    _('Your payment could not be processed. Please try again or choose a different payment method.')
                )

            return redirect(reverse('presale:event.order', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
                'code': order_code,
                'hash': hash_value
            }) + '?opened')

        except Order.DoesNotExist:
            messages.error(request, _('Order not found.'))
            return redirect(reverse('presale:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug
            }))
        except OrderPayment.DoesNotExist:
            messages.error(request, _('Payment not found.'))
            return redirect(reverse('presale:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug
            }))
        except Exception as e:
            logger.exception(f'Error processing POLi return: {str(e)}')
            messages.error(request, _('An error occurred while processing your payment.'))
            return redirect(reverse('presale:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug
            }))


class PoliCancelView(View):
    """
    Handle when user cancels payment on POLi's side.
    """

    def get(self, request, *args, **kwargs):
        """
        Handle GET request when user cancels POLi payment.
        """
        order_code = kwargs.get('order')
        payment_id = kwargs.get('payment')
        hash_value = kwargs.get('hash')

        try:
            order = Order.objects.get(code=order_code, event=request.event)
            if order.secret != hash_value:
                raise PermissionDenied()

            payment = order.payments.get(pk=payment_id)

            # Mark payment as canceled/failed
            if payment.state == OrderPayment.PAYMENT_STATE_CREATED:
                payment.cancel()

            messages.info(
                request,
                _('You cancelled the POLi payment. You can try again or choose a different '
                    'payment method.')
            )

            return redirect(reverse('presale:event.order', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
                'code': order_code,
                'hash': hash_value
            }) + '?opened')

        except Order.DoesNotExist:
            messages.error(request, _('Order not found.'))
            return redirect(reverse('presale:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug
            }))
        except Exception as e:
            logger.exception(f'Error processing POLi cancel: {str(e)}')
            messages.error(request, _('An error occurred.'))
            return redirect(reverse('presale:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug
            }))


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(xframe_options_exempt, name='dispatch')
class PoliWebhookView(View):
    """
    Handle POLi Nudge (webhook) notifications.

    POLi sends a POST request with the Token when a transaction reaches a terminal state.
    """

    def post(self, request, *args, **kwargs):
        """
        Handle POST webhook from POLi.
        """
        token = request.POST.get('token')

        if not token:
            logger.warning('POLi webhook received without token')
            return HttpResponseBadRequest('Token is required')

        # Get the event from the request - this is a multidomain setup
        # We need to find the order by querying the transaction data
        try:
            # For now, log the webhook and return success
            # The return view will handle the actual status update
            logger.info(f'POLi webhook received with token: {token}')

            # For production use, we should:
            # 1. Query the POLi API to get transaction details
            # 2. Extract MerchantData which contains order_code and payment_id
            # 3. Find the corresponding order and payment
            # 4. Update the payment status
            return HttpResponse('OK')

        except Exception as e:
            logger.exception(f'Error processing POLi webhook: {str(e)}')
            return HttpResponse('OK', status=202)  # Accept but don't process on error
