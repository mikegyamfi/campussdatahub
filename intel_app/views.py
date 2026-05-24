from datetime import datetime, timedelta
from decimal import Decimal
import logging

from decouple import config
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseRedirect
from django.db import transaction as db_transaction
from django.utils import timezone
import requests
from django.views.decorators.csrf import csrf_exempt
import json

from . import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from . import geosams, helper, models
from .forms import UploadFileForm
from .models import CustomUser
from .utils import parse_momo_sms

logger = logging.getLogger(__name__)

MACRODROID_SECRET = config("MACRODROID_SECRET", default=None)


def _submit_to_geosams(transaction, network, phone_number, amount_mb, reference):
    """
    Submit a Pending transaction row to the Geosams Controller API.
    Mutates the row in place; returns (user_message, rejected_bool).
    Caller refunds the wallet on rejection.
    """
    result = geosams.send_bundle(phone_number, amount_mb, network, reference)
    if result.accepted:
        transaction.submitted_to_api = True
        transaction.description = (result.message or "submitted")[:500]
        transaction.save()
        return "Your transaction has been submitted and will complete shortly.", False
    if result.retryable:
        transaction.submitted_to_api = True
        transaction.description = f"queued; will retry: {result.message}"[:500]
        transaction.save()
        return "Your transaction is queued and will retry shortly.", False
    transaction.transaction_status = "Failed"
    transaction.description = (result.message or "rejected")[:500]
    transaction.save()
    logger.warning("Geosams rejected %s (code=%s): %s", reference, result.code, result.message)
    return f"Transaction rejected: {result.message}", True


def _api_enabled(network):
    admin = models.AdminInfo.objects.filter().first()
    if admin is None:
        return False
    if network == geosams.NETWORK_MTN:
        return bool(admin.mtn_api_enabled)
    if network == geosams.NETWORK_TELECEL:
        return bool(admin.telecel_api_enabled)
    if network == geosams.NETWORK_AT:
        return bool(admin.at_api_enabled)
    return False


# Create your views here.
def home(request):
    return render(request, "layouts/index.html")


def services(request):
    return render(request, "layouts/services.html")


def pay_with_wallet(request):
    if request.method == "POST":
        admin_info = models.AdminInfo.objects.filter().first()
        admin_phone = admin_info.phone_number if admin_info else ""
        user = models.CustomUser.objects.get(id=request.user.id)
        phone_number = request.POST.get("phone")
        amount = request.POST.get("amount")
        reference = request.POST.get("reference")
        if user.wallet is None or user.wallet <= 0 or user.wallet < float(amount):
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge. Admin Contact Info: 0{admin_phone}'})

        if user.status == "Agent":
            bundle = models.AgentIshareBundlePrice.objects.get(price=float(amount)).bundle_volume
        elif user.status == "Super Agent":
            bundle = models.SuperAgentIshareBundlePrice.objects.get(price=float(amount)).bundle_volume
        else:
            bundle = models.IshareBundlePrice.objects.get(price=float(amount)).bundle_volume

        user.wallet -= float(amount)
        user.save()

        new_transaction = models.IShareBundleTransaction.objects.create(
            user=request.user,
            bundle_number=phone_number,
            offer=f"{bundle}MB",
            reference=reference,
            transaction_status="Pending",
        )

        if _api_enabled(geosams.NETWORK_AT):
            msg, rejected = _submit_to_geosams(
                new_transaction, geosams.NETWORK_AT, phone_number, bundle, reference
            )
            if rejected:
                user.wallet += float(amount)
                user.save()
                return JsonResponse({'status': msg, 'icon': 'error'})
            return JsonResponse({'status': msg, 'icon': 'success'})

        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    return redirect('airtel-tigo')


@login_required(login_url='login')
def airtel_tigo(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    status = user.status
    form = forms.IShareBundleForm(status)
    reference = helper.ref_generator()
    user_email = request.user.email
    if request.method == "POST":
        form = forms.IShareBundleForm(data=request.POST, status=status)
        if form.is_valid():
            phone_number = form.cleaned_data["phone_number"]
            amount = form.cleaned_data["offers"]

            print(amount.price)

            details = {
                'phone_number': phone_number,
                'offers': amount.price
            }

            new_payment = models.Payment.objects.create(
                user=request.user,
                reference=reference,
                transaction_date=datetime.now(),
                transaction_details=details,
                channel="ishare",
            )
            new_payment.save()
            print("payment saved")
            print("form valid")

            url = "https://payproxyapi.hubtel.com/items/initiate"

            payload = json.dumps({
                "totalAmount": float(amount.price) + (1 / 100) * float(amount.price),
                "description": "Payment for AT Bundle",
                "callbackUrl": "https://www.geosams.com/hubtel_webhook",
                "returnUrl": "https://www.geosams.com",
                "cancellationUrl": "https://www.geosams.com",
                "merchantAccountNumber": "2019751",
                "clientReference": new_payment.reference
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic TnhvOFo2ejpjNDRlYmRiZTNjMWY0ZTgxODliNDU2MTE4OGQ3MjkyYg=='
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            data = response.json()

            checkoutUrl = data['data']['checkoutUrl']

            return redirect(checkoutUrl)
    # if request.method == "POST":
    #     form = forms.IShareBundleForm(data=request.POST, status=status)
    #     payment_reference = request.POST.get("reference")
    #     amount_paid = request.POST.get("amount")
    #     new_payment = models.Payment.objects.create(
    #         user=request.user,
    #         reference=payment_reference,
    #         amount=amount_paid,
    #         transaction_date=datetime.now(),
    #         transaction_status="Completed"
    #     )
    #     new_payment.save()
    #     print("payment saved")
    #     print("form valid")
    #     phone_number = request.POST.get("phone")
    #     offer = request.POST.get("amount")
    #     print(offer)
    #     if user.status == "User":
    #         bundle = models.IshareBundlePrice.objects.get(price=float(offer)).bundle_volume
    #     elif user.status == "Agent":
    #         bundle = models.AgentIshareBundlePrice.objects.get(price=float(offer)).bundle_volume
    #     elif user.status == "Super Agent":
    #         bundle = models.SuperAgentIshareBundlePrice.objects.get(price=float(offer)).bundle_volume
    #     else:
    #         bundle = models.IshareBundlePrice.objects.get(price=float(offer)).bundle_volume
    #
    #     new_transaction = models.IShareBundleTransaction.objects.create(
    #         user=request.user,
    #         bundle_number=phone_number,
    #         offer=f"{bundle}MB",
    #         reference=payment_reference,
    #         transaction_status="Pending"
    #     )
    #     print("created")
    #     new_transaction.save()
    #
    #     print("===========================")
    #     print(phone_number)
    #     print(bundle)
    #     send_bundle_response = helper.send_bundle(request.user, phone_number, bundle, payment_reference)
    #     data = send_bundle_response.json()
    #
    #     print(data)
    #
    #     sms_headers = {
    #         'Authorization': 'Bearer 1136|LwSl79qyzTZ9kbcf9SpGGl1ThsY0Ujf7tcMxvPze',
    #         'Content-Type': 'application/json'
    #     }
    #
    #     sms_url = 'https://webapp.usmsgh.com/api/sms/send'
    #
    #     if send_bundle_response.status_code == 200:
    #         if data["code"] == "0000":
    #             transaction_to_be_updated = models.IShareBundleTransaction.objects.get(reference=payment_reference)
    #             print("got here")
    #             print(transaction_to_be_updated.transaction_status)
    #             transaction_to_be_updated.transaction_status = "Completed"
    #             transaction_to_be_updated.save()
    #             print(request.user.phone)
    #             print("***********")
    #             receiver_message = f"Your bundle purchase has been completed successfully. {bundle}MB has been credited to you by {request.user.phone}.\nReference: {payment_reference}\n"
    #             sms_message = f"Hello @{request.user.username}. Your bundle purchase has been completed successfully. {bundle}MB has been credited to {phone_number}.\nReference: {payment_reference}\nThank you for using Geosams GH.\n\nThe Geosams GH"
    #
    #             num_without_0 = phone_number[1:]
    #             print(num_without_0)
    #             receiver_body = {
    #                 'recipient': f"233{num_without_0}",
    #                 'sender_id': 'Geosams',
    #                 'message': receiver_message
    #             }
    #
    #             response = requests.request('POST', url=sms_url, params=receiver_body, headers=sms_headers)
    #             print(response.text)
    #
    #             sms_body = {
    #                 'recipient': f"233{request.user.phone}",
    #                 'sender_id': 'Geosams',
    #                 'message': sms_message
    #             }
    #
    #             response = requests.request('POST', url=sms_url, params=sms_body, headers=sms_headers)
    #
    #             print(response.text)
    #
    #             return JsonResponse({'status': 'Transaction Completed Successfully', 'icon': 'success'})
    #         else:
    #             transaction_to_be_updated = models.IShareBundleTransaction.objects.get(reference=payment_reference)
    #             transaction_to_be_updated.transaction_status = "Failed"
    #             new_transaction.save()
    #             sms_message = f"Hello @{request.user.username}. Something went wrong with your transaction. Contact us for enquiries.\nBundle: {bundle}MB\nPhone Number: {phone_number}.\nReference: {payment_reference}\nThank you for using Geosams GH.\n\nThe Geosams GH"
    #
    #             sms_body = {
    #                 'recipient': f"233{request.user.phone}",
    #                 'sender_id': 'Geosams',
    #                 'message': sms_message
    #             }
    #             # response = requests.request('POST', url=sms_url, params=sms_body, headers=sms_headers)
    #             # print(response.text)
    #             # r_sms_url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=UmpEc1JzeFV4cERKTWxUWktqZEs&to={phone_number}&from=Geosams GH&sms={receiver_message}"
    #             # response = requests.request("GET", url=r_sms_url)
    #             # print(response.text)
    #             return JsonResponse({'status': 'Something went wrong', 'icon': 'error'})
    #     else:
    #         transaction_to_be_updated = models.IShareBundleTransaction.objects.get(reference=payment_reference)
    #         transaction_to_be_updated.transaction_status = "Failed"
    #         new_transaction.save()
    #         sms_message = f"Hello @{request.user.username}. Something went wrong with your transaction. Contact us for enquiries.\nBundle: {bundle}MB\nPhone Number: {phone_number}.\nReference: {payment_reference}\nThank you for using Geosams GH.\n\nThe Geosams GH"
    #
    #         sms_body = {
    #             'recipient': f'233{request.user.phone}',
    #             'sender_id': 'Geosams',
    #             'message': sms_message
    #         }
    #
    #         # response = requests.request('POST', url=sms_url, params=sms_body, headers=sms_headers)
    #         #
    #         # print(response.text)
    #         return JsonResponse({'status': 'Something went wrong', 'icon': 'error'})
    user = models.CustomUser.objects.get(id=request.user.id)
    context = {"form": form, "ref": reference, "email": user_email, "wallet": 0 if user.wallet is None else user.wallet}
    return render(request, "layouts/services/at.html", context=context)


def mtn_pay_with_wallet(request):
    if request.method == "POST":
        admin_info = models.AdminInfo.objects.filter().first()
        admin_phone = admin_info.phone_number if admin_info else ""
        user = models.CustomUser.objects.get(id=request.user.id)
        phone_number = request.POST.get("phone")
        amount = request.POST.get("amount")
        reference = request.POST.get("reference")

        if user.wallet is None or user.wallet <= 0 or user.wallet < float(amount):
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge. Admin Contact Info: 0{admin_phone}'})

        if user.status == "Agent":
            bundle = models.AgentMTNBundlePrice.objects.get(price=float(amount)).bundle_volume
        elif user.status == "Super Agent":
            bundle = models.SuperAgentMTNBundlePrice.objects.get(price=float(amount)).bundle_volume
        else:
            bundle = models.MTNBundlePrice.objects.get(price=float(amount)).bundle_volume

        user.wallet -= float(amount)
        user.save()

        new_mtn_transaction = models.MTNTransaction.objects.create(
            user=request.user,
            bundle_number=phone_number,
            offer=f"{bundle}MB",
            reference=reference,
        )

        if _api_enabled(geosams.NETWORK_MTN):
            msg, rejected = _submit_to_geosams(
                new_mtn_transaction, geosams.NETWORK_MTN, phone_number, bundle, reference
            )
            if rejected:
                user.wallet += float(amount)
                user.save()
                return JsonResponse({'status': msg, 'icon': 'error'})
            return JsonResponse({'status': msg, 'icon': 'success'})

        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    return redirect('mtn')


@login_required(login_url='login')
def big_time_pay_with_wallet(request):
    if request.method == "POST":
        user = models.CustomUser.objects.get(id=request.user.id)
        phone_number = request.POST.get("phone")
        amount = request.POST.get("amount")
        reference = request.POST.get("reference")
        print(phone_number)
        print(amount)
        print(reference)
        if user.wallet is None:
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge.'})
        elif user.wallet <= 0 or user.wallet < float(amount):
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge.'})
        if user.status == "User":
            bundle = models.BigTimeBundlePrice.objects.get(price=float(amount)).bundle_volume
        elif user.status == "Agent":
            bundle = models.AgentBigTimeBundlePrice.objects.get(price=float(amount)).bundle_volume
        elif user.status == "Super Agent":
            bundle = models.SuperAgentBigTimeBundlePrice.objects.get(price=float(amount)).bundle_volume
        else:
            bundle = models.BigTimeBundlePrice.objects.get(price=float(amount)).bundle_volume
        print(bundle)
        new_mtn_transaction = models.BigTimeTransaction.objects.create(
            user=request.user,
            bundle_number=phone_number,
            offer=f"{bundle}MB",
            reference=reference,
        )
        new_mtn_transaction.save()
        user.wallet -= float(amount)
        user.save()
        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    return redirect('big_time')


@login_required(login_url='login')
def mtn(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    status = user.status
    form = forms.MTNForm(status=status)
    reference = helper.ref_generator()
    user_email = request.user.email
    admin = models.AdminInfo.objects.filter().first().phone_number
    if request.method == "POST":
        form = forms.MTNForm(data=request.POST, status=status)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']
            amount = form.cleaned_data['offers']

            print(amount.price)

            details = {
                'phone_number': phone_number,
                'offers': amount.price
            }

            new_payment = models.Payment.objects.create(
                user=request.user,
                reference=reference,
                transaction_date=datetime.now(),
                transaction_details=details,
                channel="mtn",
            )
            new_payment.save()
            print("payment saved")
            print("form valid")

            url = "https://payproxyapi.hubtel.com/items/initiate"

            payload = json.dumps({
                "totalAmount": float(amount.price) + (1 / 100) * float(amount.price),
                "description": "Payment for MTN Bundle",
                "callbackUrl": "https://www.geosams.com/hubtel_webhook",
                "returnUrl": "https://www.geosams.com",
                "cancellationUrl": "https://www.geosams.com",
                "merchantAccountNumber": "2019751",
                "clientReference": new_payment.reference
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic TnhvOFo2ejpjNDRlYmRiZTNjMWY0ZTgxODliNDU2MTE4OGQ3MjkyYg=='
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            data = response.json()

            checkoutUrl = data['data']['checkoutUrl']

            return redirect(checkoutUrl)
    user = models.CustomUser.objects.get(id=request.user.id)
    context = {'form': form, "ref": reference, "email": user_email, "wallet": 0 if user.wallet is None else user.wallet}
    return render(request, "layouts/services/mtn.html", context=context)


@login_required(login_url='login')
def afa_registration(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    reference = helper.ref_generator()
    price = models.AdminInfo.objects.filter().first().afa_price
    user_email = request.user.email
    print(price)
    if request.method == "POST":
        form = forms.AFARegistrationForm(request.POST)
        if form.is_valid():
            # name = transaction_details["name"]
            # phone_number = transaction_details["phone"]
            # gh_card_number = transaction_details["card"]
            # occupation = transaction_details["occupation"]
            # date_of_birth = transaction_details["date_of_birth"]
            details = {
                "name": form.cleaned_data["name"],
                "phone": form.cleaned_data["phone_number"],
                "card": form.cleaned_data["gh_card_number"],
                "occupation": form.cleaned_data["occupation"],
                "date_of_birth": form.cleaned_data["date_of_birth"],
            }
            new_payment = models.Payment.objects.create(
                user=request.user,
                reference=reference,
                transaction_details=details,
                transaction_date=datetime.now(),
                channel="afa"
            )
            new_payment.save()

            url = "https://payproxyapi.hubtel.com/items/initiate"

            payload = json.dumps({
                "totalAmount": float(price) + (1 / 100) * float(price),
                "description": "Payment for AFA Registration",
                "callbackUrl": "https://www.geosams.com/hubtel_webhook",
                "returnUrl": "https://www.geosams.com",
                "cancellationUrl": "https://www.geosams.com",
                "merchantAccountNumber": "2019751",
                "clientReference": new_payment.reference
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic TnhvOFo2ejpjNDRlYmRiZTNjMWY0ZTgxODliNDU2MTE4OGQ3MjkyYg=='
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            data = response.json()

            checkoutUrl = data['data']['checkoutUrl']

            return redirect(checkoutUrl)
    form = forms.AFARegistrationForm()
    context = {'form': form, 'ref': reference, 'price': price, "email": user_email,
               "wallet": 0 if user.wallet is None else user.wallet}
    return render(request, "layouts/services/afa.html", context=context)


def afa_registration_wallet(request):
    if request.method == "POST":
        user = models.CustomUser.objects.get(id=request.user.id)
        phone_number = request.POST.get("phone")
        amount = request.POST.get("amount")
        reference = request.POST.get("reference")
        name = request.POST.get("name")
        card_number = request.POST.get("card")
        occupation = request.POST.get("occupation")
        date_of_birth = request.POST.get("birth")
        price = models.AdminInfo.objects.filter().first().afa_price

        if user.wallet is None:
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge.'})
        elif user.wallet <= 0 or user.wallet < float(amount):
            return JsonResponse(
                {'status': f'Your wallet balance is low. Contact the admin to recharge.'})

        new_registration = models.AFARegistration.objects.create(
            user=user,
            reference=reference,
            name=name,
            phone_number=phone_number,
            gh_card_number=card_number,
            occupation=occupation,
            date_of_birth=date_of_birth
        )
        new_registration.save()
        user.wallet -= float(price)
        user.save()
        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    return redirect('home')


@login_required(login_url='login')
def big_time(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    status = user.status
    form = forms.BigTimeBundleForm(status)
    reference = helper.ref_generator()
    user_email = request.user.email

    if request.method == "POST":
        form = forms.BigTimeBundleForm(data=request.POST, status=status)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']
            amount = form.cleaned_data['offers']
            details = {
                'phone_number': phone_number,
                'offers': amount.price
            }
            new_payment = models.Payment.objects.create(
                user=request.user,
                reference=reference,
                transaction_details=details,
                transaction_date=datetime.now(),
                channel="bigtime"
            )
            new_payment.save()

            url = "https://payproxyapi.hubtel.com/items/initiate"

            payload = json.dumps({
                "totalAmount": float(amount.price) + (1 / 100) * float(amount.price),
                "description": "Payment for AFA Registration",
                "callbackUrl": "https://www.geosams.com/hubtel_webhook",
                "returnUrl": "https://www.geosams.com",
                "cancellationUrl": "https://www.geosams.com",
                "merchantAccountNumber": "2019751",
                "clientReference": new_payment.reference
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic TnhvOFo2ejpjNDRlYmRiZTNjMWY0ZTgxODliNDU2MTE4OGQ3MjkyYg=='
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            data = response.json()

            checkoutUrl = data['data']['checkoutUrl']

            return redirect(checkoutUrl)
    user = models.CustomUser.objects.get(id=request.user.id)
    # phone_num = user.phone
    # mtn_dict = {}
    #
    # if user.status == "Agent":
    #     mtn_offer = models.AgentMTNBundlePrice.objects.all()
    # else:
    #     mtn_offer = models.MTNBundlePrice.objects.all()
    # for offer in mtn_offer:
    #     mtn_dict[str(offer)] = offer.bundle_volume
    context = {'form': form,
               "ref": reference, "email": user_email, "wallet": 0 if user.wallet is None else user.wallet}
    return render(request, "layouts/services/big_time.html", context=context)


@login_required(login_url='login')
def history(request):
    user_transactions = models.IShareBundleTransaction.objects.filter(user=request.user).order_by(
        'transaction_date').reverse()[:1000]
    header = "AirtelTigo Transactions"
    net = "tigo"
    context = {'txns': user_transactions, "header": header, "net": net}
    return render(request, "layouts/history.html", context=context)


@login_required(login_url='login')
def mtn_history(request):
    user_transactions = models.MTNTransaction.objects.filter(user=request.user).order_by('transaction_date').reverse()[:1000]
    header = "MTN Transactions"
    net = "mtn"
    context = {'txns': user_transactions, "header": header, "net": net}
    return render(request, "layouts/history.html", context=context)


@login_required(login_url='login')
def big_time_history(request):
    user_transactions = models.BigTimeTransaction.objects.filter(user=request.user).order_by(
        'transaction_date').reverse()[:1000]
    header = "Big Time Transactions"
    net = "bt"
    context = {'txns': user_transactions, "header": header, "net": net}
    return render(request, "layouts/history.html", context=context)


@login_required(login_url='login')
def afa_history(request):
    user_transactions = models.AFARegistration.objects.filter(user=request.user).order_by('transaction_date').reverse()[:1000]
    header = "AFA Registrations"
    net = "afa"
    context = {'txns': user_transactions, "header": header, "net": net}
    return render(request, "layouts/afa_history.html", context=context)


def verify_transaction(request, reference):
    if request.method == "GET":
        response = helper.verify_paystack_transaction(reference)
        data = response.json()
        try:
            status = data["data"]["status"]
            amount = data["data"]["amount"]
            api_reference = data["data"]["reference"]
            date = data["data"]["paid_at"]
            real_amount = float(amount) / 100
            print(status)
            print(real_amount)
            print(api_reference)
            print(reference)
            print(date)
        except:
            status = data["status"]
        return JsonResponse({'status': status})


@login_required(login_url='login')
def admin_mtn_history(request):
    if request.user.is_staff and request.user.is_superuser:
        all_txns = models.MTNTransaction.objects.all().order_by('transaction_date').reverse()[:1000]
        context = {'txns': all_txns}
        return render(request, "layouts/services/mtn_admin.html", context=context)


@login_required(login_url='login')
def admin_bt_history(request):
    if request.user.is_staff and request.user.is_superuser:
        all_txns = models.BigTimeTransaction.objects.filter().order_by('-transaction_date')[:1000]
        context = {'txns': all_txns}
        return render(request, "layouts/services/bt_admin.html", context=context)


@login_required(login_url='login')
def admin_afa_history(request):
    if request.user.is_staff and request.user.is_superuser:
        all_txns = models.AFARegistration.objects.filter().order_by('-transaction_date')[:1000]
        context = {'txns': all_txns}
        return render(request, "layouts/services/afa_admin.html", context=context)


@login_required(login_url='login')
def mark_as_sent(request, pk):
    if request.user.is_staff and request.user.is_superuser:
        txn = models.MTNTransaction.objects.filter(id=pk).first()
        print(txn)
        txn.transaction_status = "Completed"
        txn.save()
        sms_headers = {
            'Authorization': 'Bearer 1136|LwSl79qyzTZ9kbcf9SpGGl1ThsY0Ujf7tcMxvPze',
            'Content-Type': 'application/json'
        }

        sms_url = 'https://webapp.usmsgh.com/api/sms/send'
        sms_message = f"Your account has been credited with {txn.offer}.\nTransaction Reference: {txn.reference}"

        response1 = requests.get(
            f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=UnBzemdvanJyUGxhTlJzaVVQaHk&to=0{request.user.phone}&from=CampusData&sms={sms_message}")
        print(response1.text)

        return redirect('mtn_admin')


@login_required(login_url='login')
def bt_mark_as_sent(request, pk):
    if request.user.is_staff and request.user.is_superuser:
        txn = models.BigTimeTransaction.objects.filter(id=pk).first()
        print(txn)
        txn.transaction_status = "Completed"
        txn.save()
        sms_headers = {
            'Authorization': 'Bearer 1136|LwSl79qyzTZ9kbcf9SpGGl1ThsY0Ujf7tcMxvPze',
            'Content-Type': 'application/json'
        }

        sms_url = 'https://webapp.usmsgh.com/api/sms/send'
        sms_message = f"Your AT BIG TIME transaction has been completed. {txn.bundle_number} has been credited with {txn.offer}.\nTransaction Reference: {txn.reference}"

        response1 = requests.get(
            f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=UnBzemdvanJyUGxhTlJzaVVQaHk&to=0{request.user.phone}&from=CampusData&sms={sms_message}")
        print(response1.text)
        messages.success(request, f"Transaction Completed")
        return redirect('bt_admin')


@login_required(login_url='login')
def afa_mark_as_sent(request, pk):
    if request.user.is_staff and request.user.is_superuser:
        txn = models.AFARegistration.objects.filter(id=pk).first()
        print(txn)
        txn.transaction_status = "Completed"
        txn.save()
        sms_headers = {
            'Authorization': 'Bearer 1136|LwSl79qyzTZ9kbcf9SpGGl1ThsY0Ujf7tcMxvPze',
            'Content-Type': 'application/json'
        }

        sms_url = 'https://webapp.usmsgh.com/api/sms/send'
        sms_message = f"Your AFA Registration has been completed. {txn.phone_number} has been registered.\nTransaction Reference: {txn.reference}"

        response1 = requests.get(
            f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=UnBzemdvanJyUGxhTlJzaVVQaHk&to=0{request.user.phone}&from=CampusData&sms={sms_message}")
        print(response1.text)
        messages.success(request, f"Transaction Completed")
        return redirect('afa_admin')


def credit_user(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    if request.user.is_superuser:
        form = forms.CreditUserForm()
        if request.method == "POST":
            form = forms.CreditUserForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data["user"]
                amount = form.cleaned_data["amount"]
                print(user)
                print(amount)
                user_needed = models.CustomUser.objects.get(username=user)
                if user_needed.wallet is None:
                    user_needed.wallet = amount
                else:
                    user_needed.wallet += float(amount)
                user_needed.save()
                print(user_needed.username)
                messages.success(request, "Crediting Successful")
                return redirect('credit_user')
        context = {'form': form}
        return render(request, "layouts/services/credit.html", context=context)
    else:
        messages.success(request, "Access Denied")
        return redirect('home')


@login_required(login_url='login')
def topup_info(request):
    # if request.method == "POST":
    #     admin = models.AdminInfo.objects.filter().first().phone_number
    #     user = models.CustomUser.objects.get(id=request.user.id)
    #     amount = request.POST.get("amount")
    #     print(amount)
    #     reference = helper.top_up_ref_generator()
    #     details = {
    #         'topup_amount': amount
    #     }
    #     new_payment = models.Payment.objects.create(
    #         user=request.user,
    #         reference=reference,
    #         transaction_details=details,
    #         transaction_date=datetime.now(),
    #         channel="topup"
    #     )
    #     new_payment.save()
    #
    #     url = "https://payproxyapi.hubtel.com/items/initiate"
    #     print("hello world")
    #     print("Amount is " + amount)
    #
    #     try:
    #         total_amount = float(amount) + (1 / 100) * float(amount)
    #     except:
    #         return redirect('topup-info')
    #
    #     payload = json.dumps({
    #         "totalAmount": total_amount,
    #         "description": "Payment for Wallet Topup",
    #         "callbackUrl": "https://www.geosams.com/hubtel_webhook",
    #         "returnUrl": "https://www.geosams.com",
    #         "cancellationUrl": "https://www.geosams.com",
    #         "merchantAccountNumber": "2019751",
    #         "clientReference": new_payment.reference
    #     })
    #     headers = {
    #         'Content-Type': 'application/json',
    #         'Authorization': 'Basic TnhvOFo2ejpjNDRlYmRiZTNjMWY0ZTgxODliNDU2MTE4OGQ3MjkyYg=='
    #     }
    #
    #     response = requests.request("POST", url, headers=headers, data=payload)
    #
    #     data = response.json()
    #
    #     checkoutUrl = data['data']['checkoutUrl']
    #
    #     return redirect(checkoutUrl)
    admin_info = models.AdminInfo.objects.filter().first()
    macrodroid_on = admin_info.macrodroid_enabled if admin_info else True

    if request.method == "POST":
        amount = request.POST.get("amount")
        reference = helper.top_up_ref_generator()
        models.TopUpRequestt.objects.create(
            user=request.user,
            amount=amount,
            reference=reference,
        )

        if macrodroid_on:
            messages.success(
                request,
                f"Request created. Pay GHS {amount} to the number below, then paste the "
                f"Transaction ID from your MoMo SMS to credit your wallet instantly."
            )
            return redirect("claim_topup", reference=reference)

        admin_phone = admin_info.phone_number if admin_info else ""
        messages.success(
            request,
            f"Your request has been sent. Kindly pay to {admin_phone} and quote the "
            f"reference. Reference: {reference}"
        )
        return redirect("request_successful", reference)

    context = {
        "macrodroid_on": macrodroid_on,
        "business_momo_number": f"0{admin_info.momo_numberr}" if admin_info and admin_info.momo_numberr else "",
        "business_momo_name": admin_info.name if admin_info else "",
        "channel": admin_info.payment_channell if admin_info else "",
    }
    return render(request, "layouts/topup-info.html", context=context)


@login_required(login_url='login')
def request_successful(request, reference):
    admin = models.AdminInfo.objects.filter().first()
    context = {
        "name": admin.name if admin else "",
        "number": f"0{admin.momo_numberr}" if admin and admin.momo_numberr else "",
        "channel": admin.payment_channell if admin else "",
        "reference": reference,
        "macrodroid_on": admin.macrodroid_enabled if admin else True,
    }
    return render(request, "layouts/services/request_successful.html", context=context)


def topup_list(request):
    if request.user.is_superuser:
        topup_requests = models.TopUpRequestt.objects.all().order_by('date').reverse()
        context = {
            'requests': topup_requests,
        }
        return render(request, "layouts/services/topup_list.html", context=context)
    else:
        messages.error(request, "Access Denied")
        return redirect('home')


@login_required(login_url='login')
def credit_user_from_list(request, reference):
    if request.user.is_superuser:
        crediting = models.TopUpRequestt.objects.filter(reference=reference).first()
        if crediting.status:
            return redirect('topup_list')
        user = crediting.user
        custom_user = models.CustomUser.objects.get(username=user.username)
        amount = crediting.amount
        print(user)
        print(user.phone)
        print(amount)
        custom_user.wallet += amount
        custom_user.save()
        crediting.status = True
        crediting.credited_at = datetime.now()
        crediting.save()
        sms_headers = {
            'Authorization': 'Bearer 1334|wroIm5YnQD6hlZzd8POtLDXxl4vQodCZNorATYGX',
            'Content-Type': 'application/json'
        }

        sms_url = 'https://webapp.usmsgh.com/api/sms/send'
        sms_message = f"Hello,\nYour wallet has been topped up with GHS{amount}.\nReference: {reference}.\nThank you"

        response1 = requests.get(
            f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=UnBzemdvanJyUGxhTlJzaVVQaHk&to=0{request.user.phone}&from=CampusData&sms={sms_message}")
        print(response1.text)
        messages.success(request, f"{user} has been credited with {amount}")
        return redirect('topup_list')


@csrf_exempt
def hubtel_webhook(request):
    if request.method == 'POST':
        print("hit the webhook")
        try:
            payload = request.body.decode('utf-8')
            print("Hubtel payment Info: ", payload)
            json_payload = json.loads(payload)
            print(json_payload)

            data = json_payload.get('Data')
            print(data)
            reference = data.get('ClientReference')
            print(reference)
            txn_status = data.get('Status')
            txn_description = data.get('Description')
            amount = data.get('Amount')
            print(txn_status, amount)

            if txn_status == 'Success':
                print("success")
                transaction_saved = models.Payment.objects.get(reference=reference, transaction_status="Unfinished")
                transaction_saved.transaction_status = "Paid"
                transaction_saved.payment_description = txn_description
                transaction_saved.amount = amount
                transaction_saved.save()
                transaction_details = transaction_saved.transaction_details
                transaction_channel = transaction_saved.channel
                user = transaction_saved.user
                # receiver = collection_saved['number']
                # bundle_volume = collection_saved['data_volume']
                # name = collection_saved['name']
                # email = collection_saved['email']
                # phone_number = collection_saved['buyer']
                # date_and_time = collection_saved['date_and_time']
                # txn_type = collection_saved['type']
                # user_id = collection_saved['uid']
                print(transaction_details, transaction_channel)

                if transaction_channel == "ishare":
                    offer = transaction_details["offers"]
                    phone_number = transaction_details["phone_number"]
                    phone_str = f"0{phone_number}"

                    if user.status == "Agent":
                        bundle = models.AgentIshareBundlePrice.objects.get(price=float(offer)).bundle_volume
                    elif user.status == "Super Agent":
                        bundle = models.SuperAgentIshareBundlePrice.objects.get(price=float(offer)).bundle_volume
                    else:
                        bundle = models.IshareBundlePrice.objects.get(price=float(offer)).bundle_volume

                    new_transaction = models.IShareBundleTransaction.objects.create(
                        user=user,
                        bundle_number=phone_number,
                        offer=f"{bundle}MB",
                        reference=reference,
                        transaction_status="Pending",
                    )

                    if _api_enabled(geosams.NETWORK_AT):
                        _submit_to_geosams(
                            new_transaction, geosams.NETWORK_AT, phone_str, bundle, reference
                        )
                    return JsonResponse(
                        {'status': "Your transaction will be completed shortly"}, status=200,
                    )
                elif transaction_channel == "mtn":
                    offer = transaction_details["offers"]
                    phone_number = transaction_details["phone_number"]
                    phone_str = f"0{phone_number}"

                    if user.status == "Agent":
                        bundle = models.AgentMTNBundlePrice.objects.get(price=float(offer)).bundle_volume
                    elif user.status == "Super Agent":
                        bundle = models.SuperAgentMTNBundlePrice.objects.get(price=float(offer)).bundle_volume
                    else:
                        bundle = models.MTNBundlePrice.objects.get(price=float(offer)).bundle_volume

                    new_mtn_transaction = models.MTNTransaction.objects.create(
                        user=user,
                        bundle_number=phone_number,
                        offer=f"{bundle}MB",
                        reference=reference,
                    )

                    if _api_enabled(geosams.NETWORK_MTN):
                        _submit_to_geosams(
                            new_mtn_transaction, geosams.NETWORK_MTN, phone_str, bundle, reference
                        )
                    return JsonResponse(
                        {'status': "Your transaction will be completed shortly"}, status=200,
                    )
                elif transaction_channel == "telecel":
                    offer = transaction_details["offers"]
                    phone_number = transaction_details["phone_number"]
                    phone_str = f"0{phone_number}"

                    if user.status == "Agent":
                        bundle = models.AgentVodaBundlePrice.objects.get(price=float(offer)).bundle_volume
                    elif user.status == "Super Agent":
                        bundle = models.SuperAgentVodaBundlePrice.objects.get(price=float(offer)).bundle_volume
                    else:
                        bundle = models.VodaBundlePrice.objects.get(price=float(offer)).bundle_volume

                    new_voda_transaction = models.VodafoneTransaction.objects.create(
                        user=user,
                        bundle_number=phone_number,
                        offer=f"{bundle}MB",
                        reference=reference,
                    )

                    if _api_enabled(geosams.NETWORK_TELECEL):
                        _submit_to_geosams(
                            new_voda_transaction, geosams.NETWORK_TELECEL, phone_str, bundle, reference
                        )
                    return JsonResponse(
                        {'status': "Your transaction will be completed shortly"}, status=200,
                    )
                elif transaction_channel == "bigtime":
                    offer = transaction_details["offers"]
                    phone_number = transaction_details["phone_number"]
                    if user.status == "User":
                        bundle = models.BigTimeBundlePrice.objects.get(price=float(offer)).bundle_volume
                    elif user.status == "Agent":
                        bundle = models.AgentBigTimeBundlePrice.objects.get(price=float(offer)).bundle_volume
                    elif user.status == "Super Agent":
                        bundle = models.SuperAgentBigTimeBundlePrice.objects.get(price=float(offer)).bundle_volume
                    else:
                        bundle = models.SuperAgentBigTimeBundlePrice.objects.get(price=float(offer)).bundle_volume
                    print(phone_number)
                    new_mtn_transaction = models.BigTimeTransaction.objects.create(
                        user=user,
                        bundle_number=phone_number,
                        offer=f"{bundle}MB",
                        reference=reference,
                    )
                    new_mtn_transaction.save()
                    return JsonResponse({'status': "Your transaction will be completed shortly"}, status=200)
                elif transaction_channel == "afa":
                    name = transaction_details["name"]
                    phone_number = transaction_details["phone"]
                    gh_card_number = transaction_details["card"]
                    occupation = transaction_details["occupation"]
                    date_of_birth = transaction_details["date_of_birth"]

                    new_afa_reg = models.AFARegistration.objects.create(
                        user=user,
                        phone_number=phone_number,
                        gh_card_number=gh_card_number,
                        name=name,
                        occupation=occupation,
                        reference=reference,
                        date_of_birth=date_of_birth
                    )
                    new_afa_reg.save()
                    return JsonResponse({'status': "Your transaction will be completed shortly"}, status=200)
                elif transaction_channel == "topup":
                    amount = transaction_details["topup_amount"]

                    user.wallet += float(amount)
                    user.save()

                    new_topup = models.TopUpRequestt.objects.create(
                        user=user,
                        reference=reference,
                        amount=amount,
                        status=True,
                    )
                    new_topup.save()
                    return JsonResponse({'status': "Wallet Credited"}, status=200)
                else:
                    print("no type found")
                    return JsonResponse({'message': "No Type Found"}, status=500)
            else:
                print("Transaction was not Successful")
                return JsonResponse({'message': 'Transaction Failed'}, status=200)
        except Exception as e:
            print("Error Processing hubtel webhook:", str(e))
            return JsonResponse({'status': 'error'}, status=500)
    else:
        print("not post")
        return JsonResponse({'message': 'Not Found'}, status=404)


# def populate_custom_users_from_excel(request):
#     # Read the Excel file using pandas
#     if request.method == 'POST':
#         form = UploadFileForm(request.POST, request.FILES)
#         if form.is_valid():
#             excel_file = request.FILES['file']
#
#             # Process the uploaded Excel file
#             df = pd.read_excel(excel_file)
#             counter = 0
#             # Iterate through rows to create CustomUser instances
#             for index, row in df.iterrows():
#                 print(counter)
#                 # Create a CustomUser instance for each row
#                 custom_user = CustomUser.objects.create(
#                     first_name=row['first_name'],
#                     last_name=row['last_name'],
#                     username=str(row['username']),
#                     email=row['email'],
#                     phone=row['phone'],
#                     wallet=float(row['wallet']),
#                     status=str(row['status']),
#                     password1=row['password1'],
#                     password2=row['password2'],
#                     is_superuser=row['is_superuser'],
#                     is_staff=row['is_staff'],
#                     is_active=row['is_active'],
#                     password=row['password']
#                 )
#
#                 custom_user.save()
#
#                 # group_names = row['groups'].split(',')  # Assuming groups are comma-separated
#                 # groups = Group.objects.filter(name__in=group_names)
#                 # custom_user.groups.set(groups)
#                 #
#                 # if row['user_permissions']:
#                 #     permission_ids = [int(pid) for pid in row['user_permissions'].split(',')]
#                 #     permissions = Permission.objects.filter(id__in=permission_ids)
#                 #     custom_user.user_permissions.set(permissions)
#                 print("killed")
#                 counter = counter + 1
#             messages.success(request, 'All done')
#     else:
#         form = UploadFileForm()
#     return render(request, 'layouts/import_users.html', {'form': form})


def delete_custom_users(request):
    CustomUser.objects.all().delete()
    return HttpResponseRedirect('Done')


@login_required(login_url='login')
def voda(request):
    user = models.CustomUser.objects.get(id=request.user.id)
    status = user.status
    form = forms.VodaBundleForm(status)
    reference = helper.ref_generator()
    user_email = request.user.email

    if request.method == "POST":
        payment_reference = request.POST.get("reference")
        amount_paid = request.POST.get("amount")
        new_payment = models.Payment.objects.create(
            user=request.user,
            reference=payment_reference,
            amount=amount_paid,
            transaction_date=datetime.now(),
            transaction_status="Pending"
        )
        new_payment.save()
        phone_number = request.POST.get("phone")
        offer = request.POST.get("amount")
        if user.status == "User":
            bundle = models.VodaBundlePrice.objects.get(price=float(offer)).bundle_volume
        elif user.status == "Agent":
            bundle = models.AgentVodaBundlePrice.objects.get(price=float(offer)).bundle_volume
        elif user.status == "Super Agent":
            bundle = models.SuperAgentVodaBundlePrice.objects.get(price=float(offer)).bundle_volume
        else:
            bundle = models.VodaBundlePrice.objects.get(price=float(offer)).bundle_volume

        print(phone_number)
        new_mtn_transaction = models.VodafoneTransaction.objects.create(
            user=request.user,
            bundle_number=phone_number,
            offer=f"{bundle}MB",
            reference=payment_reference,
        )
        new_mtn_transaction.save()
        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    user = models.CustomUser.objects.get(id=request.user.id)
    # phone_num = user.phone
    # mtn_dict = {}
    #
    # if user.status == "Agent":
    #     mtn_offer = models.AgentMTNBundlePrice.objects.all()
    # else:
    #     mtn_offer = models.MTNBundlePrice.objects.all()
    # for offer in mtn_offer:
    #     mtn_dict[str(offer)] = offer.bundle_volume
    context = {'form': form,
               "ref": reference, "email": user_email, "wallet": 0 if user.wallet is None else user.wallet}
    return render(request, "layouts/services/voda.html", context=context)


@login_required(login_url='login')
def voda_pay_with_wallet(request):
    if request.method == "POST":
        user = models.CustomUser.objects.get(id=request.user.id)
        phone_number = request.POST.get("phone")
        amount = request.POST.get("amount")
        reference = request.POST.get("reference")

        if user.wallet is None or user.wallet <= 0 or user.wallet < float(amount):
            return JsonResponse(
                {'status': 'Your wallet balance is low. Contact the admin to recharge.'})

        if user.status == "Agent":
            bundle = models.AgentVodaBundlePrice.objects.get(price=float(amount)).bundle_volume
        elif user.status == "Super Agent":
            bundle = models.SuperAgentVodaBundlePrice.objects.get(price=float(amount)).bundle_volume
        else:
            bundle = models.VodaBundlePrice.objects.get(price=float(amount)).bundle_volume

        user.wallet -= float(amount)
        user.save()

        new_voda_transaction = models.VodafoneTransaction.objects.create(
            user=request.user,
            bundle_number=phone_number,
            offer=f"{bundle}MB",
            reference=reference,
        )

        if _api_enabled(geosams.NETWORK_TELECEL):
            msg, rejected = _submit_to_geosams(
                new_voda_transaction, geosams.NETWORK_TELECEL, phone_number, bundle, reference
            )
            if rejected:
                user.wallet += float(amount)
                user.save()
                return JsonResponse({'status': msg, 'icon': 'error'})
            return JsonResponse({'status': msg, 'icon': 'success'})

        return JsonResponse({'status': "Your transaction will be completed shortly", 'icon': 'success'})
    return redirect('voda')


@login_required(login_url='login')
def voda_history(request):
    user_transactions = models.VodafoneTransaction.objects.filter(user=request.user).order_by(
        'transaction_date').reverse()[:200]
    header = "Vodafone Transactions"
    net = "voda"
    context = {'txns': user_transactions, "header": header, "net": net}
    return render(request, "layouts/history.html", context=context)


@login_required(login_url='login')
def voda_mark_as_sent(request, pk):
    if request.user.is_staff and request.user.is_superuser:
        txn = models.VodafoneTransaction.objects.filter(id=pk).first()
        print(txn)
        txn.transaction_status = "Completed"
        txn.save()

        sms_url = 'https://webapp.usmsgh.com/api/sms/send'
        sms_message = f"Your Vodafone transaction has been completed. {txn.bundle_number} has been credited with {txn.offer}.\nTransaction Reference: {txn.reference}"

        sms_body = {
            'recipient': f"233{txn.user.phone}",
            'sender_id': 'Geosams',
            'message': sms_message
        }

        # response = requests.request('POST', url=sms_url, params=sms_body, headers=sms_headers)
        # print(response.text)

        messages.success(request, f"Transaction Completed")
        return redirect('voda_admin')


@login_required(login_url='login')
def admin_voda_history(request):
    if request.user.is_staff and request.user.is_superuser:
        all_txns = models.VodafoneTransaction.objects.filter().order_by('-transaction_date')[
                   :800]
        context = {'txns': all_txns}
        return render(request, "layouts/services/voda_admin.html", context=context)
    else:
        messages.error(request, "Access Denied")
        return redirect('voda_admin')


@csrf_exempt
def momo_webhook_receiver(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    secret = request.headers.get("X-Secret-Key")
    if MACRODROID_SECRET is None or secret != MACRODROID_SECRET:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    sms_body = data.get("sms_body", "")
    sender = data.get("sender", "")
    received_at = data.get("timestamp", "")

    try:
        txn_id, amount = parse_momo_sms(sms_body)

        if not txn_id:
            models.MobileMoneyAlert.objects.create(
                raw_sms_body=sms_body,
                sender_address=sender,
                received_at_phone=received_at,
                status="Ignored",
            )
            return JsonResponse({"status": "ignored", "reason": "No ID found"})

        with db_transaction.atomic():
            alert, created = models.MobileMoneyAlert.objects.get_or_create(
                transaction_id=txn_id,
                defaults={
                    "raw_sms_body": sms_body,
                    "sender_address": sender,
                    "received_at_phone": received_at,
                    "amount": Decimal(str(amount)),
                    "status": "Unclaimed",
                },
            )
            if not created:
                return JsonResponse({"status": "duplicate", "message": "Already received"})

        return JsonResponse({"status": "success", "id": txn_id})

    except Exception as e:
        logger.exception("MoMo webhook error")
        return JsonResponse({"error": str(e)}, status=500)


@login_required(login_url='login')
def claim_topup(request, reference):
    topup_req = get_object_or_404(
        models.TopUpRequestt, reference=reference, user=request.user
    )
    admin = models.AdminInfo.objects.filter().first()

    if request.method == "POST":
        txn_id = request.POST.get("transaction_id", "").strip()
        if not txn_id:
            messages.error(request, "Please enter the Transaction ID from your SMS.")
            return redirect("claim_topup", reference=reference)

        try:
            with db_transaction.atomic():
                topup_req = models.TopUpRequestt.objects.select_for_update().get(
                    id=topup_req.id
                )
                if topup_req.status:
                    messages.info(request, "This top-up request has already been completed.")
                    return redirect("home")

                alert = (
                    models.MobileMoneyAlert.objects.select_for_update()
                    .filter(transaction_id=txn_id)
                    .first()
                )

                if not alert:
                    messages.error(request, "Transaction ID not found. If you just paid, wait a moment and try again.")
                    return redirect("claim_topup", reference=reference)
                if alert.status == "Claimed":
                    messages.error(request, "This Transaction ID has already been used.")
                    return redirect("claim_topup", reference=reference)
                if alert.status in ("Ignored", "Expired"):
                    messages.error(request, "This transaction data is invalid or expired.")
                    return redirect("claim_topup", reference=reference)

                if timezone.now() - alert.created_at > timedelta(hours=24):
                    alert.status = "Expired"
                    alert.save()
                    messages.error(
                        request,
                        "This transaction has expired (older than 24 hours). Contact support.",
                    )
                    return redirect("claim_topup", reference=reference)

                amount_paid = Decimal(str(alert.amount))
                expected_price = Decimal(str(topup_req.amount))
                if amount_paid != expected_price:
                    messages.error(
                        request,
                        f"Amount mismatch. You requested GHS {expected_price}, "
                        f"but the SMS shows GHS {amount_paid}. Contact admin if this is wrong.",
                    )
                    return redirect("claim_topup", reference=reference)

                alert.status = "Claimed"
                alert.claimed_by = request.user
                alert.claimed_at = timezone.now()
                alert.save()

                topup_req.status = True
                topup_req.credited_at = timezone.now()
                topup_req.save()

                user = models.CustomUser.objects.select_for_update().get(id=request.user.id)
                user.wallet = (user.wallet or 0.0) + float(alert.amount)
                user.save()

            messages.success(
                request,
                f"Success! GHS {alert.amount} has been added to your wallet.",
            )
            return redirect("home")

        except Exception:
            logger.exception("claim_topup failed for reference=%s", reference)
            messages.error(request, "System error processing claim. Please try again or contact support.")
            return redirect("claim_topup", reference=reference)

    context = {
        "topup_req": topup_req,
        "reference": reference,
        "business_momo_number": f"0{admin.momo_numberr}" if admin and admin.momo_numberr else "",
        "business_momo_name": admin.name if admin else "",
        "channel": admin.payment_channell if admin else "",
    }
    return render(request, "layouts/services/claim_topup.html", context=context)


