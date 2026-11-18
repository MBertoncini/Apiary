"""Test dei trattamenti sanitari: salvataggio dal web e isolamento tra utenti.

Coprono la issue #2 del repo server:

1. Dalla pagina di un apiario il campo apiario del form web è disabilitato:
   il browser non lo invia e il salvataggio falliva sempre con "campo
   obbligatorio".
2. Il form web elencava gli apiari (e, dopo un errore, le arnie) di tutti
   gli utenti e accettava un apiario altrui.
3. L'API accettava in creazione e modifica un apiario non accessibile.
4. In italiano le date del form di modifica venivano scritte come gg/mm/aaaa
   in un <input type="date">, che le mostra vuote.

Eseguire con:  python manage.py test core.test_trattamenti
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Arnia, TipoTrattamento, TrattamentoSanitario
from .tests import _crea_apiario, _crea_colonia


class _Base(TestCase):
    def setUp(self):
        self.user, self.apiario = _crea_apiario('apicoltore_a', nome='Apiario Proprio')
        self.altro, self.apiario_altrui = _crea_apiario('apicoltore_b', nome='Apiario Altrui')
        self.colonia = _crea_colonia(self.apiario, numero=1)
        self.colonia_altrui = _crea_colonia(self.apiario_altrui, numero=77)
        self.arnia = self.colonia.arnia
        self.arnia_altrui = self.colonia_altrui.arnia
        self.tipo = TipoTrattamento.objects.create(nome='Acido ossalico', tempo_sospensione=0)

    def _dati_form(self, **extra):
        dati = {
            'tipo_trattamento': self.tipo.pk,
            'data_inizio': '2026-11-10',
            'data_fine': '2026-11-20',
            'stato': 'programmato',
            'seleziona_tutte_arnie': 'on',
            'save': '1',
        }
        dati.update(extra)
        return dati


class TrattamentoWebTest(_Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_nuovo_dalla_pagina_apiario_si_salva(self):
        # Il select apiario è disabilitato: il browser non lo invia.
        url = reverse('nuovo_trattamento_apiario', args=[self.apiario.pk])
        resp = self.client.post(url, self._dati_form())
        self.assertEqual(resp.status_code, 302)
        t = TrattamentoSanitario.objects.get()
        self.assertEqual(t.apiario, self.apiario)
        self.assertEqual(t.utente, self.user)

    def test_nuovo_non_elenca_apiari_altrui(self):
        resp = self.client.get(reverse('nuovo_trattamento'))
        self.assertContains(resp, 'Apiario Proprio')
        self.assertNotContains(resp, 'Apiario Altrui')

    def test_errore_di_validazione_non_mostra_dati_altrui(self):
        resp = self.client.post(
            reverse('nuovo_trattamento'),
            self._dati_form(apiario=self.apiario.pk, data_inizio='', seleziona_tutte_arnie=''),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TrattamentoSanitario.objects.exists())
        self.assertNotContains(resp, 'Apiario Altrui')

    def test_nuovo_rifiuta_apiario_altrui(self):
        self.client.post(reverse('nuovo_trattamento'), self._dati_form(apiario=self.apiario_altrui.pk))
        self.assertFalse(TrattamentoSanitario.objects.exists())

    def test_nuovo_rifiuta_arnie_di_altri_apiari(self):
        self.client.post(
            reverse('nuovo_trattamento'),
            self._dati_form(apiario=self.apiario.pk, seleziona_tutte_arnie='',
                            arnie=[self.arnia_altrui.pk]),
        )
        self.assertFalse(TrattamentoSanitario.objects.exists())

    def test_nuovo_senza_apiario_nell_url_si_salva(self):
        resp = self.client.post(
            reverse('nuovo_trattamento'),
            self._dati_form(apiario=self.apiario.pk, seleziona_tutte_arnie='',
                            arnie=[self.arnia.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        t = TrattamentoSanitario.objects.get()
        self.assertEqual(list(t.arnie.all()), [self.arnia])

    def _trattamento(self):
        return TrattamentoSanitario.objects.create(
            apiario=self.apiario, tipo_trattamento=self.tipo, utente=self.user,
            data_inizio=date(2026, 11, 10), data_fine=date(2026, 11, 20))

    def test_modifica_mostra_le_date_in_formato_iso(self):
        t = self._trattamento()
        resp = self.client.get(reverse('modifica_trattamento', args=[t.pk]))
        self.assertContains(resp, 'value="2026-11-10"')
        self.assertContains(resp, 'value="2026-11-20"')
        self.assertNotContains(resp, 'Apiario Altrui')

    def test_modifica_rifiuta_apiario_altrui(self):
        t = self._trattamento()
        self.client.post(
            reverse('modifica_trattamento', args=[t.pk]),
            self._dati_form(apiario=self.apiario_altrui.pk),
        )
        t.refresh_from_db()
        self.assertEqual(t.apiario, self.apiario)


class TrattamentoApiTest(_Base):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.url = '/api/v1/trattamenti/'

    def _payload(self, **extra):
        dati = {
            'apiario': self.apiario.pk,
            'tipo_trattamento': self.tipo.pk,
            'data_inizio': '2026-11-10',
        }
        dati.update(extra)
        return dati

    def test_crea_su_apiario_proprio(self):
        resp = self.api.post(self.url, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_crea_su_apiario_altrui_rifiutato(self):
        resp = self.api.post(self.url, self._payload(apiario=self.apiario_altrui.pk), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(TrattamentoSanitario.objects.exists())
        self.assertNotIn('Apiario Altrui', resp.content.decode())

    def test_crea_con_arnie_altrui_rifiutato(self):
        resp = self.api.post(self.url, self._payload(arnie=[self.arnia_altrui.pk]), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(TrattamentoSanitario.objects.exists())

    def test_crea_con_colonie_altrui_rifiutato(self):
        resp = self.api.post(self.url, self._payload(colonie=[self.colonia_altrui.pk]), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(TrattamentoSanitario.objects.exists())

    def test_modifica_verso_apiario_altrui_rifiutata(self):
        t = TrattamentoSanitario.objects.create(
            apiario=self.apiario, tipo_trattamento=self.tipo, utente=self.user,
            data_inizio=date(2026, 11, 10))
        resp = self.api.patch(f'{self.url}{t.pk}/', {'apiario': self.apiario_altrui.pk}, format='json')
        self.assertEqual(resp.status_code, 400)
        t.refresh_from_db()
        self.assertEqual(t.apiario, self.apiario)

    def test_arnie_filtrate_per_apiario(self):
        # Il form trattamenti dell'app chiede /arnie/?apiario=<id>.
        from .models import Apiario
        secondo = Apiario.objects.create(nome='Secondo', proprietario=self.user)
        _crea_colonia(secondo, numero=2)
        resp = self.api.get(f'/api/v1/arnie/?apiario={self.apiario.pk}')
        self.assertEqual(resp.status_code, 200)
        dati = resp.json()
        righe = dati['results'] if isinstance(dati, dict) else dati
        self.assertEqual([r['id'] for r in righe], [self.arnia.pk])

    def test_viewer_del_gruppo_non_puo_creare(self):
        from .models import Gruppo, MembroGruppo
        gruppo = Gruppo.objects.create(nome='Gruppo', creatore=self.altro)
        MembroGruppo.objects.create(utente=self.altro, gruppo=gruppo, ruolo='admin')
        MembroGruppo.objects.create(utente=self.user, gruppo=gruppo, ruolo='viewer')
        self.apiario_altrui.gruppo = gruppo
        self.apiario_altrui.condiviso_con_gruppo = True
        self.apiario_altrui.save()
        resp = self.api.post(self.url, self._payload(apiario=self.apiario_altrui.pk), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_editor_del_gruppo_puo_creare(self):
        from .models import Gruppo, MembroGruppo
        gruppo = Gruppo.objects.create(nome='Gruppo', creatore=self.altro)
        MembroGruppo.objects.create(utente=self.altro, gruppo=gruppo, ruolo='admin')
        MembroGruppo.objects.create(utente=self.user, gruppo=gruppo, ruolo='editor')
        self.apiario_altrui.gruppo = gruppo
        self.apiario_altrui.condiviso_con_gruppo = True
        self.apiario_altrui.save()
        resp = self.api.post(self.url, self._payload(apiario=self.apiario_altrui.pk), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
