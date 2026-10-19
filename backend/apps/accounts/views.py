import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.http import JsonResponse

from .models import CustomUser, DeviceAuthKey
from .forms import RegisterForm, LoginForm, PasswordResetRequestForm, SetNewPasswordForm
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server

logger = logging.getLogger(__name__)

def apply_persistent_auth(request, response, user, remember=True, days=90):
    """
    Caches authentication for 90 days.
    Sets 90-day session expiry and attaches a persistent 90-day DeviceAuthKey cookie.
    """
    cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
    if remember:
        request.session.set_expiry(days * 24 * 3600)
        device_key = DeviceAuthKey.issue_key(user, request=request, days=days)
        response.set_cookie(
            cookie_name,
            device_key.key,
            max_age=days * 24 * 3600,
            httponly=True,
            samesite='Lax',
            secure=request.is_secure()
        )
        logger.info(f"Issued 90-day device key for {user.username}")
    else:
        request.session.set_expiry(0)
    return response

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    email_already_exists = False
    existing_email = ''

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        ref_code = request.GET.get('ref') or request.POST.get('ref')
        
        if form.is_valid():
            user = form.save(commit=False)
            if ref_code:
                try:
                    referrer = CustomUser.objects.get(referral_code=ref_code)
                    user.referred_by = referrer
                    # Bonus for referrer
                    referrer.balance += 10
                    referrer.save()
                except CustomUser.DoesNotExist:
                    pass
            user.save()

            # Ensure default active VPN key is created
            try:
                server = get_or_create_default_server()
                VPNKey.objects.get_or_create(user=user, server=server)
            except Exception as e:
                logger.error(f"Error provisioning initial VPN key: {e}")

            login(request, user)
            messages.success(request, f"Добро пожаловать, {user.username}! Вам начислен пробный баланс.")
            response = redirect('dashboard')
            return apply_persistent_auth(request, response, user, remember=True, days=90)
        else:
            if 'email' in form.errors:
                for err in form.errors['email'].as_data():
                    if err.code == 'email_exists':
                        email_already_exists = True
                        existing_email = request.POST.get('email', '')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'email_already_exists': email_already_exists,
        'existing_email': existing_email
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            remember_me = form.cleaned_data.get('remember_me', True)
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            response = redirect(next_url)
            return apply_persistent_auth(request, response, user, remember=remember_me, days=90)
    else:
        form = LoginForm(initial={'remember_me': True})

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
    device_key_val = request.COOKIES.get(cookie_name)
    if device_key_val:
        DeviceAuthKey.objects.filter(key=device_key_val).delete()
    logout(request)
    response = redirect('login')
    response.delete_cookie(cookie_name)
    response.delete_cookie(getattr(settings, 'SESSION_COOKIE_NAME', 'vpn_sessionid'))
    return response


def password_reset_request_view(request):
    initial_email = request.GET.get('email', '')
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            users = CustomUser.objects.filter(email__iexact=email)
            if users.exists():
                user = users.first()
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                reset_link = f"{settings.SITE_URL}/auth/password-reset-confirm/{uid}/{token}/"
                
                subject = "Восстановление пароля — VPN Live Dev"
                message_html = render_to_string('accounts/emails/password_reset_email.html', {
                    'user': user,
                    'reset_link': reset_link,
                    'domain': settings.DOMAIN,
                })
                
                try:
                    send_mail(
                        subject=subject,
                        message=f"Перейдите по ссылке для сброса пароля: {reset_link}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        html_message=message_html,
                        fail_silently=False
                    )
                except Exception as e:
                    logger.error(f"Error sending email: {e}")
            
            # Show the same confirmation screen regardless of user existence (security best practice)
            return redirect('password_reset_done')
    else:
        form = PasswordResetRequestForm(initial={'email': initial_email})

    return render(request, 'accounts/password_reset_request.html', {'form': form})


def password_reset_done_view(request):
    return render(request, 'accounts/password_reset_done.html')


def password_reset_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetNewPasswordForm(request.POST)
            if form.is_valid():
                user.set_password(form.cleaned_data['new_password'])
                user.save()
                login(request, user)
                messages.success(request, "Ваш пароль успешно изменен!")
                response = redirect('dashboard')
                return apply_persistent_auth(request, response, user, remember=True, days=90)
        else:
            form = SetNewPasswordForm()
        return render(request, 'accounts/password_reset_confirm.html', {'form': form, 'validlink': True})
    else:
        return render(request, 'accounts/password_reset_confirm.html', {'validlink': False})


@login_required
def dashboard_view(request):
    user = request.user
    
    # Get or create VPN key (preserve selected server)
    key = VPNKey.objects.filter(user=user).first()
    if not key:
        server = get_or_create_default_server()
        key = VPNKey.objects.create(user=user, server=server)
    
    servers = VPNServer.objects.filter(is_active=True).order_by('ping_ms')
    referrals_count = user.referrals.count()
    referral_url = f"{settings.SITE_URL}/auth/register/?ref={user.referral_code}"
    
    return render(request, 'accounts/dashboard.html', {
        'user': user,
        'vpn_key': key,
        'servers': servers,
        'referrals_count': referrals_count,
        'referral_url': referral_url,
    })

