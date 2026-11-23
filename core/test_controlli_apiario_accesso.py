"""Campi dettagliati dei controlli solo sugli apiari accessibili.

/apiari/{id}/controlli/?detail=1 restituisce i campi completi solo se l'apiario
e' dell'utente o condiviso con un suo gruppo; sugli apiari solo pubblici resta
la risposta breve. Gli altri endpoint dei controlli non vedono gli apiari
pubblici altrui.

Eseguire con:  python manage.py test core.test_controlli_apiario_accesso
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Apiario, Arnia, Colonia, ControlloArnia, Gruppo, MembroGruppo


CAMPI_BREVI = {
    'id', 'colonia', 'colonia_id', 'arnia', 'arnia_numero',
    'apiario_nome', 'data', 'telaini_scorte', 'telaini_covata',
    'presenza_regina', 'problemi_sanitari',
}
CAMPI_RISERVATI = {'note', 'note_problemi', 'note_sciamatura', 'utente', 'utente_username'}


class ControlliApiarioAccessoTests(TestCase):

    def setUp(self):
        self.proprietario = User.objects.create_user(
            username='prop_prova', password='x-test-pw-123')
        self.collaboratore = User.objects.create_user(
            username='collab_prova', password='x-test-pw-123')
        self.estraneo = User.objects.create_user(
            username='estraneo_prova', password='x-test-pw-123')

        self.gruppo = Gruppo.objects.create(nome='Gruppo prova', creatore=self.proprietario)
        MembroGruppo.objects.create(
            utente=self.collaboratore, gruppo=self.gruppo, ruolo='viewer')

        # Apiario pubblico sulla mappa e condiviso col gruppo
        self.apiario = Apiario.objects.create(
            nome='Apiario pubblico', proprietario=self.proprietario,
            gruppo=self.gruppo, condiviso_con_gruppo=True,
            visibilita_mappa='pubblico')
        self.arnia = Arnia.objects.create(
            apiario=self.apiario, numero=1, data_installazione=date(2026, 3, 1))
        self.colonia = Colonia.objects.create(
            apiario=self.apiario, arnia=self.arnia, utente=self.proprietario,
            data_inizio=date(2026, 3, 1))
        ControlloArnia.objects.create(
            colonia=self.colonia, arnia=self.arnia, utente=self.proprietario,
            data=timezone.now().date() - timedelta(days=2),
            telaini_scorte=3, telaini_covata=4,
            sciamatura=True, note_sciamatura='testo sciamatura',
            problemi_sanitari=True, note_problemi='testo problemi',
            note='testo note')
        self.url = f'/api/v1/apiari/{self.apiario.pk}/controlli/'

    def _client(self, utente):
        client = APIClient()
        client.force_authenticate(utente)
        return client

    def test_proprietario_riceve_i_campi_completi(self):
        resp = self._client(self.proprietario).get(self.url, {'detail': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['note'], 'testo note')
        self.assertEqual(resp.data[0]['utente_username'], 'prop_prova')

    def test_collaboratore_del_gruppo_riceve_i_campi_completi(self):
        resp = self._client(self.collaboratore).get(self.url, {'detail': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]['note_problemi'], 'testo problemi')
        self.assertEqual(resp.data[0]['note_sciamatura'], 'testo sciamatura')

    def test_estraneo_su_apiario_pubblico_riceve_la_risposta_breve(self):
        for valore in ('1', 'true'):
            resp = self._client(self.estraneo).get(self.url, {'detail': valore})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(resp.data), 1)
            self.assertEqual(set(resp.data[0].keys()), CAMPI_BREVI)
            self.assertFalse(CAMPI_RISERVATI & set(resp.data[0].keys()))

    def test_estraneo_senza_detail_riceve_la_risposta_breve(self):
        resp = self._client(self.estraneo).get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data[0].keys()), CAMPI_BREVI)

    def test_estraneo_su_apiario_privato_non_lo_trova(self):
        self.apiario.visibilita_mappa = 'privato'
        self.apiario.save()
        resp = self._client(self.estraneo).get(self.url, {'detail': '1'})
        self.assertEqual(resp.status_code, 404)

    def test_estraneo_e_gli_altri_endpoint_dei_controlli(self):
        client = self._client(self.estraneo)
        controllo = ControlloArnia.objects.get()
        self.assertEqual(
            client.get(f'/api/v1/arnie/{self.arnia.pk}/controlli/').status_code, 404)
        self.assertEqual(
            client.get(f'/api/v1/colonie/{self.colonia.pk}/controlli/').status_code, 404)
        self.assertEqual(
            client.get(f'/api/v1/controlli/{controllo.pk}/').status_code, 404)
        elenco = client.get('/api/v1/controlli/')
        self.assertEqual(elenco.status_code, 200)
        risultati = elenco.data.get('results', elenco.data) \
            if isinstance(elenco.data, dict) else elenco.data
        self.assertEqual(len(risultati), 0)
