from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from statistiche.services.excel_service import genera_excel
from statistiche.services.pdf_service import genera_pdf


class ExportExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        titolo = request.data.get('titolo', 'Export')
        colonne = request.data.get('colonne', [])
        righe = request.data.get('righe', [])

        if not colonne:
            from rest_framework.response import Response
            return Response({'error': 'Colonne obbligatorie'}, status=400)

        try:
            excel_bytes = genera_excel(titolo, colonne, righe)
        except Exception as e:
            from rest_framework.response import Response
            return Response({'error': f'Errore generazione Excel: {str(e)}'}, status=500)

        filename = titolo.replace(' ', '_')[:50] + '.xlsx'
        response = HttpResponse(
            excel_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        titolo = request.data.get('titolo', 'Export')
        colonne = request.data.get('colonne', [])
        righe = request.data.get('righe', [])

        try:
            pdf_bytes = genera_pdf(titolo, colonne, righe)
        except Exception as e:
            from rest_framework.response import Response
            return Response({'error': f'Errore generazione PDF: {str(e)}'}, status=500)

        filename = titolo.replace(' ', '_')[:50] + '.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
