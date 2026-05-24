from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


# Create your models here.
class CustomUser(AbstractUser):
    first_name = models.CharField(max_length=100, null=False, blank=False)
    last_name = models.CharField(max_length=100, null=False, blank=False)
    username = models.CharField(max_length=100, null=False, blank=False, unique=True)
    email = models.EmailField(max_length=250, null=False, blank=False)
    phone = models.PositiveIntegerField(null=True, blank=True)
    wallet = models.FloatField(null=True, blank=True, default=0.0)
    choices = (
        ("User", "User"),
        ("Agent", "Agent"),
        ("Super Agent", "Super Agent")
    )
    status = models.CharField(max_length=250, null=False, blank=False, choices=choices, default="User")
    password1 = models.CharField(max_length=100, null=False, blank=False)
    password2 = models.CharField(max_length=100, null=False, blank=False)

    def __str__(self):
        return self.username


class AdminInfo(models.Model):
    name = models.CharField(max_length=250, null=True, blank=True)
    phone_number = models.BigIntegerField(null=True, blank=True)
    momo_numberr = models.PositiveBigIntegerField(null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    choices = (
        ("MTN Mobile Money", "MTN Mobile Money"),
        ("Vodafone Cash", "Vodafone Cash"),
        ("AT Money", "AT Money")
    )
    payment_channell = models.CharField(max_length=250, choices=choices)
    afa_price = models.FloatField(null=True, blank=True)

    mtn_api_enabled = models.BooleanField(
        default=False,
        help_text="Route MTN bundle orders through the Geosams Controller API. "
                  "When OFF, orders are saved as Pending for manual fulfilment.",
    )
    telecel_api_enabled = models.BooleanField(
        default=False,
        help_text="Route Telecel bundle orders through the Geosams Controller API.",
    )
    at_api_enabled = models.BooleanField(
        default=False,
        help_text="Route AirtelTigo (iShare) bundle orders through the Geosams Controller API.",
    )
    macrodroid_enabled = models.BooleanField(
        default=True,
        help_text="When ON, top-up requests redirect customers to the MoMo Transaction ID "
                  "claim page (self-service). When OFF, customers see the legacy 'pay and "
                  "wait for admin to credit' page; admin credits manually from the Requests list.",
    )


class IShareBundleTransaction(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    bundle_number = models.BigIntegerField(null=False, blank=False)
    offer = models.CharField(max_length=250, null=False, blank=False)
    reference = models.CharField(max_length=20, null=False, blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    transaction_status = models.CharField(max_length=100, null=False)
    description = models.CharField(max_length=500, null=True, blank=True)
    submitted_to_api = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.bundle_number} - {self.reference}"
    

class IshareBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class AgentIshareBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class SuperAgentIshareBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"
    

class MTNTransaction(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    bundle_number = models.BigIntegerField(null=False, blank=False)
    offer = models.CharField(max_length=250, null=False, blank=False)
    reference = models.CharField(max_length=20, null=False, blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    choices = (
        ("Pending", "Pending"),
        ("Completed", "Completed"),
        ("Failed", "Failed")
    )
    transaction_status = models.CharField(max_length=100, choices=choices, default="Pending")
    description = models.CharField(max_length=500, null=True, blank=True)
    submitted_to_api = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.bundle_number} - {self.reference}"


class BigTimeBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class AgentBigTimeBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class SuperAgentBigTimeBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class MTNBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)


    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class AgentMTNBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)


    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class SuperAgentMTNBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)


    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume/1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class BigTimeTransaction(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    bundle_number = models.BigIntegerField(null=False, blank=False)
    offer = models.CharField(max_length=250, null=False, blank=False)
    reference = models.CharField(max_length=20, null=False, blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    choices = (
        ("Pending", "Pending"),
        ("Completed", "Completed"),
        ("Failed", "Failed")
    )
    transaction_status = models.CharField(max_length=100, choices=choices, default="Pending")
    description = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.bundle_number} - {self.reference}"


class AFARegistration(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    phone_number = models.BigIntegerField(null=False, blank=False)
    gh_card_number = models.CharField(null=False, blank=False, max_length=256)
    name = models.CharField(max_length=250, null=False, blank=False)
    occupation = models.CharField(max_length=250, null=False, blank=True)
    reference = models.CharField(max_length=250, null=False, blank=True)
    date_of_birth = models.DateField(null=False, blank=False)
    choices = (
        ("Pending", "Pending"),
        ("Completed", "Completed"),
        ("Failed", "Failed")
    )
    transaction_status = models.CharField(max_length=100, choices=choices, default="Pending")
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.phone_number} - {self.gh_card_number}"
    

class Payment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    reference = models.CharField(max_length=256, null=False, blank=False)
    amount = models.FloatField(null=True, blank=True)
    channels = (
        ("mtn", "mtn"),
        ("ishare", "ishare"),
        ("bigtime", "bigtime"),
        ("afa", "afa"),
        ("topup", "topup")
    )
    transaction_details = models.JSONField(null=True, blank=True)
    channel = models.CharField(max_length=250, null=True, blank=True, choices=channels)
    payment_description = models.CharField(max_length=500, null=True, blank=True)
    transaction_status = models.CharField(max_length=256, null=True, blank=True, default="Unfinished")
    transaction_date = models.CharField(max_length=250, null=True, blank=True)
    payment_details = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.reference}"


# class TopUpRequest(models.Model):
#     user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
#     reference = models.CharField(max_length=250, null=False, blank=False)
#     amount = models.FloatField(blank=False, null=False)
#     status = models.BooleanField(default=False, blank=False, null=False)
#     date = models.DateTimeField(auto_now_add=True)
#     credited_at = models.DateTimeField(auto_now_add=True)


class TopUpRequestt(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    reference = models.CharField(max_length=250, null=False, blank=False)
    amount = models.FloatField(blank=False, null=False)
    status = models.BooleanField(default=False, blank=False, null=False)
    date = models.DateTimeField(auto_now_add=True)
    credited_at = models.DateTimeField(auto_now_add=True)


class VodaBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume / 1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class AgentVodaBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume / 1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class SuperAgentVodaBundlePrice(models.Model):
    price = models.FloatField(null=False, blank=False)
    bundle_volume = models.FloatField(null=False, blank=False)

    def __str__(self):
        if self.bundle_volume >= 1000:
            return f"GHS{self.price} - {self.bundle_volume / 1000}GB"
        return f"GHS{self.price} - {self.bundle_volume}MB"


class VodafoneTransaction(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    bundle_number = models.BigIntegerField(null=False, blank=False)
    offer = models.CharField(max_length=250, null=False, blank=False)
    reference = models.CharField(max_length=20, null=False, blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    choices = (
        ("Pending", "Pending"),
        ("Completed", "Completed"),
        ("Processing", "Processing"),
        ("Failed", "Failed")
    )
    transaction_status = models.CharField(max_length=100, choices=choices, default="Pending")
    description = models.CharField(max_length=500, null=True, blank=True)
    submitted_to_api = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.bundle_number} - {self.reference}"


class SystemTask(models.Model):
    """
    Ledger row for the in-process scheduler. Each periodic job has one row keyed by
    a stable string. Middleware checks `last_run_at + interval_seconds` per request and
    spawns a daemon thread to run the job when due. Concurrent workers race via
    `select_for_update(skip_locked=True)` so at most one worker fires a given tick.
    """
    key = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    interval_seconds = models.PositiveIntegerField(default=60)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=50, blank=True)
    last_run_detail = models.CharField(max_length=500, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.key} (every {self.interval_seconds}s, enabled={self.enabled})"


class MobileMoneyAlert(models.Model):
    STATUS_CHOICES = (
        ("Unclaimed", "Unclaimed"),
        ("Claimed", "Claimed"),
        ("Ignored", "Ignored"),
        ("Expired", "Expired"),
    )

    raw_sms_body = models.TextField()
    sender_address = models.CharField(max_length=50)
    received_at_phone = models.CharField(max_length=100, blank=True)

    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Unclaimed")
    claimed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_id} - {self.amount} ({self.status})"