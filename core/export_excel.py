"""Esportazione dei dati dell'utente in un file Excel multi-foglio.

Un foglio per ogni sezione (apiari, arnie, controlli, trattamenti, ...) più un
foglio di riepilogo con filtri applicati e numero di righe per sezione.

Il perimetro dei dati è lo stesso delle API REST: apiari propri o condivisi
con i gruppi dell'utente (``get_apiari_accessibili``) e, per i dati economici
non legati a un apiario (vendite, pagamenti, attrezzature), i record propri o
del gruppo. Il filtro per apiario si applica solo ai fogli legati a un
apiario; il filtro per anno solo ai fogli di eventi datati (non alle anagrafiche).

Usato da ``api_views.export_dati_excel`` (GET /api/v1/export/excel/).
"""

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Callable, Iterable, Optional

from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import (
    Alimentazione, Apiario, Arnia, Attrezzatura, Colonia, ControlloArnia,
    Gruppo, Invasettamento, Melario, Pagamento, Regina, Smielatura,
    SpesaAttrezzatura, TrattamentoSanitario, VarroaCheckpoint, Vendita,
)

LINGUE = ('it', 'en')

_HEADER_FILL = PatternFill('solid', fgColor='D4A017')
_TITLE_FILL = PatternFill('solid', fgColor='1A1A2E')
_DATE_FORMAT = 'DD/MM/YYYY'
_DATETIME_FORMAT = 'DD/MM/YYYY HH:MM'
_MAX_CELL_LEN = 32767  # limite Excel per cella


@dataclass
class Filtri:
    user: object
    apiari: object          # queryset degli apiari nel perimetro (già filtrato per apiario)
    gruppi: object          # queryset dei gruppi dell'utente
    anno: Optional[int]
    lang: str
    per_apiario: bool       # True se l'utente ha scelto un singolo apiario

    def t(self, it: str, en: str) -> str:
        return en if self.lang == 'en' else it

    def bool(self, value) -> str:
        if value is None:
            return ''
        return self.t('Sì', 'Yes') if value else 'No'


@dataclass
class Sezione:
    key: str
    titolo: tuple            # (it, en) — max 31 caratteri, limite Excel
    colonne: list            # [(it, en), ...]
    righe: Callable[[Filtri], Iterable[list]]


# ── Helper ──────────────────────────────────────────────────────────────────

def _nome_utente(user) -> str:
    if user is None:
        return ''
    return user.get_full_name() or user.username


def _contenitore(colonia) -> str:
    if colonia is None:
        return ''
    return colonia.contenitore_display()


def _anno(qs, campo, filtri: Filtri):
    if filtri.anno:
        return qs.filter(**{f'{campo}__year': filtri.anno})
    return qs


# ── Righe per sezione ───────────────────────────────────────────────────────

def _righe_apiari(f: Filtri):
    qs = f.apiari.select_related('proprietario', 'gruppo').order_by('nome')
    for a in qs:
        yield [
            a.id, a.nome, a.posizione, a.latitudine, a.longitudine,
            _nome_utente(a.proprietario), a.gruppo.nome if a.gruppo else '',
            f.bool(a.condiviso_con_gruppo), a.data_creazione, a.note,
        ]


def _righe_arnie(f: Filtri):
    qs = (Arnia.objects.filter(apiario__in=f.apiari)
          .select_related('apiario').order_by('apiario__nome', 'numero'))
    for a in qs:
        yield [
            a.id, a.apiario.nome, a.numero, a.get_tipo_arnia_display(),
            a.get_colore_display(), a.data_installazione, f.bool(a.attiva), a.note,
        ]


def _righe_colonie(f: Filtri):
    qs = (Colonia.objects.filter(apiario__in=f.apiari)
          .select_related('apiario', 'arnia', 'nucleo')
          .order_by('apiario__nome', '-data_inizio'))
    for c in qs:
        yield [
            c.id, c.apiario.nome, _contenitore(c), c.get_stato_display(),
            c.data_inizio, c.data_fine, c.colonia_origine_id, c.motivo_fine, c.note,
        ]


def _righe_controlli(f: Filtri):
    qs = ControlloArnia.objects.filter(
        Q(colonia__apiario__in=f.apiari) |
        Q(colonia__isnull=True, arnia__apiario__in=f.apiari)
    ).select_related(
        'colonia', 'colonia__apiario', 'colonia__arnia', 'colonia__nucleo',
        'arnia', 'arnia__apiario', 'utente',
    ).distinct().order_by('-data', '-id')
    for c in _anno(qs, 'data', f):
        apiario = c.colonia.apiario if c.colonia else (c.arnia.apiario if c.arnia else None)
        contenitore = f'Arnia {c.arnia.numero}' if c.arnia else _contenitore(c.colonia)
        yield [
            c.data, apiario.nome if apiario else '', contenitore, c.colonia_id,
            c.telaini_covata, c.telaini_scorte, f.bool(c.presenza_regina),
            f.bool(c.regina_vista), f.bool(c.uova_fresche), f.bool(c.celle_reali),
            c.numero_celle_reali, f.bool(c.regina_sostituita), f.bool(c.sciamatura),
            c.data_sciamatura, f.bool(c.problemi_sanitari), c.note_problemi, c.note,
            _nome_utente(c.utente),
        ]


def _righe_regine(f: Filtri):
    qs = (Regina.objects.filter(colonia__apiario__in=f.apiari)
          .select_related('colonia', 'colonia__apiario', 'colonia__arnia', 'colonia__nucleo')
          .distinct().order_by('-data_introduzione'))
    for r in qs:
        yield [
            r.id, r.colonia.apiario.nome if r.colonia else '', _contenitore(r.colonia),
            r.colonia_id, r.get_razza_display(), r.get_origine_display(),
            r.data_nascita, r.data_introduzione, f.bool(r.marcata),
            r.get_colore_marcatura_display(), r.codice_marcatura, f.bool(r.fecondata),
            f.bool(r.selezionata), r.docilita, r.produttivita, r.resistenza_malattie,
            r.tendenza_sciamatura, r.regina_madre_id, r.note,
        ]


def _righe_trattamenti(f: Filtri):
    qs = (TrattamentoSanitario.objects.filter(apiario__in=f.apiari)
          .select_related('apiario', 'tipo_trattamento')
          .prefetch_related('colonie__arnia', 'colonie__nucleo', 'arnie')
          .order_by('-data_inizio'))
    stati = dict(TrattamentoSanitario.STATO_CHOICES)
    for t in _anno(qs, 'data_inizio', f):
        trattate = [_contenitore(c) for c in t.colonie.all()]
        if not trattate:
            trattate = [f'Arnia {a.numero}' for a in t.arnie.all()]
        yield [
            t.data_inizio, t.data_fine, t.apiario.nome, t.tipo_trattamento.nome,
            t.tipo_trattamento.principio_attivo, t.get_metodo_applicazione_display() or '',
            stati.get(t.stato_effettivo, t.stato),
            ', '.join(trattate) or f.t("Tutto l'apiario", 'Whole apiary'),
            t.data_fine_sospensione, f.bool(t.blocco_covata_attivo),
            t.data_inizio_blocco, t.data_fine_blocco, t.metodo_blocco, t.note,
        ]


def _righe_varroa(f: Filtri):
    qs = (VarroaCheckpoint.objects.filter(colonia__apiario__in=f.apiari)
          .select_related('colonia', 'colonia__apiario', 'colonia__arnia', 'colonia__nucleo')
          .order_by('-data_campionamento'))
    for v in _anno(qs, 'data_campionamento', f):
        yield [
            v.data_campionamento, v.colonia.apiario.nome, _contenitore(v.colonia),
            v.colonia_id, v.get_metodo_display(), v.api_campionate, v.acari_contati,
            v.giorni_misurazione, v.percentuale_calcolata, v.caduta_giornaliera, v.note,
        ]


def _righe_alimentazioni(f: Filtri):
    qs = (Alimentazione.objects.filter(colonia__apiario__in=f.apiari)
          .select_related('colonia', 'colonia__apiario', 'colonia__arnia', 'colonia__nucleo')
          .order_by('-data', '-id'))
    for a in _anno(qs, 'data', f):
        yield [
            a.data, a.colonia.apiario.nome, _contenitore(a.colonia), a.colonia_id,
            a.get_tipo_display(), a.get_scopo_display() if a.scopo else '',
            a.quantita_kg, a.note,
        ]


def _righe_melari(f: Filtri):
    qs = (Melario.objects.filter(colonia__apiario__in=f.apiari)
          .select_related('colonia', 'colonia__apiario', 'colonia__arnia', 'colonia__nucleo')
          .distinct().order_by('-data_posizionamento'))
    for m in _anno(qs, 'data_posizionamento', f):
        yield [
            m.numero_progressivo or m.id, m.colonia.apiario.nome, _contenitore(m.colonia),
            m.colonia_id, m.posizione, m.get_tipo_melario_display(), m.numero_telaini,
            m.get_stato_favi_display(), f.bool(m.escludi_regina), m.data_posizionamento,
            m.data_rimozione, m.get_stato_display(), m.peso_stimato, m.note,
        ]


def _righe_smielature(f: Filtri):
    qs = (Smielatura.objects.filter(apiario__in=f.apiari)
          .select_related('apiario').prefetch_related('melari', 'fioriture')
          .order_by('-data'))
    for s in _anno(qs, 'data', f):
        yield [
            s.data, s.apiario.nome, s.tipo_miele, s.quantita_miele, s.kg_trasferiti,
            s.kg_residui, len(s.melari.all()),
            ', '.join(fi.pianta for fi in s.fioriture.all()),
            f.bool(s.archiviata), s.note,
        ]


def _righe_invasettamenti(f: Filtri):
    accesso = Q(smielatura__apiario__in=f.apiari)
    if not f.per_apiario:
        accesso |= Q(contenitore__utente=f.user)
    qs = (Invasettamento.objects.filter(accesso)
          .select_related('smielatura', 'smielatura__apiario')
          .distinct().order_by('-data'))
    for i in _anno(qs, 'data', f):
        yield [
            i.data, i.smielatura.apiario.nome if i.smielatura else '', i.tipo_miele,
            i.formato_vasetto, i.numero_vasetti, i.numero_vasetti_venduti,
            i.vasetti_disponibili, i.kg_totali, i.lotto, i.get_stato_display(), i.note,
        ]


def _righe_vendite(f: Filtri):
    qs = (Vendita.objects.filter(Q(utente=f.user) | Q(gruppo__in=f.gruppi))
          .select_related('cliente').prefetch_related('dettagli')
          .distinct().order_by('-data', '-id'))
    for v in _anno(qs, 'data', f):
        cliente = v.cliente.nome if v.cliente else (v.acquirente_nome or '')
        testa = [v.id, v.data, cliente, v.get_canale_display(), v.get_pagamento_display()]
        dettagli = list(v.dettagli.all())
        if not dettagli:
            yield testa + ['', '', '', None, None, None, v.note]
        for d in dettagli:
            yield testa + [
                d.get_categoria_display(), d.tipo_miele or '', d.formato_vasetto,
                d.quantita, d.prezzo_unitario, d.subtotale, v.note,
            ]


def _righe_pagamenti(f: Filtri):
    qs = (Pagamento.objects.filter(Q(utente=f.user) | Q(gruppo__in=f.gruppi))
          .select_related('utente', 'destinatario', 'gruppo')
          .distinct().order_by('-data', '-id'))
    for p in _anno(qs, 'data', f):
        yield [
            p.data, p.descrizione, p.importo, _nome_utente(p.utente),
            _nome_utente(p.destinatario), p.gruppo.nome if p.gruppo else '',
            f.bool(p.spesa_attrezzatura_id is not None),
        ]


def _righe_attrezzature(f: Filtri):
    qs = (Attrezzatura.objects.filter(
            Q(proprietario=f.user) |
            Q(condiviso_con_gruppo=True, gruppo__in=f.gruppi))
          .select_related('categoria', 'apiario', 'gruppo')
          .distinct().order_by('nome'))
    for a in qs:
        yield [
            a.nome, a.categoria.nome if a.categoria else '', a.marca, a.modello,
            a.numero_serie, a.get_stato_display(), a.get_condizione_display(),
            a.apiario.nome if a.apiario else '', a.posizione, a.quantita, a.unita_misura,
            a.prezzo_acquisto, a.data_acquisto, a.fornitore,
            a.gruppo.nome if a.gruppo else '',
        ]


def _righe_spese_attrezzatura(f: Filtri):
    qs = (SpesaAttrezzatura.objects.filter(Q(utente=f.user) | Q(gruppo__in=f.gruppi))
          .select_related('attrezzatura', 'pagato_da', 'gruppo')
          .distinct().order_by('-data', '-id'))
    for s in _anno(qs, 'data', f):
        yield [
            s.data, s.get_tipo_display(), s.descrizione,
            s.attrezzatura.nome if s.attrezzatura else '', s.importo, s.fornitore,
            s.numero_fattura, _nome_utente(s.pagato_da),
            s.gruppo.nome if s.gruppo else '', s.note,
        ]


# ── Definizione dei fogli ───────────────────────────────────────────────────

_APIARIO = ('Apiario', 'Apiary')
_CONTENITORE = ('Arnia/Nucleo', 'Hive/Nuc')
_COLONIA_ID = ('ID colonia', 'Colony ID')
_DATA = ('Data', 'Date')
_NOTE = ('Note', 'Notes')

SEZIONI = [
    Sezione('apiari', ('Apiari', 'Apiaries'), [
        ('ID', 'ID'), ('Nome', 'Name'), ('Posizione', 'Location'),
        ('Latitudine', 'Latitude'), ('Longitudine', 'Longitude'),
        ('Proprietario', 'Owner'), ('Gruppo', 'Group'),
        ('Condiviso con gruppo', 'Shared with group'),
        ('Data creazione', 'Created'), _NOTE,
    ], _righe_apiari),
    Sezione('arnie', ('Arnie', 'Hives'), [
        ('ID', 'ID'), _APIARIO, ('Numero', 'Number'), ('Tipo', 'Type'),
        ('Colore', 'Colour'), ('Data installazione', 'Installed'),
        ('Attiva', 'Active'), _NOTE,
    ], _righe_arnie),
    Sezione('colonie', ('Colonie', 'Colonies'), [
        ('ID', 'ID'), _APIARIO, _CONTENITORE, ('Stato', 'Status'),
        ('Data inizio', 'Start date'), ('Data fine', 'End date'),
        ('ID colonia origine', 'Parent colony ID'), ('Motivo fine', 'End reason'), _NOTE,
    ], _righe_colonie),
    Sezione('controlli', ('Controlli', 'Inspections'), [
        _DATA, _APIARIO, _CONTENITORE, _COLONIA_ID,
        ('Telaini covata', 'Brood frames'), ('Telaini scorte', 'Store frames'),
        ('Presenza regina', 'Queen present'), ('Regina vista', 'Queen seen'),
        ('Uova fresche', 'Fresh eggs'), ('Celle reali', 'Queen cells'),
        ('N. celle reali', 'No. queen cells'), ('Regina sostituita', 'Queen replaced'),
        ('Sciamatura', 'Swarming'), ('Data sciamatura', 'Swarm date'),
        ('Problemi sanitari', 'Health issues'), ('Note problemi', 'Issue notes'),
        _NOTE, ('Utente', 'User'),
    ], _righe_controlli),
    Sezione('regine', ('Regine', 'Queens'), [
        ('ID', 'ID'), _APIARIO, _CONTENITORE, _COLONIA_ID, ('Razza', 'Breed'),
        ('Origine', 'Origin'), ('Data nascita', 'Birth date'),
        ('Data introduzione', 'Introduced'), ('Marcata', 'Marked'),
        ('Colore marcatura', 'Marking colour'), ('Codice marcatura', 'Marking code'),
        ('Fecondata', 'Mated'), ('Selezionata', 'Selected'),
        ('Docilità (1-5)', 'Gentleness (1-5)'), ('Produttività (1-5)', 'Productivity (1-5)'),
        ('Resistenza malattie (1-5)', 'Disease resistance (1-5)'),
        ('Tendenza sciamatura (1-5)', 'Swarming tendency (1-5)'),
        ('ID regina madre', 'Mother queen ID'), _NOTE,
    ], _righe_regine),
    Sezione('trattamenti', ('Trattamenti', 'Treatments'), [
        ('Data inizio', 'Start date'), ('Data fine', 'End date'), _APIARIO,
        ('Trattamento', 'Treatment'), ('Principio attivo', 'Active ingredient'),
        ('Metodo', 'Method'), ('Stato', 'Status'), ('Trattate', 'Treated'),
        ('Fine sospensione', 'Withdrawal end'), ('Blocco covata', 'Brood break'),
        ('Inizio blocco', 'Break start'), ('Fine blocco', 'Break end'),
        ('Metodo blocco', 'Break method'), _NOTE,
    ], _righe_trattamenti),
    Sezione('varroa', ('Varroa', 'Varroa'), [
        _DATA, _APIARIO, _CONTENITORE, _COLONIA_ID, ('Metodo', 'Method'),
        ('Api campionate', 'Bees sampled'), ('Acari contati', 'Mites counted'),
        ('Giorni misurazione', 'Days measured'), ('Infestazione %', 'Infestation %'),
        ('Caduta giornaliera', 'Daily mite drop'), _NOTE,
    ], _righe_varroa),
    Sezione('alimentazioni', ('Alimentazioni', 'Feeding'), [
        _DATA, _APIARIO, _CONTENITORE, _COLONIA_ID, ('Tipo', 'Type'),
        ('Scopo', 'Purpose'), ('Quantità (kg)', 'Quantity (kg)'), _NOTE,
    ], _righe_alimentazioni),
    Sezione('melari', ('Melari', 'Supers'), [
        ('Numero', 'Number'), _APIARIO, _CONTENITORE, _COLONIA_ID,
        ('Posizione', 'Position'), ('Tipo', 'Type'), ('N. telaini', 'No. frames'),
        ('Favi', 'Combs'), ('Escludiregina', 'Queen excluder'),
        ('Data posizionamento', 'Placed'), ('Data rimozione', 'Removed'),
        ('Stato', 'Status'), ('Peso stimato (kg)', 'Est. weight (kg)'), _NOTE,
    ], _righe_melari),
    Sezione('smielature', ('Smielature', 'Extractions'), [
        _DATA, _APIARIO, ('Tipo miele', 'Honey type'), ('Quantità (kg)', 'Quantity (kg)'),
        ('Kg in maturazione', 'Kg to ripening'), ('Kg residui', 'Kg remaining'),
        ('N. melari', 'No. supers'), ('Fioriture', 'Blooms'),
        ('Archiviata', 'Archived'), _NOTE,
    ], _righe_smielature),
    Sezione('invasettamenti', ('Invasettamenti', 'Jarring'), [
        _DATA, _APIARIO, ('Tipo miele', 'Honey type'), ('Formato (g)', 'Jar size (g)'),
        ('Vasetti', 'Jars'), ('Venduti', 'Sold'), ('Disponibili', 'Available'),
        ('Kg totali', 'Total kg'), ('Lotto', 'Batch'), ('Stato', 'Status'), _NOTE,
    ], _righe_invasettamenti),
    Sezione('vendite', ('Vendite', 'Sales'), [
        ('ID vendita', 'Sale ID'), _DATA, ('Cliente', 'Customer'), ('Canale', 'Channel'),
        ('Pagamento', 'Payment'), ('Categoria', 'Category'), ('Tipo miele', 'Honey type'),
        ('Formato (g)', 'Jar size (g)'), ('Quantità', 'Quantity'),
        ('Prezzo unitario (€)', 'Unit price (€)'), ('Subtotale (€)', 'Subtotal (€)'), _NOTE,
    ], _righe_vendite),
    Sezione('pagamenti', ('Pagamenti', 'Payments'), [
        _DATA, ('Descrizione', 'Description'), ('Importo (€)', 'Amount (€)'),
        ('Pagato da', 'Paid by'), ('Destinatario', 'Recipient'), ('Gruppo', 'Group'),
        ('Da spesa attrezzatura', 'From equipment expense'),
    ], _righe_pagamenti),
    Sezione('attrezzature', ('Attrezzature', 'Equipment'), [
        ('Nome', 'Name'), ('Categoria', 'Category'), ('Marca', 'Brand'),
        ('Modello', 'Model'), ('N. serie', 'Serial no.'), ('Stato', 'Status'),
        ('Condizione', 'Condition'), _APIARIO, ('Posizione', 'Location'),
        ('Quantità', 'Quantity'), ('Unità', 'Unit'),
        ('Prezzo acquisto (€)', 'Purchase price (€)'), ('Data acquisto', 'Purchase date'),
        ('Fornitore', 'Supplier'), ('Gruppo', 'Group'),
    ], _righe_attrezzature),
    Sezione('spese_attrezzatura', ('Spese attrezzatura', 'Equipment expenses'), [
        _DATA, ('Tipo', 'Type'), ('Descrizione', 'Description'),
        ('Attrezzatura', 'Equipment'), ('Importo (€)', 'Amount (€)'),
        ('Fornitore', 'Supplier'), ('N. fattura', 'Invoice no.'),
        ('Pagato da', 'Paid by'), ('Gruppo', 'Group'), _NOTE,
    ], _righe_spese_attrezzatura),
]

SEZIONI_KEYS = [s.key for s in SEZIONI]

# Fogli non legati a un apiario: il filtro per apiario non li restringe.
SEZIONI_NON_APIARIO = {'vendite', 'pagamenti', 'attrezzature', 'spese_attrezzatura'}


# ── Scrittura del workbook ──────────────────────────────────────────────────

def _valore_cella(value):
    """Normalizza un valore Python per openpyxl."""
    if isinstance(value, datetime):
        # openpyxl non accetta datetime con timezone
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub('', value)
        return value[:_MAX_CELL_LEN]
    return value


def _scrivi_riga(ws, riga: list):
    ws.append([_valore_cella(v) for v in riga])
    for cell in ws[ws.max_row]:
        # Le stringhe che iniziano con '=' verrebbero salvate come formule:
        # un testo inserito dall'utente non deve mai diventare una formula.
        if cell.data_type == 'f':
            cell.data_type = 's'
        elif isinstance(cell.value, datetime):
            cell.number_format = _DATETIME_FORMAT
        elif isinstance(cell.value, date):
            cell.number_format = _DATE_FORMAT


def _formatta_foglio(ws, n_colonne: int):
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.freeze_panes = 'A2'
    if ws.max_row > 1:
        ws.auto_filter.ref = f'A1:{get_column_letter(n_colonne)}{ws.max_row}'
    for idx, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 500)), 1):
        larghezza = max(
            (10 if isinstance(c.value, (date, datetime)) else len(str(c.value or '')))
            for c in col
        )
        ws.column_dimensions[get_column_letter(idx)].width = min(max(larghezza + 2, 10), 50)


def genera_export_excel(user, *, apiario_id=None, anno=None, sezioni=None, lang='it') -> bytes:
    """Costruisce il workbook e ne restituisce i byte.

    ``apiario_id`` deve essere già validato come accessibile dal chiamante.
    ``sezioni`` è una lista di chiavi di ``SEZIONI_KEYS`` (None = tutte).
    """
    from .api_views import get_apiari_accessibili

    apiari = get_apiari_accessibili(user)
    apiario_nome = None
    if apiario_id is not None:
        apiari = apiari.filter(pk=apiario_id)
        apiario_nome = apiari.values_list('nome', flat=True).first()
    filtri = Filtri(
        user=user,
        apiari=apiari,
        gruppi=Gruppo.objects.filter(membri=user),
        anno=anno,
        lang=lang if lang in LINGUE else 'it',
        per_apiario=apiario_id is not None,
    )
    t = filtri.t
    selezionate = [s for s in SEZIONI if sezioni is None or s.key in sezioni]

    wb = Workbook()
    riepilogo = wb.active
    riepilogo.title = t('Riepilogo', 'Summary')

    conteggi = []
    for sezione in selezionate:
        ws = wb.create_sheet(t(*sezione.titolo)[:31])
        ws.append([t(*c) for c in sezione.colonne])
        n = 0
        for riga in sezione.righe(filtri):
            _scrivi_riga(ws, riga)
            n += 1
        _formatta_foglio(ws, len(sezione.colonne))
        conteggi.append((t(*sezione.titolo), n, sezione.key))

    # Foglio di riepilogo
    riepilogo.append([t('Apiary Manager — esportazione dati', 'Apiary Manager — data export')])
    riepilogo['A1'].font = Font(bold=True, size=14, color='FFFFFF')
    riepilogo['A1'].fill = _TITLE_FILL
    riepilogo.merge_cells('A1:B1')
    info = [
        (t('Generato il', 'Generated on'), timezone.localtime().replace(tzinfo=None)),
        (t('Utente', 'User'), _nome_utente(user)),
        (t('Apiario', 'Apiary'), apiario_nome or t('Tutti', 'All')),
        (t('Anno', 'Year'), anno or t('Tutti', 'All')),
    ]
    for label, value in info:
        _scrivi_riga(riepilogo, [label, value])
        riepilogo.cell(row=riepilogo.max_row, column=1).font = Font(bold=True)
    riepilogo.append([])
    riepilogo.append([t('Foglio', 'Sheet'), t('Righe', 'Rows')])
    for cell in riepilogo[riepilogo.max_row]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = _HEADER_FILL
    for titolo, n, key in conteggi:
        riepilogo.append([titolo, n])
    if apiario_id is not None and any(k in SEZIONI_NON_APIARIO for _, _, k in conteggi):
        riepilogo.append([])
        riepilogo.append([t(
            'Vendite, pagamenti e attrezzature non sono legati a un apiario: '
            'sono esportati per intero.',
            'Sales, payments and equipment are not tied to an apiary: '
            'they are exported in full.',
        )])
    riepilogo.column_dimensions['A'].width = 34
    riepilogo.column_dimensions['B'].width = 24

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
