# auth_views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
import re


def logout_view(request):
    """Gestisce il logout dell'utente"""
    logout(request)
    messages.success(request, "Hai effettuato il logout con successo.")
    return redirect('homepage')


@csrf_protect
@require_http_methods(["GET", "POST"])
def login_view(request):
    """Login con errori contestuali come l'app mobile."""
    User = get_user_model()
    context = {
        'error_type': None,
        'error_message': '',
        'username': '',
        'next': request.GET.get('next', request.POST.get('next', '')),
    }

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        context['username'] = username

        if not username or not password:
            context['error_type'] = 'empty_fields'
            context['error_message'] = 'Inserisci username e password.'
        else:
            # Check if user exists
            user_exists = User.objects.filter(username__iexact=username).exists()
            if not user_exists:
                # Also check by email
                user_exists = User.objects.filter(email__iexact=username).exists()

            if not user_exists:
                context['error_type'] = 'user_not_found'
                context['error_message'] = 'Nessun account trovato con questo username.'
            else:
                # Try to authenticate - support login by email too
                user = authenticate(request, username=username, password=password)
                if user is None:
                    # Try email-based login
                    try:
                        user_obj = User.objects.get(email__iexact=username)
                        user = authenticate(request, username=user_obj.username, password=password)
                    except User.DoesNotExist:
                        pass

                if user is not None:
                    login(request, user)
                    next_url = request.POST.get('next', '')
                    return redirect(next_url if next_url else 'dashboard')
                else:
                    context['error_type'] = 'wrong_password'
                    context['error_message'] = 'Password non corretta.'

    return render(request, 'auth/login.html', context)


@csrf_protect
@require_http_methods(["GET", "POST"])
def register_view(request):
    """Registrazione con campi espliciti come l'app mobile."""
    User = get_user_model()
    context = {
        'errors': {},
        'username': '',
        'email': '',
        'privacy_accepted': False,
    }

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        privacy = request.POST.get('privacy_accepted') == 'on'

        context['username'] = username
        context['email'] = email
        context['privacy_accepted'] = privacy

        errors = {}

        # Validate username
        if not username:
            errors['username'] = 'Lo username è obbligatorio.'
        elif len(username) < 3:
            errors['username'] = 'Lo username deve avere almeno 3 caratteri.'
        elif User.objects.filter(username__iexact=username).exists():
            errors['username'] = 'Questo username è già in uso.'

        # Validate email
        if not email:
            errors['email'] = "L'email è obbligatoria."
        elif not re.match(r'^[\w\.\-\+]+@([\w\-]+\.)+[\w\-]{2,}$', email):
            errors['email'] = 'Inserisci un indirizzo email valido.'
        elif User.objects.filter(email__iexact=email).exists():
            errors['email'] = 'Questa email è già registrata.'

        # Validate password
        if not password:
            errors['password'] = 'La password è obbligatoria.'
        elif len(password) < 8:
            errors['password'] = 'La password deve avere almeno 8 caratteri.'
        else:
            try:
                validate_password(password)
            except DjangoValidationError as e:
                errors['password'] = e.messages[0]

        # Validate confirm password
        if password and password != confirm_password:
            errors['confirm_password'] = 'Le password non corrispondono.'

        # Validate privacy
        if not privacy:
            errors['privacy'] = 'Devi accettare l\'informativa sulla privacy.'

        if errors:
            context['errors'] = errors
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            login(request, user)
            messages.success(request, f"Benvenuto, {user.username}! Il tuo account è stato creato con successo.")
            return redirect('dashboard')

    return render(request, 'auth/register.html', context)


@csrf_protect
@require_http_methods(["GET", "POST"])
def forgot_password_view(request):
    """Pagina web per richiedere il reset della password (come l'app mobile)."""
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail
    from django.conf import settings

    User = get_user_model()
    context = {
        'state': 'form',  # form | success | error
        'email': '',
        'error_message': '',
    }

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        context['email'] = email

        if not email:
            context['error_message'] = "L'email è obbligatoria."
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            context['error_message'] = 'Inserisci un indirizzo email valido.'
        else:
            # Always show success to avoid revealing which emails exist
            context['state'] = 'success'

            try:
                user = User.objects.get(email__iexact=email)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_url = request.build_absolute_uri(f'/reset-password/{uid}/{token}/')

                send_mail(
                    subject='Reimposta la tua password – Apiary',
                    message=(
                        f"Ciao {user.username},\n\n"
                        f"Hai richiesto di reimpostare la password del tuo account Apiary.\n\n"
                        f"Clicca sul link seguente per scegliere una nuova password:\n{reset_url}\n\n"
                        f"Il link è valido per 24 ore. Se non hai richiesto il reset, ignora questa email.\n\n"
                        f"– Il team di Apiary"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except User.DoesNotExist:
                pass  # Don't reveal if email exists

    return render(request, 'auth/forgot_password.html', context)


def password_reset_confirm_web(request, uidb64, token):
    """Pagina web per scegliere la nuova password dopo aver cliccato il link nell'email."""
    User = get_user_model()

    # Valida uid e token
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        user = None

    token_valid = user is not None and default_token_generator.check_token(user, token)

    if not token_valid:
        return render(request, 'auth/reset_password.html', {'invalid': True})

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        errors = []

        if not new_password:
            errors.append('La nuova password è obbligatoria.')
        elif new_password != confirm_password:
            errors.append('Le password non corrispondono.')
        else:
            try:
                validate_password(new_password, user)
            except DjangoValidationError as e:
                errors.extend(e.messages)

        if errors:
            return render(request, 'auth/reset_password.html', {'errors': errors})

        user.set_password(new_password)
        user.save()
        return render(request, 'auth/reset_password.html', {'success': True})

    return render(request, 'auth/reset_password.html', {})


def delete_data_view(request):
    """Pagina pubblica per richiedere l'eliminazione dei dati utente.
    Se autenticato può eliminare tutti i dati di apicoltura mantenendo l'account."""
    if request.method == 'POST' and request.user.is_authenticated:
        from django.contrib.auth import authenticate as auth_authenticate
        from core.models import Apiario, Attrezzatura, Cliente, Pagamento, Maturatore, ContenitoreStoccaggio
        password = request.POST.get('password', '')
        user = auth_authenticate(username=request.user.username, password=password)
        if user is not None:
            Apiario.objects.filter(proprietario=user).delete()
            Attrezzatura.objects.filter(proprietario=user).delete()
            Cliente.objects.filter(utente=user).delete()
            Pagamento.objects.filter(utente=user).delete()
            Maturatore.objects.filter(utente=user).delete()
            ContenitoreStoccaggio.objects.filter(utente=user).delete()
            messages.success(request, 'Tutti i tuoi dati sono stati eliminati. L\'account è ancora attivo.')
            return redirect('delete_data')
        else:
            messages.error(request, 'Password non corretta. Riprova.')
            return redirect('delete_data')
    return render(request, 'auth/delete_data.html')


def delete_account_view(request):
    """Pagina pubblica per richiedere l'eliminazione dell'account.
    Se l'utente è autenticato può eliminare direttamente inserendo la password."""
    if request.method == 'POST' and request.user.is_authenticated:
        password = request.POST.get('password', '')
        user = authenticate(username=request.user.username, password=password)
        if user is not None:
            logout(request)
            user.delete()
            messages.success(request, 'Il tuo account è stato eliminato definitivamente.')
            return redirect('homepage')
        else:
            messages.error(request, 'Password non corretta. Riprova.')
            return redirect('delete_account')
    return render(request, 'auth/delete_account.html')
