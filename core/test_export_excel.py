"""Test dell'esportazione Excel dei dati utente (GET /api/v1/export/excel/).

Eseguire con:  python manage.py test core.test_export_excel
"""

from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from .models import (
    Alimentazione, Apiario, Arnia, Attrezzatura, Colonia, ControlloArnia,
    DettaglioVendita, Invasettamento, Melario, Pagamento, Regina, Smielatura,
    SmielaturaMelario, SpesaAttrezzatura, TipoTrattamento, TrattamentoSanitario,
    VarroaCheckpoint, Vendita,
)
from .export_excel import SEZIONI

URL = '/api/v1/export/excel/'


def _crea_colonia(apiario, numero):
    arnia = Arnia.objects.create(
        apiario=apiario, numero=numero, data_installazione=date(2026, 3, 1),
    )
    return Colonia.objects.create(
        apiario=apiario, arnia=arnia, utente=apiario.proprietario,
        data_inizio=date(2026, 3, 1),
    )


def _controllo(colonia, data, note=''):
    return ControlloArnia.objects.create(
        colonia=colonia, arnia=colonia.arnia, data=data,
        utente=colonia.utente, telaini_scorte=3, telaini_covata=5, note=note,
    )


class ExportExcelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='x-test-pw-123')
        self.apiario = Apiario.objects.create(nome='Collina', proprietario=self.user)
        self.altro_apiario = Apiario.objects.create(nome='Valle', proprietario=self.user)
        self.colonia = _crea_colonia(self.apiario, 1)
        self.colonia_valle = _crea_colonia(self.altro_apiario, 1)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _workbook(self, **params):
        resp = self.client.get(URL, params)
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return load_workbook(BytesIO(resp.content))

    def _righe(self, ws):
        return list(ws.iter_rows(min_row=2, values_only=True))

    def test_export_completo_contiene_tutti_i_fogli(self):
        _controllo(self.colonia, date(2026, 5, 10))
        wb = self._workbook()
        self.assertEqual(wb.sheetnames[0], 'Riepilogo')
        for nome in ('Apiari', 'Arnie', 'Controlli', 'Trattamenti', 'Vendite', 'Pagamenti'):
            self.assertIn(nome, wb.sheetnames)
        self.assertEqual(len(self._righe(wb['Apiari'])), 2)
        controlli = self._righe(wb['Controlli'])
        self.assertEqual(len(controlli), 1)
        self.assertEqual(controlli[0][1], 'Collina')

    def test_ogni_foglio_con_dati(self):
        """Una riga per ogni sezione: esercita tutti gli accessi ai campi."""
        u, col = self.user, self.colonia
        _controllo(col, date(2026, 5, 10))
        Regina.objects.create(colonia=col, data_introduzione=date(2026, 4, 1))
        tipo = TipoTrattamento.objects.create(nome='ApiBioxal', principio_attivo='Acido ossalico')
        tratt = TrattamentoSanitario.objects.create(
            apiario=self.apiario, tipo_trattamento=tipo, data_inizio=date(2026, 7, 20),
            data_fine=date(2026, 7, 21), utente=u,
        )
        tratt.colonie.add(col)
        VarroaCheckpoint.objects.create(
            colonia=col, data_campionamento=date(2026, 7, 1), metodo='lavaggio_alcolico',
            api_campionate=300, acari_contati=6, utente=u,
        )
        Alimentazione.objects.create(colonia=col, data=date(2026, 9, 1), tipo='candito',
                                     quantita_kg=1, utente=u)
        melario = Melario.objects.create(colonia=col, posizione=1,
                                         data_posizionamento=date(2026, 5, 1))
        smiel = Smielatura.objects.create(data=date(2026, 7, 1), apiario=self.apiario,
                                          quantita_miele=12, tipo_miele='Acacia', utente=u)
        SmielaturaMelario.objects.create(smielatura=smiel, melario=melario)
        Invasettamento.objects.create(data=date(2026, 7, 10), smielatura=smiel,
                                      tipo_miele='Acacia', formato_vasetto=500,
                                      numero_vasetti=10, utente=u)
        vendita = Vendita.objects.create(data=date(2026, 8, 1), utente=u)
        DettaglioVendita.objects.create(vendita=vendita, quantita=2, prezzo_unitario=8)
        Pagamento.objects.create(utente=u, importo=10, data=date(2026, 8, 2), descrizione='Vasetti')
        attr = Attrezzatura.objects.create(nome='Smielatore', proprietario=u)
        SpesaAttrezzatura.objects.create(attrezzatura=attr, descrizione='Acquisto', importo=300,
                                         data=date(2026, 3, 1), utente=u)

        wb = self._workbook(anno=2026)
        for sezione in SEZIONI:
            righe = self._righe(wb[sezione.titolo[0]])
            self.assertTrue(righe, f'foglio {sezione.key} vuoto')
            self.assertEqual(len(righe[0]), len(sezione.colonne), sezione.key)

    def test_filtro_apiario_e_anno(self):
        _controllo(self.colonia, date(2026, 5, 10))
        _controllo(self.colonia, date(2025, 5, 10))
        _controllo(self.colonia_valle, date(2026, 6, 1))
        wb = self._workbook(apiario=self.apiario.id, anno=2026, sezioni='apiari,controlli')
        self.assertEqual(wb.sheetnames, ['Riepilogo', 'Apiari', 'Controlli'])
        self.assertEqual([r[1] for r in self._righe(wb['Apiari'])], ['Collina'])
        controlli = self._righe(wb['Controlli'])
        self.assertEqual(len(controlli), 1)
        self.assertEqual(controlli[0][0].date(), date(2026, 5, 10))

    def test_dati_di_altri_utenti_esclusi(self):
        bob = User.objects.create_user(username='bob', password='x-test-pw-123')
        apiario_bob = Apiario.objects.create(nome='Di Bob', proprietario=bob)
        _controllo(_crea_colonia(apiario_bob, 1), date(2026, 5, 10))
        vendita = Vendita.objects.create(data=date(2026, 7, 1), utente=bob)
        DettaglioVendita.objects.create(vendita=vendita, quantita=2, prezzo_unitario=8)

        wb = self._workbook(sezioni='apiari,controlli,vendite')
        self.assertNotIn('Di Bob', [r[1] for r in self._righe(wb['Apiari'])])
        self.assertEqual(self._righe(wb['Controlli']), [])
        self.assertEqual(self._righe(wb['Vendite']), [])

        resp = self.client.get(URL, {'apiario': apiario_bob.id})
        self.assertEqual(resp.status_code, 404)

    def test_note_con_uguale_non_diventano_formule(self):
        _controllo(self.colonia, date(2026, 5, 10), note='=HYPERLINK("http://x")')
        wb = self._workbook(sezioni='controlli')
        cella = wb['Controlli'].cell(row=2, column=17)
        self.assertEqual(cella.value, '=HYPERLINK("http://x")')
        self.assertEqual(cella.data_type, 's')

    def test_intestazioni_in_inglese(self):
        wb = self._workbook(sezioni='controlli', lang='en')
        self.assertEqual(wb.sheetnames, ['Summary', 'Inspections'])
        self.assertEqual(wb['Inspections'].cell(row=1, column=1).value, 'Date')

    def test_parametri_non_validi(self):
        self.assertEqual(self.client.get(URL, {'sezioni': 'foo'}).status_code, 400)
        self.assertEqual(self.client.get(URL, {'anno': 'xx'}).status_code, 400)
        self.assertEqual(self.client.get(URL, {'apiario': 'xx'}).status_code, 400)

    def test_richiede_autenticazione(self):
        self.assertEqual(APIClient().get(URL).status_code, 401)
