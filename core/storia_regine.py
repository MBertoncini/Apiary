"""
Apertura e chiusura delle righe di StoriaRegine.

Lo storico è l'unica traccia di una regina che non c'è più: le statistiche
(sostituzioni per motivo, durata media) lo leggono da qui. Le view web lo
aggiornavano già; l'API usata dall'app no: le regine nascevano senza riga di
storico e la sostituzione cancellava la regina, portandosi via in cascata
anche lo storico. Queste funzioni sono idempotenti e vanno chiamate da ogni
percorso che introduce o toglie una regina.
"""
from __future__ import annotations

from datetime import date

from .models import Colonia, Regina, StoriaRegine


def apri_storia(regina: Regina) -> StoriaRegine | None:
    """Garantisce una riga aperta per la regina nella sua colonia attuale."""
    if not regina.colonia_id:
        return None
    aperta = StoriaRegine.objects.filter(
        colonia_id=regina.colonia_id, regina=regina, data_fine__isnull=True,
    ).first()
    if aperta:
        return aperta
    return StoriaRegine.objects.create(
        colonia_id=regina.colonia_id,
        regina=regina,
        data_inizio=regina.data_introduzione,
    )


def chiudi_storia(regina: Regina, data_fine: date, motivo: str) -> StoriaRegine | None:
    """Chiude la riga aperta della regina; se manca, la crea già chiusa."""
    if not regina.colonia_id:
        return None
    storia = StoriaRegine.objects.filter(
        colonia_id=regina.colonia_id, regina=regina, data_fine__isnull=True,
    ).order_by('-data_inizio').first()
    if storia is None:
        storia = StoriaRegine(
            colonia_id=regina.colonia_id,
            regina=regina,
            data_inizio=min(regina.data_introduzione, data_fine),
        )
    storia.data_fine = data_fine
    storia.motivo_fine = motivo[:100]  # StoriaRegine.motivo_fine è max_length=100
    storia.save()
    return storia


def chiudi_storia_colonia(colonia: Colonia) -> StoriaRegine | None:
    """Alla chiusura di una colonia chiude anche il periodo della sua regina.

    La regina resta agganciata alla colonia chiusa, di cui fa parte la storia;
    senza data di fine, però, non entrava nella durata media.
    """
    try:
        regina = colonia.regina
    except Regina.DoesNotExist:
        return None
    return chiudi_storia(
        regina,
        colonia.data_fine or date.today(),
        f"Colonia chiusa: {colonia.get_stato_display()}",
    )
