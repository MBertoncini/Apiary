"""Logica di cantina condivisa da API, signal e comandi.

Due responsabilità:

1. **Vasetti e vendite** — `scarica_lotti` toglie dai lotti di cantina i
   vasetti di una riga di vendita (FIFO) e ne tiene traccia in
   `DettaglioVenditaLotto`; `ripristina_lotti` li restituisce quando la riga
   viene modificata o eliminata.

2. **Produzione per colonia** — `ripartisci_kg_smielatura` divide i kg di una
   smielatura fra i melari che l'hanno prodotta, così ogni colonia ha il suo
   dato di raccolto (target dei modelli predittivi).
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F, Q

from .models import (
    DettaglioVenditaLotto, Invasettamento, PesataMelario, Smielatura,
    SmielaturaMelario,
)

CENT = Decimal('0.01')
TOLLERANZA_KG = Decimal('0.01')


def kg_vasetti(formato_vasetto, numero_vasetti):
    """Kg di miele contenuti in `numero_vasetti` vasetti da `formato_vasetto` g."""
    return (Decimal(int(formato_vasetto)) * Decimal(int(numero_vasetti)) / Decimal(1000)).quantize(
        CENT, rounding=ROUND_HALF_UP)


def stato_contenitore(kg_attuali, capacita_kg):
    kg = Decimal(str(kg_attuali))
    if kg <= 0:
        return 'vuoto'
    if kg < Decimal(str(capacita_kg)):
        return 'parziale'
    return 'pieno'


# ── Vasetti e vendite ────────────────────────────────────────────────────────

def lotti_accessibili(user):
    """Lotti di vasetti che l'utente può vedere e vendere."""
    from .api_views import get_apiari_accessibili
    return Invasettamento.objects.filter(
        Q(utente=user)
        | Q(smielatura__apiario__in=get_apiari_accessibili(user))
        | Q(contenitore__utente=user)
    ).distinct()


def scarica_lotti(dettaglio):
    """Scarica dalla cantina i vasetti di una riga di vendita di miele.

    Prende dai lotti più vecchi con lo stesso tipo di miele e formato. Se la
    cantina non copre tutta la quantità si scarica quel che c'è: una vendita
    resta registrabile anche da chi non tiene i lotti in cantina.
    Restituisce il numero di vasetti effettivamente scaricati.
    """
    tipo = (dettaglio.tipo_miele or '').strip()
    if dettaglio.categoria != 'miele' or not tipo or not dettaglio.formato_vasetto:
        return 0
    rimanenti = int(dettaglio.quantita or 0)
    if rimanenti <= 0:
        return 0

    scaricati = 0
    with transaction.atomic():
        ids = list(
            lotti_accessibili(dettaglio.vendita.utente).filter(
                tipo_miele__iexact=tipo,
                formato_vasetto=dettaglio.formato_vasetto,
                numero_vasetti__gt=F('numero_vasetti_venduti'),
            ).values_list('id', flat=True)
        )
        lotti = Invasettamento.objects.select_for_update().filter(
            id__in=ids).order_by('data', 'id')
        for lotto in lotti:
            if rimanenti <= 0:
                break
            preso = min(lotto.vasetti_disponibili, rimanenti)
            if preso <= 0:
                continue
            lotto.numero_vasetti_venduti += preso
            if lotto.numero_vasetti_venduti >= lotto.numero_vasetti:
                lotto.stato = 'venduto'
            lotto.save(update_fields=['numero_vasetti_venduti', 'stato'])
            DettaglioVenditaLotto.objects.create(
                dettaglio=dettaglio, invasettamento=lotto, quantita=preso)
            rimanenti -= preso
            scaricati += preso
    return scaricati


def ripristina_lotti(dettaglio):
    """Restituisce ai lotti i vasetti scaricati da una riga di vendita."""
    with transaction.atomic():
        scarichi = list(DettaglioVenditaLotto.objects.filter(dettaglio=dettaglio))
        for scarico in scarichi:
            lotto = Invasettamento.objects.select_for_update().filter(
                pk=scarico.invasettamento_id).first()
            if lotto is None:
                continue
            lotto.numero_vasetti_venduti = max(
                0, lotto.numero_vasetti_venduti - scarico.quantita)
            if lotto.numero_vasetti_venduti < lotto.numero_vasetti:
                lotto.stato = 'disponibile'
            lotto.save(update_fields=['numero_vasetti_venduti', 'stato'])
        DettaglioVenditaLotto.objects.filter(
            pk__in=[s.pk for s in scarichi]).delete()


# ── Smielatura: kg trasferiti ────────────────────────────────────────────────

def sposta_kg_trasferiti(smielatura_id, delta):
    """Somma `delta` (anche negativo) a Smielatura.kg_trasferiti, mai sotto 0."""
    if not smielatura_id:
        return
    delta = Decimal(str(delta))
    if delta == 0:
        return
    with transaction.atomic():
        sm = Smielatura.objects.select_for_update().filter(pk=smielatura_id).first()
        if sm is None:
            return
        sm.kg_trasferiti = max(Decimal('0'), Decimal(sm.kg_trasferiti) + delta)
        sm.save(update_fields=['kg_trasferiti'])


# ── Produzione per colonia ───────────────────────────────────────────────────

# Capienza relativa dei formati di melario, usata quando mancano le pesate.
FATTORE_TIPO_MELARIO = {'standard': 1.0, 'tre_quarti': 0.75, 'meta': 0.5}


def _netto_da_pesate(melario_id, data_smielatura):
    """Kg netti di miele stimati dalle pesate del melario, o None."""
    pesate = list(
        PesataMelario.objects.filter(melario_id=melario_id, data__lte=data_smielatura)
        .order_by('-data', '-id')
    )
    finale = next((p for p in pesate if p.tipo in ('smielatura', 'rimozione')), None)
    if finale is None:
        return None
    if finale.peso_netto_kg is not None:
        return float(finale.peso_netto_kg)
    # Senza tara: la pesata al posizionamento (melario vuoto) fa da tara.
    iniziale = next((p for p in pesate if p.tipo == 'posizionamento'), None)
    if iniziale is not None:
        return max(0.0, float(finale.peso_lordo_kg) - float(iniziale.peso_lordo_kg))
    return None


def _pesi_ripartizione(righe, data_smielatura):
    """Peso relativo di ogni riga e criterio usato ('pesate' o 'telaini')."""
    netti = [_netto_da_pesate(r.melario_id, data_smielatura) for r in righe]
    if righe and all(n is not None and n > 0 for n in netti):
        return netti, 'pesate'
    pesi = []
    for r in righe:
        telaini = r.melario.numero_telaini or 0
        fattore = FATTORE_TIPO_MELARIO.get(r.melario.tipo_melario, 1.0)
        pesi.append(telaini * fattore if telaini > 0 else fattore)
    return pesi, 'telaini'


def ripartisci_kg_smielatura(smielatura):
    """Divide i kg della smielatura fra i suoi melari.

    Le righe con `kg_manuale=True` non vengono toccate; il resto dei kg è
    diviso fra le altre in proporzione al miele pesato (se tutte hanno una
    pesata utile) oppure ai telaini, corretti per il formato del melario.
    Restituisce il criterio usato, o None se non c'era nulla da ripartire.
    """
    if not isinstance(smielatura, Smielatura):
        smielatura = Smielatura.objects.filter(pk=smielatura).first()
    if smielatura is None:
        return None

    righe = list(
        SmielaturaMelario.objects.filter(smielatura=smielatura)
        .select_related('melario').order_by('id')
    )
    if not righe:
        return None

    manuali = [r for r in righe if r.kg_manuale and r.kg_miele is not None]
    auto = [r for r in righe if not (r.kg_manuale and r.kg_miele is not None)]
    if not auto:
        return 'manuale'

    totale = Decimal(str(smielatura.quantita_miele or 0))
    residuo = max(Decimal('0'), totale - sum((r.kg_miele for r in manuali), Decimal('0')))
    pesi, criterio = _pesi_ripartizione(auto, smielatura.data)
    somma_pesi = sum(pesi) or 1.0

    assegnati = Decimal('0')
    for i, (riga, peso) in enumerate(zip(auto, pesi)):
        if i == len(auto) - 1:
            # L'ultima riga assorbe gli arrotondamenti: la somma torna esatta.
            kg = residuo - assegnati
        else:
            kg = (residuo * Decimal(str(peso)) / Decimal(str(somma_pesi))).quantize(
                CENT, rounding=ROUND_HALF_UP)
            assegnati += kg
        kg = max(Decimal('0'), kg)
        if riga.kg_miele != kg or riga.kg_manuale:
            SmielaturaMelario.objects.filter(pk=riga.pk).update(
                kg_miele=kg, kg_manuale=False)
    return criterio


def aggancia_melari_smielatura(smielatura, melari_ids):
    """Completa le righe appena create: colonia produttrice e pesate collegate."""
    righe = SmielaturaMelario.objects.filter(
        smielatura=smielatura, melario_id__in=melari_ids,
    ).select_related('melario')
    for riga in righe:
        if riga.colonia_id is None and riga.melario.colonia_id:
            SmielaturaMelario.objects.filter(pk=riga.pk).update(
                colonia_id=riga.melario.colonia_id)
    PesataMelario.objects.filter(
        melario_id__in=melari_ids, smielatura__isnull=True,
        tipo__in=('rimozione', 'smielatura'), data__lte=smielatura.data,
    ).update(smielatura=smielatura)
