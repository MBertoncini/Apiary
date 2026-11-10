import time

from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ai_services import check_stats_quota, increment_stats_quota
from statistiche.services.groq_service import text_to_sql
from statistiche.services.sql_validator import validate_sql


class NLQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        domanda = request.data.get('domanda', '').strip()
        if not domanda:
            return Response({'error': 'Campo domanda obbligatorio'}, status=400)

        # Chiave Groq personale (opzionale): l'utente paga Groq direttamente,
        # quindi niente limite del tier. Senza, si usa la chiave di sistema e
        # la domanda consuma la quota giornaliera `stats` del piano.
        personal_key = str(request.data.get('groq_api_key') or '').strip()
        if not personal_key:
            allowed, quota_error, tier_limits = check_stats_quota(request.user)
            if not allowed:
                return Response({
                    'error': quota_error,
                    'quota_exceeded': True,
                    'tier_limits': tier_limits,
                }, status=429)

        # 1. Genera SQL con Groq
        try:
            result = text_to_sql(domanda, request.user.id, api_key=personal_key or None)
        except ValueError as e:
            return Response({'error': str(e)}, status=503)
        except TimeoutError:
            return Response({'error': 'Il server AI è lento, riprova tra poco'}, status=504)
        except Exception as e:
            return Response({'error': f'Errore AI: {str(e)}'}, status=503)

        # La chiamata a Groq è andata a buon fine: conta, anche se poi la
        # query generata non è valida (il costo è già stato sostenuto).
        quota_info = {}
        if not personal_key:
            stats_today = increment_stats_quota(request.user)
            if stats_today is not None:
                quota_info = {'stats_today': stats_today}

        sql = result['sql']

        # 2. Valida e sanitizza
        is_valid, sql_or_error = validate_sql(sql)
        if not is_valid:
            return Response({'error': 'Non posso rispondere a questa domanda'}, status=400)

        # 3. Esegui query (MySQL non supporta SET LOCAL statement_timeout)
        t0 = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_or_error)
                if cursor.description is None:
                    return Response({'error': 'La query non ha prodotto risultati leggibili'}, status=400)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(500)
        except Exception as e:
            return Response({'error': f'Errore esecuzione query: {str(e)}'}, status=400)

        elapsed = round(time.time() - t0, 2)
        righe = [dict(zip(columns, row)) for row in rows]

        if not righe:
            return Response({
                'domanda': domanda,
                'messaggio': 'Nessun dato trovato per questa ricerca',
                'colonne': columns,
                'righe': [],
                'totale_righe': 0,
                'tempo_ms': elapsed * 1000,
                **quota_info,
            })

        return Response({
            'domanda': domanda,
            'colonne': columns,
            'righe': righe,
            'totale_righe': len(righe),
            'tempo_ms': elapsed * 1000,
            **quota_info,
        })
