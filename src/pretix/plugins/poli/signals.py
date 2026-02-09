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

from datetime import timedelta
from django.dispatch import receiver
from django.utils.timezone import now
from pretix.base.signals import register_payment_providers, email_filter, order_placed

logger = logging.getLogger(__name__)


@receiver(register_payment_providers, dispatch_uid="payment_poli")
def register_payment_provider(sender, **kwargs):
    """
    Register the POLi payment provider with pretix.
    """
    from pretix.plugins.poli.payment import Poli
    return Poli


@receiver(email_filter, dispatch_uid="payment_poli_email_filter")
def filter_order_placed_email(sender, message, order, **kwargs):
    """
    Suppress the immediate 'order placed' email for POLi payments.

    The email will be sent later (after 2 hours) if the order remains unpaid.
    If payment is completed within 2 hours, the email is never sent.
    """
    if not order:
        return message

    # Check if this is an order with POLi payment
    if order.payments.filter(provider='poli').exists():
        # Check the email subject to determine if this is the 'order placed' email
        # The 'order paid' email should still go through
        subject = message.subject.lower() if hasattr(message, 'subject') else ''

        # The 'order placed' email subject is "Your order: {code}"
        # The 'order paid' email subject is "Payment received for your order: {code}"
        # We only suppress the 'order placed' email to avoid confusing UX during payment flow
        if 'your order:' in subject and 'payment received' not in subject:
            # Suppress the immediate email - it will be sent later if needed
            return None

    return message


@receiver(order_placed, dispatch_uid="payment_poli_schedule_reminder")
def schedule_payment_reminder(sender, order, **kwargs):
    """
    Schedule a reminder email to be sent 2 hours after order placement.

    The task will check if the order is still unpaid and send a reminder
    if payment has not been completed.
    """
    # Check if this order uses POLi payment
    if not order.payments.filter(provider='poli').exists():
        return

    # Schedule the reminder task to run in 2 hours
    from pretix.plugins.poli.tasks import send_pending_payment_reminder

    try:
        eta = now() + timedelta(hours=2)
        send_pending_payment_reminder.apply_async(
            args=[order.code, order.event.pk],
            eta=eta,
        )
        logger.info(f"Scheduled payment reminder for order {order.code} in 2 hours")
    except Exception as e:
        # If scheduling fails, log it but don't break the order flow
        logger.exception(f"Failed to schedule payment reminder for order {order.code}: {e}")
