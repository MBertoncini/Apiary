from django.db.models import Avg, Count, Sum, F
from django.db.models.functions import ExtractMonth, ExtractYear, TruncMonth
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from core.models import (
    Apiario, Arnia, ControlloArnia, DettaglioVendita,
    Fioritura, Regina, Smielatura, SpesaAttrezzatura, Vendita,
)

# Mappa entità → modello e campo utente
ENTITY_CONFIG = {
    'arnie': {
        'model': Arnia,
        'user_filter': 'apiario__proprietario',
        'date_field': 'data_installazione',
        'fields': ['numero', 'colore', 'attiva', 'data_installazione'],
    },
    'controlli': {
        'model': ControlloArnia,
        'user_filter': 'utente',
        'date_field': 'data',
        'fields': ['data', 'telaini_covata', 'telaini_scorte', 'presenza_regina', 'sciamatura', 'problemi_sanitari'],
    },
    'smielature': {
        'model': Smielatura,
        'user_filter': 'utente',
        'date_field': 'data',
        'fields': ['data', 'tipo_miele', 'quantita_miele'],
    },
    'regine': {
        'model': Regina,
        'user_filter': 'arnia__apiario__proprietario',
        'date_field': 'data_introduzione',
        'fields': ['razza', 'origine', 'data_nascita', 'data_introduzione', 'produttivita', 'docilita'],
    },
    'vendite': {
        'model': DettaglioVendita,
        'user_filter': 'vendita__utente',
        'date_field': 'vendita__data',
        'fields': ['categoria', 'tipo_miele', 'quantita', 'prezzo_unitario'],
    },
    'spese': {
        'model': SpesaAttrezzatura,
        'user_filter': 'utente',
        'date_field': 'data',
        'fields': ['tipo', 'descrizione', 'importo', 'data'],
    },
    'fioriture': {
        'model': Fioritura,
        'user_filter': 'creatore',
        'date_field': 'data_inizio',
        'fields': ['pianta', 'data_inizio', 'data_fine', 'intensita'],
    },
}

AGGREGATION_MAP = {
    'count': Count('id'),
    'sum_quantita': Sum('quantita_miele'),
    'avg': None,  # calcolato dinamicamente
    'none': None,
}

RAGGRUPPA_MAP = {
    'mese': TruncMonth,
    'anno': ExtractYear,
}


class QueryBuilderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        entita = request.data.get('entita', '').lower()
        filtri = request.data.get('filtri', {})
        aggregazione = request.data.get('aggregazione', 'count')
        raggruppa_per = request.data.get('raggruppa_per', '')
        visualizzazione = request.data.get('visualizzazione', 'table')

        if entita not in ENTITY_CONFIG:
            return Response(
                {'error': f"Entità '{entita}' non supportata. Disponibili: {', '.join(ENTITY_CONFIG.keys())}"},
                status=400,
            )

        config = ENTITY_CONFIG[entita]
        qs = config['model'].objects.filter(**{config['user_filter']: request.user})

        # Applica filtri comuni
        date_field = config['date_field']
        if filtri.get('data_da'):
            qs = qs.filter(**{f'{date_field}__gte': filtri['data_da']})
        if filtri.get('data_a'):
            qs = qs.filter(**{f'{date_field}__lte': filtri['data_a']})
        if filtri.get('apiario_id'):
            if entita == 'arnie':
                qs = qs.filter(apiario_id=filtri['apiario_id'])
            elif entita == 'controlli':
                qs = qs.filter(arnia__apiario_id=filtri['apiario_id'])
            elif entita == 'smielature':
                qs = qs.filter(apiario_id=filtri['apiario_id'])
        if filtri.get('arnia_id') and entita == 'controlli':
            qs = qs.filter(arnia_id=filtri['arnia_id'])
        if filtri.get('tipo_miele') and entita == 'smielature':
            qs = qs.filter(tipo_miele__icontains=filtri['tipo_miele'])
        if filtri.get('razza') and entita == 'regine':
            qs = qs.filter(razza=filtri['razza'])

        totale = qs.count()
        titolo = f"{entita.capitalize()} — {raggruppa_per or 'tutti'}"

        # Gestione aggregazione + raggruppamento
        if aggregazione == 'none' or not raggruppa_per:
            # Restituisci tabella grezza (max 200 righe)
            fields = config['fields']
            rows = list(qs.values(*fields)[:200])
            colonne = fields
            valori_rows = [[str(r.get(f, '')) for f in fields] for r in rows]
            return Response({
                'tipo_visualizzazione': 'table',
                'titolo': titolo,
                'dati': {'labels': [], 'valori': [], 'colonne': colonne, 'righe': valori_rows},
                'totale_righe': totale,
            })

        # Raggruppamento con aggregazione
        try:
            if raggruppa_per == 'mese':
                qs = qs.annotate(gruppo=TruncMonth(date_field))
            elif raggruppa_per == 'anno':
                qs = qs.annotate(gruppo=ExtractYear(date_field))
            else:
                qs = qs.annotate(gruppo=F(raggruppa_per))

            if aggregazione == 'count':
                qs = qs.values('gruppo').annotate(valore=Count('id')).order_by('gruppo')
            elif aggregazione == 'sum':
                # Cerca un campo numerico sensato per il sum
                campo_sum = None
                if entita == 'smielature':
                    campo_sum = 'quantita_miele'
                elif entita == 'vendite':
                    qs = qs.annotate(totale_riga=F('quantita') * F('prezzo_unitario'))
                    campo_sum = 'totale_riga'
                elif entita == 'spese':
                    campo_sum = 'importo'
                if campo_sum:
                    qs = qs.values('gruppo').annotate(valore=Sum(campo_sum)).order_by('gruppo')
                else:
                    qs = qs.values('gruppo').annotate(valore=Count('id')).order_by('gruppo')
            elif aggregazione == 'avg':
                campo_avg = None
                if entita == 'controlli':
                    campo_avg = 'telaini_covata'
                elif entita == 'regine':
                    campo_avg = 'produttivita'
                if campo_avg:
                    qs = qs.values('gruppo').annotate(valore=Avg(campo_avg)).order_by('gruppo')
                else:
                    qs = qs.values('gruppo').annotate(valore=Count('id')).order_by('gruppo')

            labels = [str(r['gruppo']) for r in qs]
            valori = [round(float(r['valore'] or 0), 2) for r in qs]

        except Exception as e:
            return Response({'error': f'Errore elaborazione query: {str(e)}'}, status=400)

        return Response({
            'tipo_visualizzazione': visualizzazione,
            'titolo': titolo,
            'dati': {'labels': labels, 'valori': valori, 'colonne': None},
            'totale_righe': totale,
        })
