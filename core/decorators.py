# core/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden

from .models import MembroGruppo, Apiario, Gruppo

def richiedi_appartenenza_gruppo(view_func):
    """
    Decorator che verifica che l'utente appartenga al gruppo specificato nella vista.
    La vista deve avere un parametro gruppo_id.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        gruppo_id = kwargs.get('gruppo_id')
        if not gruppo_id:
            messages.error(request, "Gruppo non specificato.")
            return redirect('gestione_gruppi')
        
        # Verifica che l'utente sia membro del gruppo
        if not Gruppo.objects.filter(id=gruppo_id, membri=request.user).exists():
            messages.error(request, "Non hai accesso a questo gruppo.")
            return redirect('gestione_gruppi')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def richiedi_ruolo_admin(view_func):
    """
    Decorator che verifica che l'utente sia un amministratore del gruppo.
    La vista deve avere un parametro gruppo_id.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        gruppo_id = kwargs.get('gruppo_id')
        if not gruppo_id:
            messages.error(request, "Gruppo non specificato.")
            return redirect('gestione_gruppi')
        
        # Verifica che l'utente sia un amministratore del gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo_id=gruppo_id)
            if membro.ruolo != 'admin':
                messages.error(request, "Non hai i permessi necessari. Solo gli amministratori possono accedere a questa funzionalità.")
                return redirect('dettaglio_gruppo', gruppo_id=gruppo_id)
        except MembroGruppo.DoesNotExist:
            messages.error(request, "Non sei membro di questo gruppo.")
            return redirect('gestione_gruppi')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def richiedi_permesso_scrittura(view_func):
    """
    Decorator che verifica che l'utente abbia i permessi di scrittura nel gruppo (admin o editor).
    La vista deve avere un parametro gruppo_id o apiario_id da cui ricavare il gruppo.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        gruppo_id = kwargs.get('gruppo_id')
        
        # Se non abbiamo gruppo_id ma abbiamo apiario_id, otteniamo il gruppo dall'apiario
        if not gruppo_id and 'apiario_id' in kwargs:
            try:
                apiario = Apiario.objects.get(id=kwargs['apiario_id'])
                if apiario.gruppo:
                    gruppo_id = apiario.gruppo.id
                else:
                    # Se l'apiario non ha un gruppo, verifichiamo che l'utente sia il proprietario
                    if apiario.proprietario == request.user:
                        return view_func(request, *args, **kwargs)
                    else:
                        messages.error(request, "Non hai i permessi necessari per modificare questo apiario.")
                        return redirect('visualizza_apiario', apiario_id=apiario.id)
            except Apiario.DoesNotExist:
                messages.error(request, "Apiario non trovato.")
                return redirect('dashboard')
        
        if not gruppo_id:
            messages.error(request, "Gruppo non specificato.")
            return redirect('gestione_gruppi')
        
        # Verifica che l'utente abbia i permessi di scrittura nel gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo_id=gruppo_id)
            if membro.ruolo not in ['admin', 'editor']:
                messages.error(request, "Non hai i permessi necessari per questa operazione. Solo admin ed editor possono modificare le risorse.")
                return redirect('dettaglio_gruppo', gruppo_id=gruppo_id)
        except MembroGruppo.DoesNotExist:
            messages.error(request, "Non sei membro di questo gruppo.")
            return redirect('gestione_gruppi')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def richiedi_proprietario_o_gruppo(view_func):
    """
    Decorator che verifica che l'utente sia il proprietario della risorsa
    o che abbia i permessi appropriati nel gruppo a cui la risorsa è condivisa.
    La vista deve avere un parametro che identifica la risorsa (es. apiario_id).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        apiario_id = kwargs.get('apiario_id')
        if not apiario_id:
            messages.error(request, "Risorsa non specificata.")
            return redirect('dashboard')
        
        try:
            apiario = Apiario.objects.get(id=apiario_id)
            
            # Se l'utente è il proprietario, ha sempre accesso
            if apiario.proprietario == request.user:
                return view_func(request, *args, **kwargs)
            
            # Se l'apiario è condiviso con un gruppo
            if apiario.gruppo and apiario.condiviso_con_gruppo:
                # Verifica che l'utente sia membro del gruppo
                try:
                    membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
                    # Per gli editor e admin, consenti l'accesso completo
                    if membro.ruolo in ['admin', 'editor']:
                        return view_func(request, *args, **kwargs)
                    # Per i visualizzatori, consenti solo l'accesso in lettura
                    elif membro.ruolo == 'viewer' and request.method == 'GET':
                        return view_func(request, *args, **kwargs)
                    else:
                        messages.error(request, "Non hai i permessi necessari per questa operazione nel gruppo.")
                        return redirect('visualizza_apiario', apiario_id=apiario.id)
                except MembroGruppo.DoesNotExist:
                    messages.error(request, "Non sei membro del gruppo che ha accesso a questa risorsa.")
                    return redirect('dashboard')
            else:
                messages.error(request, "Non hai accesso a questa risorsa.")
                return redirect('dashboard')
                
        except Apiario.DoesNotExist:
            messages.error(request, "Risorsa non trovata.")
            return redirect('dashboard')
    
    return _wrapped_view