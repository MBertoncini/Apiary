# core/signals.py
"""
Signal handlers per il modulo core.

Contenuto:
  - backfill leggero del dataset MeteoGiornaliero quando un Apiario viene creato
    con coordinate (o quando le coordinate vengono settate per la prima volta).
    Il backfill completo è demandato al cron quotidiano
    `aggiorna_meteo_giornaliero` o al management command
    `backfill_meteo_giornaliero`.
  - fan-out delle AdminBroadcast pubblicate verso le Notifica per utente.
  - creazione/sincronizzazione del Pagamento collegato a una SpesaAttrezzatura.
  - riallineamento della spesa di acquisto al prezzo dell'Attrezzatura.
  - coerenza fra Colonia e contenitore (Arnia/Nucleo): chiusura della colonia
    quando il suo box viene eliminato e riallineamento dell'apiario quando il
    box cambia apiario.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from decimal import Decimal

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.html import strip_tags

from .models import (
    Apiario, AdminBroadcast, Arnia, Attrezzatura, Colonia, Notifica, Nucleo,
    Pagamento, SpesaAttrezzatura,
)
from .storia_regine import chiudi_storia_colonia


logger = logging.getLogger(__name__)

# Numero di giorni di backfill "leggero" eseguito on-create. Il resto verrà
# riempito gradualmente dal cron quotidiano.
ON_CREATE_BACKFILL_DAYS = 30


def _backfill_async(apiario_id: int, days: int) -> None:
    """Esegue il backfill in un thread daemon per non bloccare la response.

    L'import di `aggiorna_meteo_apiario` è ritardato perché tocca cache/HTTP.
    """
    try:
        from .meteo_archive_utils import aggiorna_meteo_apiario
        from .models import Apiario as _Apiario

        apiario = _Apiario.objects.filter(pk=apiario_id).first()
        if not apiario or not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
            return

        oggi = date.today()
        end = oggi - timedelta(days=1)
        start = max(
            end - timedelta(days=days - 1),
            apiario.data_creazione.date() if apiario.data_creazione else end - timedelta(days=days - 1),
        )
        aggiorna_meteo_apiario(apiario, start, end)
    except Exception as e:
        logger.warning("Backfill meteo on-create fallito per apiario %s: %s", apiario_id, e)


@receiver(post_save, sender=Apiario)
def apiario_post_save_backfill_meteo(sender, instance, created, **kwargs):
    """Lancia il backfill leggero quando un apiario diventa "monitorabile".

    Si scatena se:
      - l'apiario è appena stato creato con coordinate e monitoraggio_meteo attivo
      - oppure (best effort) un apiario già esistente diventa monitorabile
        — tracciato in modo grossolano controllando se ci sono già righe
        MeteoGiornaliero; se no, partiamo.
    """
    if not instance.has_coordinates() or not instance.monitoraggio_meteo:
        return

    if not created:
        # Su update: facciamo backfill solo se non ci sono già righe per
        # questo apiario (evita lavoro inutile a ogni save).
        from .models import MeteoGiornaliero
        if MeteoGiornaliero.objects.filter(apiario=instance).exists():
            return

    t = threading.Thread(
        target=_backfill_async,
        args=(instance.pk, ON_CREATE_BACKFILL_DAYS),
        daemon=True,
    )
    t.start()


# ── Fan-out broadcast admin → una Notifica per ogni utente attivo ───────────

def _plain_excerpt(html: str, max_len: int = 500) -> str:
    """Estrae un testo plain dall'HTML del corpo, troncato.

    Serve come `messaggio` plain delle Notifica generate dalla broadcast: il
    centro notifiche dell'app può mostrare l'HTML pieno via `messaggio_html`,
    ma il fallback (lista, push) usa il plain.
    """
    text = strip_tags(html or '').strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + '…'
    return text


@receiver(post_save, sender=AdminBroadcast)
def broadcast_post_save_fanout(sender, instance, created, **kwargs):
    """Quando una AdminBroadcast viene marcata pubblicata per la prima volta,
    crea una Notifica per ciascun utente attivo. Idempotente: una volta che
    `data_pubblicazione` è stato impostato, il fan-out non viene ripetuto.
    """
    if not instance.pubblicata:
        return
    if instance.data_pubblicazione is not None:
        return  # già fan-outata

    from django.contrib.auth import get_user_model
    UserModel = get_user_model()

    user_ids = list(
        UserModel.objects.filter(is_active=True).values_list('id', flat=True)
    )
    if not user_ids:
        return

    plain = _plain_excerpt(instance.body_html)
    notifiche = [
        Notifica(
            utente_id=u_id,
            tipo='broadcast',
            titolo=instance.titolo,
            messaggio=plain,
            messaggio_html=instance.body_html or '',
            immagine_url=instance.immagine_url or None,
            link_route=instance.link_route or '',
            link_param=instance.link_param or '',
            priorita=instance.priorita,
            broadcast=instance,
            mittente=instance.creata_da,
        )
        for u_id in user_ids
    ]
    Notifica.objects.bulk_create(notifiche, batch_size=500)

    # Aggiorna senza ritriggerare il signal (.update() bypassa save())
    from django.utils import timezone as tz
    AdminBroadcast.objects.filter(pk=instance.pk).update(
        data_pubblicazione=tz.now(),
        destinatari_count=len(user_ids),
    )
    logger.info(
        "AdminBroadcast %s pubblicata → fan-out a %s utenti",
        instance.pk, len(user_ids),
    )


# ── SpesaAttrezzatura → Pagamento collegato ────────────────────────────────
#
# Il Pagamento serve al calcolo delle quote di gruppo (chi ha sborsato cosa).
# Prima veniva creato a mano da ogni chiamante (view web, client Flutter), con
# due conseguenze: l'importo finiva due volte nelle uscite del bilancio e il
# pagamento sopravviveva alla cancellazione della spesa/attrezzatura, lasciando
# un'uscita fantasma. Ora nasce qui, collegato via `spesa_attrezzatura`, così:
#   - il bilancio economico lo esclude (è già contato come SpesaAttrezzatura);
#   - la FK è CASCADE, quindi muore insieme alla spesa e all'attrezzatura.

def descrizione_pagamento_spesa(spesa: SpesaAttrezzatura) -> str:
    """Descrizione leggibile del pagamento generato da una spesa attrezzatura."""
    nome = spesa.attrezzatura.nome if spesa.attrezzatura_id else 'attrezzatura'
    if spesa.tipo == 'acquisto':
        testo = f"Acquisto attrezzatura: {nome}"
    elif spesa.tipo == 'manutenzione':
        testo = f"Manutenzione attrezzatura: {nome} - {spesa.descrizione}"
    else:
        testo = f"Spesa attrezzatura ({spesa.get_tipo_display()}): {nome} - {spesa.descrizione}"
    return testo[:200]  # Pagamento.descrizione è un CharField(max_length=200)


@receiver(post_save, sender=SpesaAttrezzatura)
def spesa_attrezzatura_post_save_pagamento(sender, instance, created, **kwargs):
    """Crea (o riallinea) il Pagamento collegato alla spesa attrezzatura.

    Chi paga è `pagato_da` se valorizzato — è il membro che ha effettivamente
    sborsato il denaro — altrimenti chi ha registrato la spesa.
    """
    # `importo` può arrivare come str o float da chiamanti che non passano dal
    # serializer (script, management command, shell): normalizziamo a Decimal
    # prima di confrontarlo, altrimenti il salvataggio esplode.
    try:
        importo = Decimal(str(instance.importo)) if instance.importo is not None else None
    except (ArithmeticError, TypeError, ValueError):
        importo = None

    if importo is None or importo <= 0:
        # Spesa a importo nullo: nessun pagamento da registrare. Se ne esisteva
        # uno da un salvataggio precedente lo rimuoviamo per non lasciare
        # residui nelle quote di gruppo.
        Pagamento.objects.filter(spesa_attrezzatura=instance).delete()
        return

    pagante_id = instance.pagato_da_id or instance.utente_id
    if not pagante_id:
        return

    esistenti = Pagamento.objects.filter(spesa_attrezzatura=instance)
    if esistenti.exists():
        if not created:
            esistenti.update(
                utente_id=pagante_id,
                importo=importo,
                data=instance.data,
                descrizione=descrizione_pagamento_spesa(instance),
                gruppo_id=instance.gruppo_id,
            )
        return

    Pagamento.objects.create(
        utente_id=pagante_id,
        importo=importo,
        data=instance.data,
        descrizione=descrizione_pagamento_spesa(instance),
        gruppo_id=instance.gruppo_id,
        spesa_attrezzatura=instance,
    )



# ── Spesa di acquisto ↔ prezzo dell'attrezzatura ─────────────────────────────
# Creando un'attrezzatura con un prezzo, API e web registrano una spesa
# "Acquisto: <nome>". Modificando poi il prezzo quella spesa restava com'era:
# azzerarlo (il modo naturale, per l'utente, di togliere il costo) lasciava
# l'uscita nel bilancio. Riallineiamo solo la spesa automatica: le spese
# aggiunte a mano restano dell'utente.

PREFISSO_SPESA_ACQUISTO = 'Acquisto: '


def allinea_spesa_acquisto(attrezzatura: Attrezzatura, apply: bool = True) -> str | None:
    """Porta la spesa di acquisto automatica al prezzo attuale dell'attrezzatura.

    Prezzo nullo o zero → la spesa (e, in cascata, il suo Pagamento) sparisce;
    prezzo diverso → la spesa lo segue e il signal della spesa riallinea il
    Pagamento. Non crea spese nuove: se l'utente l'aveva cancellata, resta
    cancellata. Restituisce una descrizione della modifica, o None se non c'era
    nulla da fare.
    """
    spesa = (
        SpesaAttrezzatura.objects
        .filter(attrezzatura=attrezzatura, tipo='acquisto',
                descrizione__startswith=PREFISSO_SPESA_ACQUISTO)
        .order_by('id').first()
    )
    if spesa is None:
        return None

    prezzo = attrezzatura.prezzo_acquisto
    if not prezzo or prezzo <= 0:
        if apply:
            spesa.delete()
        return f"elimino spesa #{spesa.id} di € {spesa.importo} (prezzo ora {prezzo})"

    if spesa.importo == prezzo:
        return None
    vecchio = spesa.importo
    if apply:
        spesa.importo = prezzo
        spesa.save(update_fields=['importo'])
    return f"spesa #{spesa.id}: € {vecchio} -> € {prezzo}"


@receiver(post_save, sender=Attrezzatura)
def attrezzatura_post_save_allinea_spesa(sender, instance, created, raw=False, **kwargs):
    if created or raw:
        return
    allinea_spesa_acquisto(instance)

# ── Colonia ↔ contenitore ────────────────────────────────────────────────────
# `Colonia.arnia` / `Colonia.nucleo` sono SET_NULL e `Colonia.apiario` è un
# campo denormalizzato: senza questi handler, eliminare un'arnia lasciava la sua
# colonia "attiva" ma senza box (un'arnia fantasma negli elenchi, con la sua
# regina ancora contata nelle statistiche), e spostare un'arnia in un altro
# apiario lasciava la colonia nel vecchio, dove compariva come doppione.

def _campo_contenitore(sender) -> str:
    return 'arnia' if sender is Arnia else 'nucleo'


@receiver(pre_delete, sender=Arnia)
@receiver(pre_delete, sender=Nucleo)
def contenitore_pre_delete_chiudi_colonia(sender, instance, **kwargs):
    """Chiude come 'eliminata' la colonia attiva del box che sta per sparire."""
    etichetta = 'Arnia' if sender is Arnia else 'Nucleo'
    for colonia in Colonia.objects.filter(
        **{_campo_contenitore(sender): instance},
        stato='attiva',
        data_fine__isnull=True,
    ):
        colonia.stato = 'eliminata'
        colonia.data_fine = timezone.localdate()
        colonia.motivo_fine = f"{etichetta} {instance.numero} eliminata"
        colonia.save(update_fields=['stato', 'data_fine', 'motivo_fine'])
        chiudi_storia_colonia(colonia)


@receiver(post_save, sender=Arnia)
@receiver(post_save, sender=Nucleo)
def contenitore_post_save_allinea_apiario(sender, instance, created, **kwargs):
    """Porta la colonia attiva nell'apiario in cui ora si trova il suo box."""
    if created:
        return
    Colonia.objects.filter(
        **{_campo_contenitore(sender): instance},
        stato='attiva',
        data_fine__isnull=True,
    ).exclude(apiario_id=instance.apiario_id).update(apiario_id=instance.apiario_id)
