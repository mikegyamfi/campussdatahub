import logging

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from intel_app import geosams, models

logger = logging.getLogger(__name__)

TERMINAL_OK = {"Completed"}
TERMINAL_FAIL = {"Failed", "Canceled and Refunded"}


class Command(BaseCommand):
    help = (
        "Polls the Geosams Controller API for each Pending transaction that was "
        "submitted via send_bundle. Updates local status and refunds the user's "
        "wallet when the remote side reports Failed / Canceled and Refunded."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing.')
        parser.add_argument('--limit', type=int, default=200,
                            help='Max transactions to poll per model in one run.')

    def handle(self, *args, **opts):
        if not geosams.is_configured():
            self.stderr.write(self.style.ERROR(
                "GEOSAMS_TOKEN is not set; cannot poll. Aborting."
            ))
            return

        dry_run = opts['dry_run']
        limit = opts['limit']

        # For MTN/Telecel, Geosams's `price` field is GHS (matches our wallet unit), so a
        # Failed/Canceled transaction can be auto-refunded. For AT, Geosams's `price` is MB
        # (matches bundle volume), which does NOT match our GHS wallet — so AT failures are
        # logged for an admin to refund manually.
        targets = [
            ("MTN",     models.MTNTransaction,        True),
            ("Telecel", models.VodafoneTransaction,   True),
            ("AT",      models.IShareBundleTransaction, False),
        ]

        total_updated = 0
        total_refunded = 0
        for label, model, refund_from_price in targets:
            qs = (model.objects
                  .filter(transaction_status="Pending", submitted_to_api=True)
                  .order_by('transaction_date')[:limit])
            count = qs.count()
            self.stdout.write(f"{label}: polling {count} pending tx")
            for tx in qs:
                detail = geosams.get_detail(tx.reference)
                if detail is None:
                    continue
                status = detail.get('status')
                if status not in TERMINAL_OK and status not in TERMINAL_FAIL:
                    continue

                if dry_run:
                    self.stdout.write(f"  [dry] {tx.reference} -> {status}")
                    continue

                with db_transaction.atomic():
                    tx_locked = model.objects.select_for_update().get(pk=tx.pk)
                    if tx_locked.transaction_status != "Pending":
                        continue
                    msg = (detail.get('message') or detail.get('response_message') or "")[:500]
                    if status in TERMINAL_OK:
                        tx_locked.transaction_status = "Completed"
                        tx_locked.description = msg
                        tx_locked.save()
                        total_updated += 1
                    else:
                        tx_locked.transaction_status = "Failed"
                        tx_locked.description = msg
                        tx_locked.save()
                        total_updated += 1
                        if refund_from_price:
                            price = detail.get('price')
                            if price is not None:
                                user = models.CustomUser.objects.select_for_update().get(pk=tx_locked.user_id)
                                user.wallet = (user.wallet or 0.0) + float(price)
                                user.save()
                                total_refunded += 1
                        else:
                            logger.warning(
                                "Geosams reported %s for AT tx %s; manual refund required "
                                "(price field is MB, not GHS).",
                                status, tx_locked.reference,
                            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. {total_updated} transitions, {total_refunded} wallet refunds."
        ))
