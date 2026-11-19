"""Test del form web dei trattamenti sanitari e delle correzioni collegate.

Ricaricamento del form senza salvataggio (cambio tipo o apiario), redirect con
filtro gruppo, URL notifiche sotto /app/, ?detail=1 su /apiari/{id}/controlli/,
eventi regina nel calendario, formato ISO dei campi data.

Eseguire con:  python manage.py test core.test_trattamenti_web
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .forms import VenditaForm
from .models import (
    Apiario, Arnia, Colonia, ControlloArnia, Gruppo, MembroGruppo, Regina,
    StoriaRegine, TipoTrattamento, TrattamentoSanitario, Vendita,
)


class TrattamentoWebFormTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='dario', password='x-test-pw-123')
        self.altro = User.objects.create_user(username='altro', password='x-test-pw-123')
        self.apiario = Apiario.objects.create(nome='Navoi', proprietario=self.user)
        self.apiario_altrui = Apiario.objects.create(nome='Segreto', proprietario=self.altro)
        self.arnia = Arnia.objects.create(
            apiario=self.apiario, numero=1, data_installazione=date(2026, 3, 1))
        self.arnia_altrui = Arnia.objects.create(
            apiario=self.apiario_altrui, numero=7, data_installazione=date(2026, 3, 1))
        self.tipo = TipoTrattamento.objects.create(nome='ApiBioxal', tempo_sospensione=0)
        self.tipo_blocco = TipoTrattamento.objects.create(
            nome='Gabbia', tempo_sospensione=0,
            richiede_blocco_covata=True, giorni_blocco_covata=24)
        self.client.force_login(self.user)

    def _dati(self, **extra):
        dati = {
            'apiario': self.apiario.pk,
            'tipo_trattamento': self.tipo.pk,
            'data_inizio': '2026-11-02',
            'data_fine': '2026-11-03',
            'stato': 'programmato',
            'seleziona_tutte_arnie': 'on',
            'save': '1',
        }
        dati.update(extra)
        return dati

    def _trattamento(self, **extra):
        campi = dict(
            apiario=self.apiario, tipo_trattamento=self.tipo, utente=self.user,
            data_inizio=date(2026, 11, 2), stato='programmato')
        campi.update(extra)
        return TrattamentoSanitario.objects.create(**campi)

    def test_lista_apiari_solo_propri(self):
        resp = self.client.get(reverse('nuovo_trattamento'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Navoi')
        self.assertNotContains(resp, 'Segreto')

    def test_nuovo_propone_la_data_di_oggi(self):
        resp = self.client.get(reverse('nuovo_trattamento'))
        oggi = timezone.now().date().isoformat()
        self.assertContains(resp, f'value="{oggi}"')

    def test_crea_da_pagina_apiario(self):
        """Apiario disabilitato nel form: il POST non lo contiene ma deve salvare."""
        url = reverse('nuovo_trattamento_apiario', args=[self.apiario.pk])
        dati = self._dati()
        del dati['apiario']
        resp = self.client.post(url, dati)
        self.assertEqual(resp.status_code, 302, resp.content.decode()[:2000])
        t = TrattamentoSanitario.objects.get()
        self.assertEqual(t.apiario, self.apiario)
        self.assertEqual(t.utente, self.user)

    def test_crea_da_lista(self):
        resp = self.client.post(reverse('nuovo_trattamento'), self._dati())
        self.assertEqual(resp.status_code, 302, resp.content.decode()[:2000])
        self.assertEqual(TrattamentoSanitario.objects.count(), 1)

    def test_rifiuta_apiario_altrui(self):
        resp = self.client.post(
            reverse('nuovo_trattamento'), self._dati(apiario=self.apiario_altrui.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TrattamentoSanitario.objects.count(), 0)

    def test_rifiuta_arnia_altrui(self):
        dati = self._dati(arnie=[self.arnia_altrui.pk])
        del dati['seleziona_tutte_arnie']
        resp = self.client.post(reverse('nuovo_trattamento'), dati)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TrattamentoSanitario.objects.count(), 0)

    def test_pulsante_salva_porta_save_e_non_c_e_campo_nascosto(self):
        resp = self.client.get(reverse('nuovo_trattamento'))
        self.assertContains(resp, 'name="save" value="1" class="btn btn-primary"')
        self.assertNotContains(resp, '<input type="hidden" name="save"')

    def test_cambio_tipo_ricarica_senza_salvare_ne_errori(self):
        dati = self._dati(data_inizio='')
        del dati['save']
        resp = self.client.post(reverse('nuovo_trattamento'), dati)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TrattamentoSanitario.objects.count(), 0)
        self.assertFalse(resp.context['form'].is_bound)
        self.assertNotContains(resp, 'is-invalid')
        # Le arnie dell'apiario scelto compaiono, quelle altrui no
        arnie = list(resp.context['form'].fields['arnie'].queryset)
        self.assertEqual(arnie, [self.arnia])

    def test_ricarica_con_form_completo_non_salva(self):
        """Prima il campo nascosto save=1 faceva salvare a ogni cambio di tipo."""
        dati = self._dati()
        del dati['save']
        resp = self.client.post(reverse('nuovo_trattamento'), dati)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TrattamentoSanitario.objects.count(), 0)
        # I valori inseriti restano nel form
        self.assertContains(resp, 'value="2026-11-03"')

    def test_ricarica_da_pagina_apiario_mostra_le_arnie(self):
        url = reverse('nuovo_trattamento_apiario', args=[self.apiario.pk])
        dati = self._dati()
        del dati['apiario']
        del dati['save']
        resp = self.client.post(url, dati)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context['form'].fields['arnie'].queryset), [self.arnia])
        self.assertTrue(resp.context['form'].fields['apiario'].disabled)

    def test_cambio_tipo_con_blocco_covata_lo_precompila(self):
        # Il JS della pagina copia data_inizio in data_inizio_blocco: il blocco
        # va attivato lo stesso, tenendo quella data.
        dati = self._dati(tipo_trattamento=self.tipo_blocco.pk, data_inizio_blocco='2026-11-02')
        del dati['save']
        resp = self.client.post(reverse('nuovo_trattamento'), dati)
        form = resp.context['form']
        self.assertTrue(form.initial['blocco_covata_attivo'])
        self.assertEqual(form.initial['data_inizio_blocco'], date(2026, 11, 2))
        self.assertEqual(form.initial['data_fine_blocco'], date(2026, 11, 26))
        self.assertEqual(resp.context['tipo_trattamento_info'], self.tipo_blocco)

    def test_modifica_mostra_data_in_formato_iso(self):
        t = self._trattamento()
        resp = self.client.get(reverse('modifica_trattamento', args=[t.pk]))
        self.assertContains(resp, 'value="2026-11-02"')
        self.assertNotContains(resp, 'Segreto')

    def test_modifica_cambio_tipo_non_salva(self):
        t = self._trattamento()
        dati = self._dati(stato='completato', tipo_trattamento=self.tipo_blocco.pk)
        del dati['save']
        resp = self.client.post(reverse('modifica_trattamento', args=[t.pk]), dati)
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.stato, 'programmato')
        self.assertEqual(t.tipo_trattamento, self.tipo)
        # Il form ricaricato mostra le scelte dell'utente e le info del nuovo tipo
        self.assertEqual(resp.context['tipo_trattamento_info'], self.tipo_blocco)
        self.assertEqual(resp.context['form'].initial['stato'], 'completato')

    def test_modifica_ricarica_tiene_checkbox_tolte(self):
        """Una checkbox tolta non viene inviata: non deve tornare il valore salvato."""
        t = self._trattamento(blocco_covata_attivo=True, data_inizio_blocco=date(2026, 11, 2))
        dati = self._dati()
        del dati['save']
        resp = self.client.post(reverse('modifica_trattamento', args=[t.pk]), dati)
        self.assertFalse(resp.context['form'].initial['blocco_covata_attivo'])

    def test_modifica_salva_con_pulsante(self):
        t = self._trattamento()
        resp = self.client.post(
            reverse('modifica_trattamento', args=[t.pk]), self._dati(stato='in_corso'))
        self.assertEqual(resp.status_code, 302, resp.content.decode()[:2000])
        t.refresh_from_db()
        self.assertEqual(t.stato, 'in_corso')


class RedirectFiltroGruppoTests(TestCase):
    """Prima redirect('gestione_trattamenti?gruppo_id=..') sollevava NoReverseMatch."""

    def setUp(self):
        self.user = User.objects.create_user(username='dario', password='x-test-pw-123')
        self.gruppo = Gruppo.objects.create(nome='Gruppo', creatore=self.user)
        MembroGruppo.objects.create(utente=self.user, gruppo=self.gruppo, ruolo='admin')
        self.apiario = Apiario.objects.create(
            nome='Navoi', proprietario=self.user, gruppo=self.gruppo, condiviso_con_gruppo=True)
        self.tipo = TipoTrattamento.objects.create(nome='ApiBioxal', tempo_sospensione=0)
        self.client.force_login(self.user)

    def _trattamento(self):
        return TrattamentoSanitario.objects.create(
            apiario=self.apiario, tipo_trattamento=self.tipo, utente=self.user,
            data_inizio=date(2026, 11, 2), stato='programmato')

    def _atteso(self):
        return f"{reverse('gestione_trattamenti')}?gruppo_id={self.gruppo.pk}"

    def test_modifica(self):
        t = self._trattamento()
        resp = self.client.post(reverse('modifica_trattamento', args=[t.pk]), {
            'apiario': self.apiario.pk, 'tipo_trattamento': self.tipo.pk,
            'data_inizio': '2026-11-02', 'stato': 'in_corso',
            'seleziona_tutte_arnie': 'on', 'save': '1',
        })
        self.assertRedirects(resp, self._atteso(), fetch_redirect_response=False)

    def test_elimina(self):
        t = self._trattamento()
        resp = self.client.post(reverse('elimina_trattamento', args=[t.pk]))
        self.assertRedirects(resp, self._atteso(), fetch_redirect_response=False)
        self.assertFalse(TrattamentoSanitario.objects.exists())

    def test_cambio_stato(self):
        t = self._trattamento()
        resp = self.client.get(reverse('cambio_stato_trattamento', args=[t.pk, 'completato']))
        self.assertRedirects(resp, self._atteso(), fetch_redirect_response=False)


class NotificheUrlTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='dario', password='x-test-pw-123')
        self.client.force_login(self.user)

    def test_base_passa_al_js_la_url_del_centro_notifiche(self):
        base = reverse('centro_notifiche')
        resp = self.client.get(reverse('gestione_trattamenti'))
        self.assertContains(resp, f'window.APIARY_NOTIFICHE_URLS = {{ base: "{base}" }}')

    def test_le_url_del_js_esistono(self):
        """notifications.js compone le URL dalla base: devono coincidere con urls.py."""
        base = reverse('centro_notifiche')
        self.assertIn('/app/', base)
        self.assertEqual(reverse('notifiche_recenti_api'), base + 'api/recenti/')
        self.assertEqual(reverse('segna_tutte_notifiche_lette'), base + 'segna-tutte-lette/')
        self.assertEqual(reverse('segna_notifica_letta', args=[5]), base + '5/segna-letta/')
        self.assertEqual(reverse('elimina_notifica', args=[5]), base + '5/elimina/')
        resp = self.client.get(base + 'api/recenti/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['non_lette'], 0)


class ControlliApiarioApiTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='dario', password='x-test-pw-123')
        self.apiario = Apiario.objects.create(nome='Navoi', proprietario=self.user)
        arnia = Arnia.objects.create(
            apiario=self.apiario, numero=1, data_installazione=date(2026, 3, 1))
        colonia = Colonia.objects.create(
            apiario=self.apiario, arnia=arnia, utente=self.user, data_inizio=date(2026, 3, 1))
        ControlloArnia.objects.create(
            colonia=colonia, arnia=arnia, utente=self.user,
            data=timezone.now().date() - timedelta(days=2),
            telaini_scorte=3, telaini_covata=4)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/v1/apiari/{self.apiario.pk}/controlli/'

    def test_senza_detail_risposta_breve_invariata(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(set(resp.data[0].keys()), {
            'id', 'colonia', 'colonia_id', 'arnia', 'arnia_numero',
            'apiario_nome', 'data', 'telaini_scorte', 'telaini_covata',
            'presenza_regina', 'problemi_sanitari',
        })

    def test_detail_1_stessi_campi_del_controllo_per_arnia(self):
        resp = self.client.get(self.url, {'detail': '1'})
        self.assertEqual(resp.status_code, 200)
        riga = resp.data[0]
        self.assertEqual(riga['utente_username'], 'dario')
        self.assertEqual(riga['apiario_id'], self.apiario.pk)
        arnia_id = riga['arnia']
        per_arnia = self.client.get(f'/api/v1/arnie/{arnia_id}/controlli/')
        self.assertEqual(set(riga.keys()), set(per_arnia.data[0].keys()))

    def test_detail_valori_non_riconosciuti_danno_la_risposta_breve(self):
        resp = self.client.get(self.url, {'detail': '0'})
        self.assertNotIn('utente_username', resp.data[0])


class CalendarioRegineTests(TestCase):
    """StoriaRegine non ha piu' il campo arnia: il filtro sollevava FieldError."""

    def test_eventi_regina_nel_calendario(self):
        user = User.objects.create_user(username='dario', password='x-test-pw-123')
        apiario = Apiario.objects.create(nome='Navoi', proprietario=user)
        arnia = Arnia.objects.create(
            apiario=apiario, numero=3, data_installazione=date(2026, 3, 1))
        colonia = Colonia.objects.create(
            apiario=apiario, arnia=arnia, utente=user, data_inizio=date(2026, 3, 1))
        regina = Regina.objects.create(colonia=colonia, data_introduzione=date(2026, 5, 10))
        StoriaRegine.objects.create(colonia=colonia, regina=regina, data_inizio=date(2026, 5, 10))
        self.client.force_login(user)
        resp = self.client.get(reverse('calendario_eventi_json'),
                               {'start': '2026-05-01', 'end': '2026-05-31'})
        self.assertEqual(resp.status_code, 200)
        titoli = [e['title'] for e in resp.json()]
        self.assertIn('Nuova Regina - Arnia #3', titoli)


class DateInputIsoTests(TestCase):

    def test_vendita_mostra_la_data_in_formato_iso(self):
        user = User.objects.create_user(username='dario', password='x-test-pw-123')
        vendita = Vendita(utente=user, data=date(2026, 11, 2))
        html = str(VenditaForm(instance=vendita)['data'])
        self.assertIn('value="2026-11-02"', html)
