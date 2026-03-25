# auth_views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

def logout_view(request):
    """Gestisce il logout dell'utente"""
    logout(request)
    messages.success(request, "Hai effettuato il logout con successo.")
    return redirect('homepage')

def register_view(request):
    """Gestisce la registrazione di un nuovo utente"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Benvenuto, {user.username}! Il tuo account è stato creato con successo.")
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'auth/register.html', {'form': form})


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