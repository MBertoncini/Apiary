"""Peso dell'arnia nei controlli (inserimento manuale).

ControlloArnia.peso_kg e' facoltativo; l'API espone anche peso_differenza_kg,
la differenza dal controllo precedente (per data) della stessa arnia che ha un
peso. Le versioni dell'app che non conoscono il campo continuano a funzionare.

Eseguire con:  python manage.py test core.test_peso_controlli
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .forms import ControlloArniaForm
from .models import Apiario, Arnia, Colonia, ControlloArnia


class PesoControlliBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='utente_prova', password='x-test-pw-123')
        self.apiario = Apiario.objects.create(nome='Apiario Uno', proprietario=self.user)
        self.arnia = Arnia.objects.create(
            apiario=self.apiario, numero=1, data_installazione=date(2026, 3, 1))
        self.colonia = Colonia.objects.create(
            apiario=self.apiario, arnia=self.arnia, utente=self.user,
            data_inizio=date(2026, 3, 1))
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def _controllo(self, data, peso=None, arnia=None):
        arnia = arnia or self.arnia
        return ControlloArnia.objects.create(
            colonia=self.colonia if arnia == self.arnia else None,
            arnia=arnia, utente=self.user, data=data,
            telaini_scorte=3, telaini_covata=4,
            peso_kg=None if peso is None else Decimal(peso))

    def _api_controllo(self, controllo):
        resp = self.api.get(f'/api/v1/controlli/{controllo.pk}/')
        self.assertEqual(resp.status_code, 200)
        return resp.data


class PesoDifferenzaTests(PesoControlliBase):

    def test_primo_controllo_senza_precedente(self):
        c = self._controllo(date(2026, 5, 1), '30.00')
        self.assertIsNone(c.peso_differenza_kg)
        self.assertIsNone(self._api_controllo(c)['peso_differenza_kg'])

    def test_differenza_col_precedente(self):
        self._controllo(date(2026, 5, 1), '30.00')
        c2 = self._controllo(date(2026, 5, 8), '31.20')
        self.assertEqual(c2.peso_differenza_kg, Decimal('1.20'))
        dati = self._api_controllo(c2)
        self.assertEqual(dati['peso_kg'], '31.20')
        self.assertEqual(dati['peso_differenza_kg'], '1.20')

    def test_calo_di_peso_negativo(self):
        self._controllo(date(2026, 5, 1), '30.00')
        c2 = self._controllo(date(2026, 5, 8), '28.50')
        self.assertEqual(self._api_controllo(c2)['peso_differenza_kg'], '-1.50')

    def test_precedente_senza_peso_saltato(self):
        self._controllo(date(2026, 5, 1), '30.00')
        intermedio = self._controllo(date(2026, 5, 5))
        c3 = self._controllo(date(2026, 5, 10), '32.00')
        self.assertEqual(self._api_controllo(c3)['peso_differenza_kg'], '2.00')
        # Senza peso non c'e' differenza
        self.assertIsNone(self._api_controllo(intermedio)['peso_differenza_kg'])

    def test_calcolo_per_data_non_per_id(self):
        # Inserito prima (id minore) ma con data successiva
        tardo = self._controllo(date(2026, 5, 10), '35.00')
        presto = self._controllo(date(2026, 5, 1), '30.00')
        self.assertLess(tardo.pk, presto.pk)
        self.assertEqual(self._api_controllo(tardo)['peso_differenza_kg'], '5.00')
        self.assertIsNone(self._api_controllo(presto)['peso_differenza_kg'])

    def test_stessa_data_vale_l_ordine_di_inserimento(self):
        self._controllo(date(2026, 5, 1), '30.00')
        secondo = self._controllo(date(2026, 5, 1), '30.40')
        self.assertEqual(self._api_controllo(secondo)['peso_differenza_kg'], '0.40')

    def test_altre_arnie_non_contano(self):
        altra = Arnia.objects.create(
            apiario=self.apiario, numero=2, data_installazione=date(2026, 3, 1))
        self._controllo(date(2026, 5, 1), '20.00', arnia=altra)
        c = self._controllo(date(2026, 5, 8), '30.00')
        self.assertIsNone(self._api_controllo(c)['peso_differenza_kg'])

    def test_elenchi_con_annotazione_danno_lo_stesso_risultato(self):
        self._controllo(date(2026, 5, 1), '30.00')
        self._controllo(date(2026, 5, 5))
        c3 = self._controllo(date(2026, 5, 10), '29.75')
        attesi = {c3.pk: '-0.25'}

        risposte = [
            self.api.get(f'/api/v1/arnie/{self.arnia.pk}/controlli/', {'days': 100000}).data,
            self.api.get(f'/api/v1/colonie/{self.colonia.pk}/controlli/').data,
            self.api.get(f'/api/v1/apiari/{self.apiario.pk}/controlli/',
                         {'detail': '1', 'days': 100000}).data,
        ]
        for elenco in risposte:
            self.assertEqual(len(elenco), 3)
            for riga in elenco:
                self.assertEqual(riga['peso_differenza_kg'], attesi.get(riga['id']))

    def test_poche_query_per_l_elenco(self):
        for giorno in range(1, 11):
            self._controllo(date(2026, 5, giorno), str(30 + giorno))
        url = f'/api/v1/arnie/{self.arnia.pk}/controlli/'
        # Una query per i controlli, piu' quelle fisse di autenticazione/arnia:
        # il peso precedente non deve costare una query per riga.
        with self.assertNumQueries(2):
            resp = self.api.get(url, {'days': 100000})
        self.assertEqual(resp.data[0]['peso_differenza_kg'], '1.00')


class PesoApiTests(PesoControlliBase):

    def _payload(self, **extra):
        # Stesso payload delle versioni dell'app che non conoscono il peso
        dati = {
            'colonia': self.colonia.pk, 'arnia': self.arnia.pk,
            'data': '2026-05-01', 'telaini_scorte': 3, 'telaini_covata': 4,
            'presenza_regina': True,
        }
        dati.update(extra)
        return dati

    def test_creazione_senza_peso_come_le_app_attuali(self):
        resp = self.api.post('/api/v1/controlli/', self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(resp.data['peso_kg'])
        self.assertIsNone(resp.data['peso_differenza_kg'])
        self.assertIsNone(ControlloArnia.objects.get().peso_kg)

    def test_creazione_con_peso(self):
        self._controllo(date(2026, 4, 20), '30.00')
        resp = self.api.post('/api/v1/controlli/', self._payload(peso_kg='31.25'), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['peso_kg'], '31.25')
        self.assertEqual(resp.data['peso_differenza_kg'], '1.25')
        self.assertEqual(ControlloArnia.objects.get(pk=resp.data['id']).peso_kg, Decimal('31.25'))

    def test_peso_null_accettato(self):
        resp = self.api.post('/api/v1/controlli/', self._payload(peso_kg=None), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(resp.data['peso_kg'])

    def test_peso_negativo_rifiutato(self):
        resp = self.api.post('/api/v1/controlli/', self._payload(peso_kg='-1'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('peso_kg', resp.data)

    def test_differenza_in_sola_lettura(self):
        resp = self.api.post('/api/v1/controlli/',
                             self._payload(peso_kg='30', peso_differenza_kg='99'), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(resp.data['peso_differenza_kg'])

    def test_modifica_senza_peso_non_lo_cancella(self):
        c = self._controllo(date(2026, 5, 1), '30.00')
        resp = self.api.patch(f'/api/v1/controlli/{c.pk}/', {'note': 'aggiornato'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        c.refresh_from_db()
        self.assertEqual(c.peso_kg, Decimal('30.00'))

    def test_modifica_della_data_ricalcola_la_differenza(self):
        self._controllo(date(2026, 5, 1), '30.00')
        self._controllo(date(2026, 5, 10), '33.00')
        c = self._controllo(date(2026, 5, 20), '34.00')
        resp = self.api.patch(f'/api/v1/controlli/{c.pk}/', {'data': '2026-05-05'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['peso_differenza_kg'], '4.00')


class PesoWebTests(PesoControlliBase):

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _post(self, **extra):
        dati = {
            'data': '2026-05-08', 'telaini_scorte': 3, 'telaini_covata': 4,
            'presenza_regina': 'on', 'note': '',
        }
        dati.update(extra)
        return self.client.post(reverse('nuovo_controllo', args=[self.arnia.pk]), dati)

    def test_form_salva_senza_peso(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(ControlloArnia.objects.get().peso_kg)

    def test_form_salva_con_peso(self):
        resp = self._post(peso_kg='31.20')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ControlloArnia.objects.get().peso_kg, Decimal('31.20'))

    def test_form_rifiuta_peso_negativo(self):
        form = ControlloArniaForm(data={
            'data': '2026-05-08', 'telaini_scorte': 3, 'telaini_covata': 4,
            'peso_kg': '-2',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('peso_kg', form.errors)

    def test_form_mostra_il_campo(self):
        resp = self.client.get(reverse('nuovo_controllo', args=[self.arnia.pk]))
        self.assertContains(resp, 'name="peso_kg"')

    def test_modifica_conserva_il_peso(self):
        c = self._controllo(date(2026, 5, 1), '30.00')
        resp = self.client.get(reverse('modifica_controllo', args=[c.pk]))
        self.assertContains(resp, 'value="30.00"')

    def test_pagina_apiario_mostra_peso_e_differenza(self):
        self._controllo(date(2026, 5, 1), '30.00')
        self._controllo(date(2026, 5, 8), '31.20')
        resp = self.client.get(reverse('visualizza_apiario', args=[self.apiario.pk]))
        self.assertEqual(resp.status_code, 200)
        testo = resp.content.decode()
        self.assertRegex(testo, r'31[.,]20 kg')
        self.assertRegex(testo, r'\(\+1[.,]20 kg\)')

    def test_pagina_apiario_senza_peso_non_mostra_nulla(self):
        self._controllo(date(2026, 5, 8))
        resp = self.client.get(reverse('visualizza_apiario', args=[self.apiario.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'arnia-peso')
