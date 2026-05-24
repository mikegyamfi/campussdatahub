import re

import requests
from django.contrib import admin, messages as admin_messages
from django.contrib.auth.admin import UserAdmin
from django.db import transaction as db_transaction
from django.utils.html import format_html
from import_export.admin import ExportActionMixin

from . import geosams, models

ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api"
ARKESEL_API_KEY = "UnBzemdvanJyUGxhTlJzaVVQaHk"


def _parse_mb(offer):
    m = re.search(r"([\d.]+)", offer or "")
    return float(m.group(1)) if m else None


def _send_completion_sms(tx, sender_id="CampusData"):
    if not tx.user or not tx.user.phone:
        return
    body = (
        f"Hello @{tx.user.username}. Your {tx.offer} bundle for {tx.bundle_number} "
        f"has been completed. Ref: {tx.reference}."
    )
    try:
        requests.get(
            ARKESEL_SMS_URL,
            params={
                'action': 'send-sms',
                'api_key': ARKESEL_API_KEY,
                'to': f"0{tx.user.phone}",
                'from': sender_id,
                'sms': body,
            },
            timeout=10,
        )
    except requests.RequestException:
        pass


class CustomUserAdmin(ExportActionMixin, UserAdmin):
    list_display = ['first_name', 'last_name', 'username', 'email', 'wallet', 'phone']

    fieldsets = (
        *UserAdmin.fieldsets,
        ('Other Personal info', {'fields': ('phone', 'wallet', 'status')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'wallet'),
        }),
    )


class GeosamsBundleAdminMixin:
    """
    Shared bulk actions for MTN / Telecel / AT transaction admins.

    Subclass must set:
      network_code   -- one of geosams.NETWORK_{MTN,TELECEL,AT}
      price_models   -- {'User': <Model>, 'Agent': <Model>, 'Super Agent': <Model>}

    Provides four actions:
      - Mark Completed and send SMS
      - Mark Failed and refund wallet (best-effort price lookup against local tables)
      - Submit selected to Geosams API (idempotent via reference)
      - Poll Geosams now for selected
    """
    network_code = None
    price_models = {}

    actions = [
        'action_mark_completed',
        'action_mark_failed_refund',
        'action_resubmit_to_geosams',
        'action_poll_geosams_now',
    ]

    def _resolve_local_price(self, tx):
        mb = _parse_mb(tx.offer)
        if mb is None:
            return None
        model = self.price_models.get(tx.user.status) or self.price_models.get('User')
        if model is None:
            return None
        row = model.objects.filter(bundle_volume=mb).first()
        return row.price if row else None

    @admin.action(description="Mark Completed and send completion SMS")
    def action_mark_completed(self, request, queryset):
        completed = 0
        for tx in queryset.exclude(transaction_status="Completed"):
            tx.transaction_status = "Completed"
            tx.save(update_fields=['transaction_status'])
            _send_completion_sms(tx)
            completed += 1
        self.message_user(
            request, f"Marked {completed} as Completed and sent SMS.",
            level=admin_messages.SUCCESS,
        )

    @admin.action(description="Mark Failed and refund user wallet (best-effort)")
    def action_mark_failed_refund(self, request, queryset):
        failed = 0
        refunded = 0
        skipped_no_price = 0
        for tx in queryset.exclude(transaction_status="Failed"):
            price = self._resolve_local_price(tx)
            with db_transaction.atomic():
                tx.transaction_status = "Failed"
                tx.save(update_fields=['transaction_status'])
                failed += 1
                if price is None:
                    skipped_no_price += 1
                    continue
                user = models.CustomUser.objects.select_for_update().get(pk=tx.user_id)
                user.wallet = (user.wallet or 0.0) + float(price)
                user.save(update_fields=['wallet'])
                refunded += 1
        self.message_user(
            request,
            f"Marked {failed} Failed; refunded {refunded}; "
            f"skipped {skipped_no_price} refunds (no matching price row — handle manually).",
            level=admin_messages.SUCCESS if skipped_no_price == 0 else admin_messages.WARNING,
        )

    @admin.action(description="Submit selected to Geosams API (re-send via reference)")
    def action_resubmit_to_geosams(self, request, queryset):
        if self.network_code is None:
            self.message_user(request, "No network code configured.", level=admin_messages.ERROR)
            return
        if not geosams.is_configured():
            self.message_user(
                request, "GEOSAMS_TOKEN is not set; cannot submit.",
                level=admin_messages.ERROR,
            )
            return
        accepted = 0
        rejected = 0
        skipped = 0
        for tx in queryset:
            mb = _parse_mb(tx.offer)
            if mb is None:
                skipped += 1
                continue
            result = geosams.send_bundle(
                f"0{tx.bundle_number}", mb, self.network_code, tx.reference
            )
            if result.accepted or result.retryable:
                tx.submitted_to_api = True
                tx.description = (result.message or tx.description or "")[:500]
                tx.save(update_fields=['submitted_to_api', 'description'])
                accepted += 1
            else:
                tx.description = (result.message or "rejected")[:500]
                tx.save(update_fields=['description'])
                rejected += 1
        self.message_user(
            request,
            f"Submitted/queued {accepted}; rejected {rejected}; skipped {skipped}.",
            level=admin_messages.SUCCESS if rejected == 0 else admin_messages.WARNING,
        )

    @admin.action(description="Poll Geosams now for selected")
    def action_poll_geosams_now(self, request, queryset):
        if not geosams.is_configured():
            self.message_user(
                request, "GEOSAMS_TOKEN is not set; cannot poll.",
                level=admin_messages.ERROR,
            )
            return
        polled = 0
        transitions = 0
        for tx in queryset.filter(submitted_to_api=True):
            detail = geosams.get_detail(tx.reference)
            polled += 1
            if not detail:
                continue
            status = detail.get('status')
            msg = (detail.get('message') or detail.get('response_message') or "")[:500]
            if status == "Completed" and tx.transaction_status != "Completed":
                tx.transaction_status = "Completed"
                tx.description = msg
                tx.save(update_fields=['transaction_status', 'description'])
                transitions += 1
            elif status in ("Failed", "Canceled and Refunded") and tx.transaction_status != "Failed":
                tx.transaction_status = "Failed"
                tx.description = msg
                tx.save(update_fields=['transaction_status', 'description'])
                transitions += 1
        self.message_user(request, f"Polled {polled}; transitioned {transitions}.")


class IShareBundleTransactionAdmin(GeosamsBundleAdminMixin, admin.ModelAdmin):
    network_code = geosams.NETWORK_AT
    price_models = {
        'User': models.IshareBundlePrice,
        'Agent': models.AgentIshareBundlePrice,
        'Super Agent': models.SuperAgentIshareBundlePrice,
    }
    list_display = ['user', 'bundle_number', 'offer', 'reference',
                    'transaction_status', 'submitted_to_api', 'transaction_date']
    list_filter = ['transaction_status', 'submitted_to_api']
    search_fields = ['reference', 'bundle_number']


class MTNTransactionAdmin(GeosamsBundleAdminMixin, ExportActionMixin, admin.ModelAdmin):
    network_code = geosams.NETWORK_MTN
    price_models = {
        'User': models.MTNBundlePrice,
        'Agent': models.AgentMTNBundlePrice,
        'Super Agent': models.SuperAgentMTNBundlePrice,
    }
    list_display = ['user', 'bundle_number', 'offer', 'reference',
                    'transaction_status', 'submitted_to_api', 'transaction_date']
    list_filter = ['transaction_status', 'submitted_to_api']
    search_fields = ['reference', 'bundle_number']


class VodafoneTransactionAdmin(GeosamsBundleAdminMixin, admin.ModelAdmin):
    network_code = geosams.NETWORK_TELECEL
    price_models = {
        'User': models.VodaBundlePrice,
        'Agent': models.AgentVodaBundlePrice,
        'Super Agent': models.SuperAgentVodaBundlePrice,
    }
    list_display = ['user', 'bundle_number', 'offer', 'reference',
                    'transaction_status', 'submitted_to_api', 'transaction_date']
    list_filter = ['transaction_status', 'submitted_to_api']
    search_fields = ['reference', 'bundle_number']


class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'reference', 'transaction_date', 'amount']


class TopUpRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'reference', 'amount', 'date', 'status']


class AdminInfoAdmin(admin.ModelAdmin):
    list_display = ['name', 'momo_numberr', 'payment_channell',
                    'macrodroid_enabled', 'mtn_api_enabled', 'telecel_api_enabled', 'at_api_enabled']
    fieldsets = (
        ('Business contact', {
            'fields': ('name', 'phone_number', 'momo_numberr', 'email', 'payment_channell'),
        }),
        ('AFA', {'fields': ('afa_price',)}),
        ('MacroDroid MoMo self-service claim', {
            'fields': ('macrodroid_enabled',),
            'description': (
                "When ON, the Top Up page tells the customer they will paste a Transaction "
                "ID from their MoMo SMS, and after submitting the request they land on the "
                "claim page directly. When OFF, customers see the legacy 'pay and wait for "
                "admin' page and you credit them by hand from /admin or the Requests page."
            ),
        }),
        ('Geosams Controller API kill switches', {
            'fields': ('mtn_api_enabled', 'telecel_api_enabled', 'at_api_enabled'),
            'description': (
                "When ON, bundle orders are submitted to the Geosams Controller API "
                "(www.geosams.com/controller). When OFF, orders are saved as Pending "
                "for manual admin fulfilment. Requires GEOSAMS_TOKEN env var to be set."
            ),
        }),
    )


@admin.register(models.SystemTask)
class SystemTaskAdmin(admin.ModelAdmin):
    list_display = ['key', 'enabled', 'interval_seconds', 'last_run_at',
                    'last_run_status', 'last_run_detail']
    list_editable = ['enabled', 'interval_seconds']
    readonly_fields = ['key', 'last_run_at', 'last_run_status', 'last_run_detail']
    fieldsets = (
        (None, {
            'fields': ('key', 'description', 'enabled', 'interval_seconds'),
            'description': (
                "In-process scheduled job ledger. Toggle 'enabled' to pause/resume a "
                "job. The interval is the minimum gap between runs; the actual cadence "
                "depends on incoming web traffic since the scheduler is request-driven."
            ),
        }),
        ('Last run', {'fields': ('last_run_at', 'last_run_status', 'last_run_detail')}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(models.CustomUser, CustomUserAdmin)
admin.site.register(models.IShareBundleTransaction, IShareBundleTransactionAdmin)
admin.site.register(models.MTNTransaction, MTNTransactionAdmin)
admin.site.register(models.IshareBundlePrice)
admin.site.register(models.MTNBundlePrice)
admin.site.register(models.AgentMTNBundlePrice)
admin.site.register(models.AgentIshareBundlePrice)
admin.site.register(models.TopUpRequestt, TopUpRequestAdmin)
admin.site.register(models.Payment, PaymentAdmin)
admin.site.register(models.AdminInfo, AdminInfoAdmin)
admin.site.register(models.SuperAgentIshareBundlePrice)
admin.site.register(models.AFARegistration)
admin.site.register(models.BigTimeTransaction)
admin.site.register(models.SuperAgentMTNBundlePrice)
admin.site.register(models.BigTimeBundlePrice)
admin.site.register(models.AgentBigTimeBundlePrice)
admin.site.register(models.SuperAgentBigTimeBundlePrice)

admin.site.register(models.AgentVodaBundlePrice)
admin.site.register(models.VodafoneTransaction, VodafoneTransactionAdmin)
admin.site.register(models.VodaBundlePrice)
admin.site.register(models.SuperAgentVodaBundlePrice)


@admin.register(models.MobileMoneyAlert)
class MobileMoneyAlertAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'amount_display', 'status_badge',
                    'sender_address', 'claimed_by', 'created_at')
    list_filter = ('status', 'created_at', 'claimed_at', 'sender_address')
    search_fields = ('transaction_id', 'raw_sms_body',
                     'claimed_by__email', 'claimed_by__username')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    readonly_fields = (
        'raw_sms_body', 'sender_address', 'received_at_phone',
        'transaction_id', 'amount', 'claimed_by', 'claimed_at', 'created_at',
    )

    fieldsets = (
        ('SMS Data (Source of Truth)', {
            'fields': ('raw_sms_body', 'sender_address', 'received_at_phone', 'created_at'),
            'classes': ('collapse',),
        }),
        ('Parsed Transaction', {'fields': ('transaction_id', 'amount', 'status')}),
        ('Claim Details', {'fields': ('claimed_by', 'claimed_at')}),
    )

    actions = ['mark_as_expired', 'mark_as_ignored']

    def amount_display(self, obj):
        return f"GHS {obj.amount}"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'

    def status_badge(self, obj):
        colors = {'Unclaimed': '#ffc107', 'Claimed': '#28a745',
                  'Ignored': '#dc3545', 'Expired': '#6c757d'}
        return format_html(
            '<span style="background:{};color:white;padding:4px 8px;border-radius:12px;'
            'font-weight:bold;font-size:11px;">{}</span>',
            colors.get(obj.status, '#343a40'), obj.status,
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    @admin.action(description="Force Expire selected (prevents claiming)")
    def mark_as_expired(self, request, queryset):
        n = queryset.filter(status='Unclaimed').update(status='Expired')
        self.message_user(request, f"Marked {n} alerts as Expired.")

    @admin.action(description="Mark selected as Ignored (junk SMS)")
    def mark_as_ignored(self, request, queryset):
        n = queryset.filter(status='Unclaimed').update(status='Ignored')
        self.message_user(request, f"Marked {n} alerts as Ignored.")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
