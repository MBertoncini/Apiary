import datetime
import math

from django.core.cache import cache
from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.db.models.functions import ExtractMonth, ExtractYear, TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Apiario, Arnia, Attrezzatura, CategoriaAttrezzatura,
    ControlloArnia, DettaglioVendita, Fioritura,
    MembroGruppo, Pagamento, QuotaUtente,
    Regina, Smielatura, SpesaAttrezzatura,
    StoriaRegine, TrattamentoSanitario, Vendita,
)
from statistiche.models import DashboardConfig
from statistiche.serializers import DashboardConfigSerializer

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

WIDGET_CATALOG = [
    {'widget_id': 'salute_arnie',          'titolo': 'Salute degli Alveari',       'tipo': 'donut',    'parametri': {'periodo_giorni': 90, 'apiario_id': None}},
    {'widget_id': 'produzione_annuale',    'titolo': 'Produzione Miele per Anno',  'tipo': 'bar',      'parametri': {'anni': 3, 'apiario_id': None}},
    {'widget_id': 'frequenza_controlli',   'titolo': 'Frequenza Controlli',        'tipo': 'heatmap',  'parametri': {'anno': None, 'apiario_id': None}},
    {'widget_id': 'regine_statistiche',    'titolo': 'Mortalità e Sostituzioni Regine', 'tipo': 'bar_kpi', 'parametri': {'anno': None}},
    {'widget_id': 'performance_regine',    'titolo': 'Performance Regine',         'tipo': 'radar',    'parametri': {'apiario_id': None, 'mostra_top_n': 5}},
    {'widget_id': 'varroa_trend',          'titolo': 'Trattamenti Sanitari nel Tempo', 'tipo': 'line', 'parametri': {'periodo_mesi': 12, 'apiario_id': None}},
    {'widget_id': 'bilancio_economico',    'titolo': 'Bilancio Economico',         'tipo': 'bar',      'parametri': {'anno': None}},
    {'widget_id': 'quote_gruppo',          'titolo': 'Quote Gruppo',               'tipo': 'progress', 'parametri': {'gruppo_id': None, 'anno': None}},
    {'widget_id': 'fioriture_vicine',      'titolo': 'Fioriture Vicine',           'tipo': 'map',      'parametri': {'raggio_km': 5}},
    {'widget_id': 'andamento_scorte',      'titolo': 'Andamento Scorte',           'tipo': 'line',     'parametri': {'periodo_mesi': 6, 'apiario_id': None}},
    {'widget_id': 'produzione_per_tipo',   'titolo': 'Produzione per Tipo di Miele', 'tipo': 'pie',   'parametri': {'anno': None}},
    {'widget_id': 'riepilogo_attrezzature','titolo': 'Riepilogo Attrezzature',     'tipo': 'table',    'parametri': {'categoria': None}},
]


def _cache_key(widget_id, user_id, params):
    return f'widget_{widget_id}_{user_id}_{hash(str(sorted(params.items())))}'


def _get_user_apiario_ids(user):
    return list(Apiario.objects.filter(proprietario=user).values_list('id', flat=True))


def _get_user_arnia_ids(user, apiario_id=None):
    qs = Arnia.objects.filter(apiario__proprietario=user, attiva=True)
    if apiario_id:
        qs = qs.filter(apiario_id=apiario_id)
    return list(qs.values_list('id', flat=True))


def _haversine_km(lat1, lon1, lat2, lon2):
    """Distanza in km tra due coordinate (Haversine)."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Widget catalog + Dashboard config
# ---------------------------------------------------------------------------

class WidgetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(WIDGET_CATALOG)


class DashboardConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        config, _ = DashboardConfig.objects.get_or_create(
            utente=request.user,
            defaults={'widget_config': [
                {'widget_id': w['widget_id'], 'posizione': i + 1, 'visibile': True, 'parametri': w['parametri']}
                for i, w in enumerate(WIDGET_CATALOG)
            ]},
        )
        return Response(DashboardConfigSerializer(config).data)

    def put(self, request):
        config, _ = DashboardConfig.objects.get_or_create(utente=request.user)
        serializer = DashboardConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# WIDGET_01 — Salute degli Alveari
# ---------------------------------------------------------------------------

class SaluteArnieView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        periodo_giorni = int(request.query_params.get('periodo_giorni', 90))
        apiario_id = request.query_params.get('apiario_id')
        params = {'periodo_giorni': periodo_giorni, 'apiario_id': apiario_id}
        cached = cache.get(_cache_key('salute_arnie', request.user.id, params))
        if cached:
            return Response(cached)

        arnie_qs = Arnia.objects.filter(apiario__proprietario=request.user, attiva=True)
        if apiario_id:
            arnie_qs = arnie_qs.filter(apiario_id=apiario_id)

        data_soglia = timezone.now().date() - datetime.timedelta(days=periodo_giorni)
        ottima = attenzione = critica = 0
        arnie_critiche = []

        for arnia in arnie_qs.select_related('apiario'):
            ultimo = ControlloArnia.objects.filter(
                arnia=arnia, data__gte=data_soglia
            ).order_by('-data').first()

            if not ultimo:
                critica += 1
                arnie_critiche.append({
                    'id': arnia.id,
                    'numero': arnia.numero,
                    'apiario': arnia.apiario.nome,
                })
            elif not ultimo.presenza_regina or ultimo.problemi_sanitari:
                attenzione += 1
            else:
                ottima += 1

        data = {
            'ottima': ottima,
            'attenzione': attenzione,
            'critica': critica,
            'totale': ottima + attenzione + critica,
            'arnie_critiche': arnie_critiche,
        }
        cache.set(_cache_key('salute_arnie', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_02 — Produzione Miele per Anno
# ---------------------------------------------------------------------------

class ProduzioneAnnualeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        n_anni = int(request.query_params.get('anni', 3))
        apiario_id = request.query_params.get('apiario_id')
        params = {'anni': n_anni, 'apiario_id': apiario_id}
        cached = cache.get(_cache_key('produzione_annuale', request.user.id, params))
        if cached:
            return Response(cached)

        anno_corrente = timezone.now().year
        anni = list(range(anno_corrente - n_anni + 1, anno_corrente + 1))

        qs = Smielatura.objects.filter(
            apiario__proprietario=request.user,
            data__year__in=anni,
        )
        if apiario_id:
            qs = qs.filter(apiario_id=apiario_id)

        per_anno = (
            qs.annotate(anno=ExtractYear('data'))
            .values('anno')
            .annotate(kg=Sum('quantita_miele'))
            .order_by('anno')
        )
        anno_kg = {str(r['anno']): float(r['kg'] or 0) for r in per_anno}

        per_apiario = (
            qs.annotate(anno=ExtractYear('data'))
            .values('anno', 'apiario__nome')
            .annotate(kg=Sum('quantita_miele'))
            .order_by('apiario__nome', 'anno')
        )

        data = {
            'anni': [str(a) for a in anni],
            'kg': [anno_kg.get(str(a), 0) for a in anni],
            'per_apiario': [
                {'apiario': r['apiario__nome'], 'anno': r['anno'], 'kg': float(r['kg'] or 0)}
                for r in per_apiario
            ],
        }
        cache.set(_cache_key('produzione_annuale', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_03 — Frequenza Controlli
# ---------------------------------------------------------------------------

class FrequenzaControlliView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anno = int(request.query_params.get('anno', timezone.now().year))
        apiario_id = request.query_params.get('apiario_id')
        params = {'anno': anno, 'apiario_id': apiario_id}
        cached = cache.get(_cache_key('frequenza_controlli', request.user.id, params))
        if cached:
            return Response(cached)

        arnie_qs = Arnia.objects.filter(apiario__proprietario=request.user, attiva=True)
        if apiario_id:
            arnie_qs = arnie_qs.filter(apiario_id=apiario_id)

        result_arnie = []
        totale_intervalli = []

        for arnia in arnie_qs:
            controlli = list(
                ControlloArnia.objects.filter(arnia=arnia, data__year=anno)
                .order_by('data').values_list('data', flat=True)
            )
            ultimo = controlli[-1] if controlli else None
            if len(controlli) >= 2:
                intervalli = [(controlli[i + 1] - controlli[i]).days for i in range(len(controlli) - 1)]
                media = round(sum(intervalli) / len(intervalli), 1)
            else:
                media = None

            if media is not None:
                totale_intervalli.append(media)

            result_arnie.append({
                'arnia_id': arnia.id,
                'numero': arnia.numero,
                'n_controlli': len(controlli),
                'ultimo_controllo': str(ultimo) if ultimo else None,
                'media_intervallo_giorni': media,
            })

        media_globale = round(sum(totale_intervalli) / len(totale_intervalli), 1) if totale_intervalli else None
        data = {
            'anno': anno,
            'media_giorni_tra_controlli': media_globale,
            'arnie': result_arnie,
        }
        cache.set(_cache_key('frequenza_controlli', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_04 — Mortalità e Sostituzioni Regine
# ---------------------------------------------------------------------------

class RegineStatisticheView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anno = request.query_params.get('anno', timezone.now().year)
        params = {'anno': anno}
        cached = cache.get(_cache_key('regine_statistiche', request.user.id, params))
        if cached:
            return Response(cached)

        arnia_ids = _get_user_arnia_ids(request.user)

        sostituzioni = StoriaRegine.objects.filter(arnia_id__in=arnia_ids)
        if anno:
            sostituzioni = sostituzioni.filter(data_inizio__year=anno)

        per_motivo = (
            sostituzioni.exclude(motivo_fine__isnull=True)
            .values('motivo_fine')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        regine_attive = Regina.objects.filter(arnia_id__in=arnia_ids).count()

        # Calcola durata media vita regine (data_inizio → data_fine in StoriaRegine)
        durata_data = StoriaRegine.objects.filter(
            arnia_id__in=arnia_ids,
            data_fine__isnull=False,
        ).annotate(
            durata=F('data_fine') - F('data_inizio')
        )
        durate = [r.data_fine and ((r.data_fine - r.data_inizio).days / 30.0) for r in durata_data if r.data_fine]
        durata_media = round(sum(durate) / len(durate), 1) if durate else None

        data = {
            'sostituzioni_totali': sostituzioni.count(),
            'per_motivo': [{'motivo': r['motivo_fine'] or 'Non specificato', 'count': r['count']} for r in per_motivo],
            'durata_media_mesi': durata_media,
            'regine_attive': regine_attive,
        }
        cache.set(_cache_key('regine_statistiche', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_05 — Performance Regine
# ---------------------------------------------------------------------------

class PerformanceRegineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        apiario_id = request.query_params.get('apiario_id')
        top_n = int(request.query_params.get('mostra_top_n', 5))
        params = {'apiario_id': apiario_id, 'top_n': top_n}
        cached = cache.get(_cache_key('performance_regine', request.user.id, params))
        if cached:
            return Response(cached)

        qs = Regina.objects.filter(arnia__apiario__proprietario=request.user).select_related('arnia', 'arnia__apiario')
        if apiario_id:
            qs = qs.filter(arnia__apiario_id=apiario_id)

        regine = []
        for r in qs:
            valori = [v for v in [r.docilita, r.produttivita, r.resistenza_malattie, r.tendenza_sciamatura] if v is not None]
            punteggio = round(sum(valori) / len(valori), 2) if valori else 0
            regine.append({
                'id': r.id,
                'codice': r.codice_marcatura or f'Regina #{r.id}',
                'arnia': r.arnia.numero,
                'apiario': r.arnia.apiario.nome,
                'punteggio_medio': punteggio,
                'docilita': r.docilita,
                'produttivita': r.produttivita,
                'resistenza_malattie': r.resistenza_malattie,
                'tendenza_sciamatura': r.tendenza_sciamatura,
            })

        regine.sort(key=lambda x: x['punteggio_medio'], reverse=True)
        data = {'regine': regine[:top_n]}
        cache.set(_cache_key('performance_regine', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_06 — Trattamenti Sanitari nel Tempo (proxy per pressione varroa)
# ---------------------------------------------------------------------------

class VarroaTrendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        periodo_mesi = int(request.query_params.get('periodo_mesi', 12))
        apiario_id = request.query_params.get('apiario_id')
        params = {'periodo_mesi': periodo_mesi, 'apiario_id': apiario_id}
        cached = cache.get(_cache_key('varroa_trend', request.user.id, params))
        if cached:
            return Response(cached)

        data_inizio = timezone.now().date() - datetime.timedelta(days=periodo_mesi * 30)
        qs = TrattamentoSanitario.objects.filter(
            apiario__proprietario=request.user,
            data_inizio__gte=data_inizio,
        )
        if apiario_id:
            qs = qs.filter(apiario_id=apiario_id)

        per_mese_apiario = (
            qs.annotate(mese=TruncMonth('data_inizio'))
            .values('mese', 'apiario__nome')
            .annotate(count=Count('id'))
            .order_by('mese', 'apiario__nome')
        )

        # Raccogli tutti i mesi
        mesi_set = sorted({r['mese'].strftime('%Y-%m') for r in per_mese_apiario if r['mese']})
        apiari_set = sorted({r['apiario__nome'] for r in per_mese_apiario})

        serie = []
        for apiario_nome in apiari_set:
            valori_map = {
                r['mese'].strftime('%Y-%m'): r['count']
                for r in per_mese_apiario
                if r['apiario__nome'] == apiario_nome and r['mese']
            }
            serie.append({'apiario_nome': apiario_nome, 'valori': [valori_map.get(m, 0) for m in mesi_set]})

        data = {'mesi': mesi_set, 'serie': serie}
        cache.set(_cache_key('varroa_trend', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_07 — Bilancio Economico
# ---------------------------------------------------------------------------

class BilancioEconomicoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anno = int(request.query_params.get('anno', timezone.now().year))
        params = {'anno': anno}
        cached = cache.get(_cache_key('bilancio_economico', request.user.id, params))
        if cached:
            return Response(cached)

        # Entrate: DettaglioVendita aggregato per mese
        entrate_qs = (
            DettaglioVendita.objects.filter(vendita__utente=request.user, vendita__data__year=anno)
            .annotate(mese=ExtractMonth('vendita__data'))
            .values('mese')
            .annotate(totale=Sum(F('quantita') * F('prezzo_unitario')))
            .order_by('mese')
        )
        entrate_map = {r['mese']: float(r['totale'] or 0) for r in entrate_qs}

        # Uscite: SpesaAttrezzatura + Pagamento personali (senza destinatario) per mese
        spese_qs = (
            SpesaAttrezzatura.objects.filter(utente=request.user, data__year=anno)
            .annotate(mese=ExtractMonth('data'))
            .values('mese')
            .annotate(totale=Sum('importo'))
            .order_by('mese')
        )
        pagamenti_qs = (
            Pagamento.objects.filter(utente=request.user, destinatario__isnull=True, data__year=anno)
            .annotate(mese=ExtractMonth('data'))
            .values('mese')
            .annotate(totale=Sum('importo'))
            .order_by('mese')
        )
        uscite_map: dict[int, float] = {}
        for r in spese_qs:
            uscite_map[r['mese']] = uscite_map.get(r['mese'], 0) + float(r['totale'] or 0)
        for r in pagamenti_qs:
            uscite_map[r['mese']] = uscite_map.get(r['mese'], 0) + float(r['totale'] or 0)

        mesi_nomi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']
        mesi = list(range(1, 13))
        entrate = [entrate_map.get(m, 0) for m in mesi]
        uscite = [uscite_map.get(m, 0) for m in mesi]
        saldo_mensile = [round(e - u, 2) for e, u in zip(entrate, uscite)]

        data = {
            'anno': anno,
            'mesi': mesi_nomi,
            'entrate': entrate,
            'uscite': uscite,
            'saldo_totale': round(sum(saldo_mensile), 2),
            'saldo_mensile': saldo_mensile,
        }
        cache.set(_cache_key('bilancio_economico', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_08 — Quote Gruppo
# ---------------------------------------------------------------------------

class QuoteGruppoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        gruppo_id = request.query_params.get('gruppo_id')
        anno = int(request.query_params.get('anno', timezone.now().year))

        if not gruppo_id:
            # Restituisci il primo gruppo di cui l'utente è coordinatore
            membro = MembroGruppo.objects.filter(
                utente=request.user, ruolo='admin'
            ).first()
            if not membro:
                return Response({'error': 'Nessun gruppo trovato per questo utente'}, status=404)
            gruppo_id = membro.gruppo_id

        # Verifica che l'utente sia admin del gruppo
        is_admin = MembroGruppo.objects.filter(
            utente=request.user, gruppo_id=gruppo_id, ruolo='admin'
        ).exists()
        if not is_admin:
            return Response({'error': 'Accesso consentito solo ai coordinatori del gruppo'}, status=403)

        params = {'gruppo_id': gruppo_id, 'anno': anno}
        cached = cache.get(_cache_key('quote_gruppo', request.user.id, params))
        if cached:
            return Response(cached)

        membri = MembroGruppo.objects.filter(gruppo_id=gruppo_id).select_related('utente')
        quote = QuotaUtente.objects.filter(gruppo_id=gruppo_id)

        totale_atteso = sum(float(q.percentuale) for q in quote)
        pagamenti = Pagamento.objects.filter(gruppo_id=gruppo_id, data__year=anno)
        totale_raccolto = float(pagamenti.aggregate(t=Sum('importo'))['t'] or 0)

        membri_data = []
        for m in membri:
            quota = quote.filter(utente=m.utente).first()
            pagato = float(pagamenti.filter(utente=m.utente).aggregate(t=Sum('importo'))['t'] or 0)
            atteso = float(quota.percentuale) if quota else 0
            membri_data.append({
                'nome': m.utente.get_full_name() or m.utente.username,
                'importo_atteso': atteso,
                'importo_pagato': pagato,
                'pagato': pagato >= atteso,
            })

        data = {
            'gruppo_id': gruppo_id,
            'totale_atteso': totale_atteso,
            'totale_raccolto': totale_raccolto,
            'percentuale': round(totale_raccolto / totale_atteso * 100, 1) if totale_atteso else 0,
            'membri': membri_data,
        }
        cache.set(_cache_key('quote_gruppo', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_09 — Fioriture Vicine
# ---------------------------------------------------------------------------

class FioritureVicineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        raggio_km = float(request.query_params.get('raggio_km', 5))
        oggi = timezone.now().date()
        params = {'raggio_km': raggio_km}
        cached = cache.get(_cache_key('fioriture_vicine', request.user.id, params))
        if cached:
            return Response(cached)

        apiari = Apiario.objects.filter(
            proprietario=request.user,
            latitudine__isnull=False,
            longitudine__isnull=False,
        )

        fioriture_attive = Fioritura.objects.filter(
            Q(data_fine__isnull=True) | Q(data_fine__gte=oggi),
            data_inizio__lte=oggi,
        )

        risultati = []
        viste = set()

        for apiario in apiari:
            for f in fioriture_attive:
                if f.id in viste:
                    continue
                distanza = _haversine_km(
                    apiario.latitudine, apiario.longitudine,
                    f.latitudine, f.longitudine,
                )
                if distanza <= raggio_km:
                    viste.add(f.id)
                    risultati.append({
                        'id': f.id,
                        'pianta': f.pianta,
                        'distanza_km': round(distanza, 2),
                        'lat': float(f.latitudine),
                        'lng': float(f.longitudine),
                        'intensita': f.intensita,
                        'data_inizio': str(f.data_inizio),
                        'data_fine': str(f.data_fine) if f.data_fine else None,
                        'apiario_vicino': apiario.nome,
                    })

        risultati.sort(key=lambda x: x['distanza_km'])
        data = {'fioriture': risultati[:50]}
        cache.set(_cache_key('fioriture_vicine', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_10 — Andamento Scorte
# ---------------------------------------------------------------------------

class AndamentoScorteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        periodo_mesi = int(request.query_params.get('periodo_mesi', 6))
        apiario_id = request.query_params.get('apiario_id')
        params = {'periodo_mesi': periodo_mesi, 'apiario_id': apiario_id}
        cached = cache.get(_cache_key('andamento_scorte', request.user.id, params))
        if cached:
            return Response(cached)

        data_inizio = timezone.now().date() - datetime.timedelta(days=periodo_mesi * 30)
        arnie_qs = Arnia.objects.filter(apiario__proprietario=request.user, attiva=True)
        if apiario_id:
            arnie_qs = arnie_qs.filter(apiario_id=apiario_id)

        result = []
        for arnia in arnie_qs[:20]:  # limita a 20 arnie per leggibilità
            controlli = (
                ControlloArnia.objects.filter(arnia=arnia, data__gte=data_inizio)
                .order_by('data')
                .values('data', 'telaini_scorte')
            )
            if controlli:
                result.append({
                    'arnia_id': arnia.id,
                    'numero': arnia.numero,
                    'dati': [{'data': str(c['data']), 'valore': c['telaini_scorte']} for c in controlli],
                })

        data = {'arnie': result}
        cache.set(_cache_key('andamento_scorte', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_11 — Produzione per Tipo di Miele
# ---------------------------------------------------------------------------

class ProduzionePerTipoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anno = request.query_params.get('anno', timezone.now().year)
        params = {'anno': anno}
        cached = cache.get(_cache_key('produzione_per_tipo', request.user.id, params))
        if cached:
            return Response(cached)

        qs = Smielatura.objects.filter(apiario__proprietario=request.user)
        if anno:
            qs = qs.filter(data__year=anno)

        per_tipo = (
            qs.values('tipo_miele')
            .annotate(kg=Sum('quantita_miele'))
            .order_by('-kg')
        )

        totale = sum(float(r['kg'] or 0) for r in per_tipo)
        tipi = [
            {
                'tipo_miele': r['tipo_miele'] or 'Non specificato',
                'kg': round(float(r['kg'] or 0), 2),
                'percentuale': round(float(r['kg'] or 0) / totale * 100, 1) if totale else 0,
            }
            for r in per_tipo
        ]

        data = {'anno': anno, 'tipi': tipi, 'totale_kg': round(totale, 2)}
        cache.set(_cache_key('produzione_per_tipo', request.user.id, params), data, timeout=300)
        return Response(data)


# ---------------------------------------------------------------------------
# WIDGET_12 — Riepilogo Attrezzature
# ---------------------------------------------------------------------------

class RiepilogoAttrezzatureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categoria = request.query_params.get('categoria')
        params = {'categoria': categoria}
        cached = cache.get(_cache_key('riepilogo_attrezzature', request.user.id, params))
        if cached:
            return Response(cached)

        qs = Attrezzatura.objects.filter(proprietario=request.user)
        if categoria:
            qs = qs.filter(categoria__nome__icontains=categoria)

        per_categoria = (
            qs.values('categoria__nome')
            .annotate(count=Count('id'), valore_totale=Sum('prezzo_acquisto'))
            .order_by('categoria__nome')
        )

        valore_inventario = float(
            qs.aggregate(t=Sum('prezzo_acquisto'))['t'] or 0
        )

        data = {
            'per_categoria': [
                {
                    'categoria': r['categoria__nome'] or 'Senza categoria',
                    'count': r['count'],
                    'valore_totale': round(float(r['valore_totale'] or 0), 2),
                }
                for r in per_categoria
            ],
            'valore_totale_inventario': round(valore_inventario, 2),
        }
        cache.set(_cache_key('riepilogo_attrezzature', request.user.id, params), data, timeout=300)
        return Response(data)
