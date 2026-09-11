"""Background reminder for a daily-dish order the customer asked to be reminded about.

A customer can optionally set "hẹn giờ nhận món" at checkout. Ten minutes
before that time, this fires a second notification for staff - independent
of whether anyone has the dashboard open, since a coffee shop counter is not
always being watched.

There is no Celery or cron here, so this runs as a background thread started
once when the app boots (see start_reminder_thread, called from app.py).
Multiple gunicorn workers each start their own thread and all poll the same
table; the UPDATE ... WHERE reminder_notified = 0 claim below is what keeps
that from sending the same reminder twice.
"""

import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# How far ahead of the appointment the reminder fires.
REMINDER_LEAD = timedelta(minutes=10)

# How often the background thread checks for due reminders.
POLL_INTERVAL_SECONDS = 20

# An appointment this far in the past is treated as stale rather than
# announced - otherwise restarting the server after being down for a while
# would fire a burst of reminders for times long gone.
STALE_AFTER = timedelta(hours=2)


def check_due_reminders(app):
    """One pass: notify for every order whose reminder time has arrived.

    Runs inside its own request-free app context, so it takes the app rather
    than relying on one already being pushed.
    """
    from extensions import db
    from models import Notification, Order

    with app.app_context():
        # process_order stores reminder_at from a plain datetime-local input
        # using datetime.now() - the shop's own wall-clock time, not UTC (the
        # shop and its customers are all in the same timezone). Comparing
        # against utcnow() here made a 7-hour-in-the-future comparison look
        # like it was already 7 hours overdue on a UTC server.
        now = datetime.now()
        due = Order.query.filter(
            Order.reminder_at.isnot(None),
            Order.reminder_notified.is_(False),
            Order.reminder_at <= now + REMINDER_LEAD,
        ).all()

        for order in due:
            stale = order.reminder_at < now - STALE_AFTER
            # Claim this order atomically: if another worker's thread already
            # flipped the flag, this UPDATE matches zero rows and we skip it.
            result = db.session.execute(
                db.text('UPDATE `order` SET reminder_notified = 1 '
                       'WHERE id = :id AND reminder_notified = 0'),
                {'id': order.id},
            )
            db.session.commit()
            if result.rowcount == 0:
                continue
            if stale:
                # Mark it done, but a reminder for a time hours ago is not
                # useful information any more - do not announce it.
                continue

            when = order.reminder_at.strftime('%H:%M')
            db.session.add(Notification(
                type='order_reminder',
                message=(f'⏰ Nhắc hẹn đơn hàng #{order.id} - {order.customer_name}: '
                        f'còn khoảng 10 phút nữa tới giờ hẹn {when}.'),
            ))
            db.session.commit()


def _loop(app):
    while True:
        try:
            check_due_reminders(app)
        except Exception:
            logger.exception('Reminder check failed; will retry on the next tick')
        time.sleep(POLL_INTERVAL_SECONDS)


def start_reminder_thread(app):
    """Start the background loop once per process."""
    thread = threading.Thread(target=_loop, args=(app,), daemon=True,
                              name='order-reminder-thread')
    thread.start()
    return thread
