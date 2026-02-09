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

from django.conf import settings
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Order, OrderPayment
from pretix.base.services.mail import SendMailException
from pretix.base.services.tasks import TransactionAwareTask
from pretix.celery_app import app

logger = logging.getLogger(__name__)


@app.task(base=TransactionAwareTask, bind=True)
def send_pending_payment_reminder(self, order_code: str, event_id: int) -> None:
    """
    Send order placed reminder email if order is still unpaid after delay.

    This task is scheduled 2 hours after an order is created with POLi payment.
    It checks if the order has been paid, and if not, sends the order placed
    email as a reminder to complete payment.
    """
    with scopes_disabled():
        try:
            order = Order.objects.get(code=order_code, event_id=event_id)
        except Order.DoesNotExist:
            logger.warning(f"Order {order_code} not found, skipping reminder email")
            return

    with scope(organizer=order.event.organizer):
        # Check if order has been paid
        if order.status == Order.STATUS_PAID:
            logger.info(f"Order {order_code} already paid, skipping reminder email")
            return

        # Check if there's a confirmed POLi payment
        if order.payments.filter(
            provider='poli',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED
        ).exists():
            logger.info(f"Order {order_code} has confirmed POLi payment, skipping reminder email")
            return

        # Check if order is expired or canceled
        if order.status in (Order.STATUS_EXPIRED, Order.STATUS_CANCELED):
            logger.info(f"Order {order_code} is {order.status}, skipping reminder email")
            return

        # Send the order placed email as a reminder
        with language(order.locale, order.event.settings.region):
            # Get the email template and subject
            if order.require_approval:
                email_template = order.event.settings.mail_text_order_placed_require_approval
                subject_template = order.event.settings.mail_subject_order_placed_require_approval
                log_entry = 'pretix.event.order.email.order_placed_require_approval'
            else:
                email_template = order.event.settings.mail_text_order_placed
                subject_template = order.event.settings.mail_subject_order_placed
                log_entry = 'pretix.event.order.email.order_placed'

            # Get the payments for this order
            payments = list(order.payments.all())
            email_context = get_email_context(event=order.event, order=order, payments=payments)

            try:
                order.send_mail(
                    subject_template,
                    email_template,
                    email_context,
                    log_entry,
                    invoices=[],
                    attach_tickets=False,  # Don't attach tickets to reminder email
                    attach_ical=False,
                )
                logger.info(f"Sent pending payment reminder email for order {order_code}")
            except SendMailException:
                logger.exception(f"Reminder email for order {order_code} could not be sent")
