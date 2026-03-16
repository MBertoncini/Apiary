import time

from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from statistiche.services.groq_service import text_to_sql
from statistiche.services.sql_validator import validate_sql


class NLQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        domanda = request.data.get('domanda', '').strip()
        if not domanda:
            return Response({'error': 'Campo domanda obbligatorio'}, status=400)

        # 1. Genera SQL con Groq
        try:
            result = text_to_sql(domanda, request.user.id)
        except ValueError as e:
            return Response({'error': str(e)}, status=503)
        except TimeoutError:
            return Response({'error': 'Il server AI è lento, riprova tra poco'}, status=504)
        except Exception as e:
            return Response({'error': f'Errore AI: {str(e)}'}, status=503)

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
            })

        return Response({
            'domanda': domanda,
            'colonne': columns,
            'righe': righe,
            'totale_righe': len(righe),
            'tempo_ms': elapsed * 1000,
        })
