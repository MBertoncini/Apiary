# core/notifications.py
"""
Utility functions per creare notifiche nel sistema Apiary.
"""
from django.urls import reverse


def crea_notifica(utente, tipo, titolo, messaggio, mittente=None, link=None, priorita='media'):
    """Crea una notifica per un utente. Import lazy per evitare circular imports."""
    from .models import Notifica
    return Notifica.objects.create(
        utente=utente,
        tipo=tipo,
        titolo=titolo,
        messaggio=messaggio,
        mittente=mittente,
        link=link,
        priorita=priorita,
    )


def notifica_invito_gruppo(invito):
    """Notifica all'utente invitato (se esiste un account con quella email)."""
    from django.contrib.auth.models import User
    try:
        utente = User.objects.get(email=invito.email)
    except User.DoesNotExist:
        return  # Utente non registrato, niente notifica in-app

    link = reverse('gestione_gruppi')
    crea_notifica(
        utente=utente,
        tipo='invito_gruppo',
        titolo=f"Invito al gruppo «{invito.gruppo.nome}»",
        messaggio=(
            f"{invito.invitato_da.get_full_name() or invito.invitato_da.username} "
            f"ti ha invitato a far parte del gruppo «{invito.gruppo.nome}» "
            f"con ruolo {invito.get_ruolo_proposto_display()}."
        ),
        mittente=invito.invitato_da,
        link=link,
        priorita='alta',
    )


def notifica_invito_accettato(invito):
    """Notifica all'invitante che l'invito è stato accettato."""
    try:
        from django.urls import reverse
        link = reverse('dettaglio_gruppo', kwargs={'gruppo_id': invito.gruppo.id})
    except Exception:
        link = None

    crea_notifica(
        utente=invito.invitato_da,
        tipo='invito_accettato',
        titolo=f"Invito accettato — {invito.gruppo.nome}",
        messaggio=(
            f"Il tuo invito per il gruppo «{invito.gruppo.nome}» è stato accettato."
        ),
        link=link,
        priorita='media',
    )


def notifica_invito_rifiutato(invito):
    """Notifica all'invitante che l'invito è stato rifiutato."""
    try:
        link = reverse('dettaglio_gruppo', kwargs={'gruppo_id': invito.gruppo.id})
    except Exception:
        link = None

    crea_notifica(
        utente=invito.invitato_da,
        tipo='invito_rifiutato',
        titolo=f"Invito rifiutato — {invito.gruppo.nome}",
        messaggio=(
            f"L'utente ha rifiutato il tuo invito per il gruppo «{invito.gruppo.nome}»."
        ),
        link=link,
        priorita='bassa',
    )


def notifica_membro_aggiunto(membro):
    """Notifica a tutti gli admin del gruppo che un nuovo membro è stato aggiunto."""
    from .models import MembroGruppo
    admin_ids = MembroGruppo.objects.filter(
        gruppo=membro.gruppo, ruolo='admin'
    ).exclude(utente=membro.utente).values_list('utente', flat=True)

    from django.contrib.auth.models import User
    for admin in User.objects.filter(id__in=admin_ids):
        try:
            link = reverse('dettaglio_gruppo', kwargs={'gruppo_id': membro.gruppo.id})
        except Exception:
            link = None
        crea_notifica(
            utente=admin,
            tipo='membro_aggiunto',
            titolo=f"Nuovo membro in «{membro.gruppo.nome}»",
            messaggio=(
                f"{membro.utente.get_full_name() or membro.utente.username} "
                f"si è unito al gruppo «{membro.gruppo.nome}» come {membro.get_ruolo_display()}."
            ),
            link=link,
            priorita='bassa',
        )


def notifica_fioritura_vicina(fioritura, apiari_vicini):
    """
    Notifica ai proprietari degli apiari vicini di una nuova fioritura.
    apiari_vicini: queryset di Apiario con i relativi proprietari.
    """
    try:
        link = reverse('calendario')
    except Exception:
        link = None

    notificati = set()
    for apiario in apiari_vicini:
        proprietario = apiario.proprietario
        if proprietario.id in notificati:
            continue
        notificati.add(proprietario.id)
        crea_notifica(
            utente=proprietario,
            tipo='fioritura_vicina',
            titolo=f"Fioritura vicina: {fioritura.nome}",
            messaggio=(
                f"È stata segnalata una fioritura di «{fioritura.nome}» "
                f"vicino al tuo apiario «{apiario.nome}». "
                f"Periodo: {fioritura.data_inizio.strftime('%d/%m/%Y')} — "
                f"{fioritura.data_fine.strftime('%d/%m/%Y') if fioritura.data_fine else 'in corso'}."
            ),
            link=link,
            priorita='media',
        )
