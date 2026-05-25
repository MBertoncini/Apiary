"""Honest backtest of the rule-based predictive baselines against real events.

For each target we walk colony history, score risk using only past-and-present
data, and compare against the real outcome — reporting discrimination (AUC) and
operating-point metrics versus naive baselines and the base rate, so we never
overstate what the model knows on scarce data. The rule baselines have nothing
to fit, so this is plain evaluation; switch to leave-one-colony-out once a fitted
layer exists.

    python manage.py backtest_models [--target swarm|wintering|all]
                                     [--horizon-days 28] [--alarm-score 45]
                                     [--winter-window 180] [--winter-alarm 35]
"""

from django.core.management.base import BaseCommand

from core.models import Colonia
from core.ml.dataset import build_colonia_dataset
from core.ml.features import (
    colony_feature_frame, attach_swarm_labels, wintering_label, AUTUMN_MONTHS,
)
from core.ml.models import swarm, wintering, production


class Command(BaseCommand):
    help = 'Backtest onesto dei baseline predittivi contro gli eventi reali.'

    def add_arguments(self, parser):
        parser.add_argument('--target',
                            choices=['swarm', 'wintering', 'production', 'all'],
                            default='all')
        parser.add_argument('--horizon-days', type=int, default=28,
                            help='[swarm] Finestra entro cui contare una sciamatura.')
        parser.add_argument('--alarm-score', type=int, default=45,
                            help='[swarm] Soglia di alert (alto/critico).')
        parser.add_argument('--winter-window', type=int, default=180,
                            help='[wintering] Giorni dopo lo snapshot per esito invernale.')
        parser.add_argument('--winter-alarm', type=int, default=35,
                            help='[wintering] Soglia di alert (alto/critico).')

    def handle(self, *args, **options):
        target = options['target']
        colonie = list(Colonia.objects.all().select_related('apiario'))
        datasets = [(c, build_colonia_dataset(c)) for c in colonie]

        if target in ('swarm', 'all'):
            self._run_swarm(datasets, options['horizon_days'], options['alarm_score'])
        if target in ('wintering', 'all'):
            if target == 'all':
                self.stdout.write('')
            self._run_wintering(datasets, options['winter_window'], options['winter_alarm'])
        if target in ('production', 'all'):
            if target == 'all':
                self.stdout.write('')
            self._run_production(datasets)

    # ── Swarm ────────────────────────────────────────────────────────────────
    def _run_swarm(self, datasets, horizon, alarm):
        scores, labels, naive = [], [], []
        n_colonies = 0
        for _, dataset in datasets:
            rows = colony_feature_frame(dataset)
            if not rows:
                continue
            attach_swarm_labels(rows, horizon_days=horizon)
            n_colonies += 1
            for i, row in enumerate(rows):
                if row.get('label_censored'):
                    continue
                result = swarm.assess(row, n_controls=i + 1, days_since_last_control=0)
                if result['score'] is None:
                    continue
                scores.append(result['score'])
                labels.append(bool(row['swarm_within_horizon']))
                naive.append(bool(row.get('in_swarm_season')))

        self._report(
            'rischio sciamatura', scores, labels, n_colonies, alarm,
            extra=(f'orizzonte {horizon}gg',),
            naives=[('solo-stagione  ', naive), ('sempre-positivo', [True] * len(scores))],
        )

    # ── Wintering ──────────────────────────────────────────────────────────────
    def _run_wintering(self, datasets, window, alarm):
        scores, labels, naive = [], [], []
        n_colonies = 0
        for _, dataset in datasets:
            rows = colony_feature_frame(dataset)
            if not rows:
                continue
            # One autumn snapshot per year (latest autumn control of each year).
            autumn_by_year = {}
            for r in rows:
                if r['month'] in AUTUMN_MONTHS:
                    autumn_by_year[r['iso_year']] = r  # rows date-ordered -> keeps latest
            if not autumn_by_year:
                continue
            counted = False
            for r in autumn_by_year.values():
                died, censored = wintering_label(dataset, r['data'], window_days=window)
                if censored:
                    continue
                result = wintering.assess(r, is_autumn=True)
                if result['score'] is None:
                    continue
                scores.append(result['score'])
                labels.append(bool(died))
                v = r.get('varroa_pct_latest')
                naive.append(v is not None and v > 3)
                counted = True
            if counted:
                n_colonies += 1

        self._report(
            'rischio invernamento', scores, labels, n_colonies, alarm,
            extra=(f'finestra {window}gg',),
            naives=[('varroa>3%      ', naive), ('sempre-positivo', [True] * len(scores))],
        )

    # ── Production (regression, pooled leave-one-out) ────────────────────────
    def _run_production(self, datasets):
        # Pool all colony-harvest observations across colonies (anonymised by id).
        pool = []
        for colonia, dataset in datasets:
            for o in production.production_observations(dataset):
                pool.append({'colony': colonia.id, 'kg': o['kg'], 'potential': o['potential']})

        self.stdout.write(self.style.SUCCESS('── Backtest produzione miele ──'))
        n = len(pool)
        if n == 0:
            self.stdout.write(self.style.WARNING(
                'Nessun raccolto con kg attribuiti e potenziale > 0: '
                'impossibile valutare. Servono smielature con kg_miele e fioriture.'
            ))
            return

        global_mean = sum(p['kg'] for p in pool) / n
        n_colonies = len({p['colony'] for p in pool})

        model_abs, model_sq = [], []
        naive_g_abs, naive_c_abs = [], []
        for i, p in enumerate(pool):
            others = pool[:i] + pool[i + 1:]
            alpha, _ = production.calibrate_alpha(
                [{'potential': o['potential'], 'kg': o['kg']} for o in others]
            )
            pred = alpha * p['potential']
            err = pred - p['kg']
            model_abs.append(abs(err))
            model_sq.append(err * err)
            gm = (sum(o['kg'] for o in others) / len(others)) if others else global_mean
            naive_g_abs.append(abs(gm - p['kg']))
            same = [o['kg'] for o in others if o['colony'] == p['colony']]
            cm = (sum(same) / len(same)) if same else gm
            naive_c_abs.append(abs(cm - p['kg']))

        mae = sum(model_abs) / n
        rmse = (sum(model_sq) / n) ** 0.5
        self.stdout.write(f'Colonie con raccolti ..... {n_colonies}')
        self.stdout.write(f'Raccolti valutati (LOO) .. {n}')
        self.stdout.write(f'kg medio (pool) .......... {global_mean:.1f}')
        self.stdout.write(f'MAE modello .............. {mae:.2f} kg')
        self.stdout.write(f'RMSE modello ............. {rmse:.2f} kg')
        self.stdout.write('\nConfronto MAE con baseline ingenue (più basso è meglio):')
        self.stdout.write(f'  media globale .......... {sum(naive_g_abs) / n:.2f} kg')
        self.stdout.write(f'  media colonia .......... {sum(naive_c_abs) / n:.2f} kg')
        if n < 5:
            self.stdout.write(self.style.WARNING(
                'Pochi raccolti: le metriche sono indicative. '
                'Il valore cresce con lo storico (pooling cross-colonia).'
            ))

    # ── Shared reporting ─────────────────────────────────────────────────────
    def _report(self, title, scores, labels, n_colonies, alarm, extra=(), naives=()):
        self.stdout.write(self.style.SUCCESS(f'── Backtest {title} ──'))
        n = len(scores)
        if n == 0:
            self.stdout.write(self.style.WARNING(
                'Nessuna osservazione valutabile (follow-up insufficiente).'
            ))
            return

        n_pos = sum(labels)
        self.stdout.write(f'Colonie valutate ......... {n_colonies}')
        self.stdout.write(f'Osservazioni ............. {n}' +
                          (f'  ({", ".join(extra)})' if extra else ''))
        self.stdout.write(f'Eventi positivi .......... {n_pos}  (base rate {n_pos / n:.1%})')

        if n_pos == 0:
            self.stdout.write(self.style.WARNING(
                'Zero eventi etichettati: dati insufficienti per misurare la qualità. '
                'Il baseline resta valido per via delle regole apistiche; '
                'rivalutare quando si accumulano eventi reali.'
            ))
            return

        auc = self._auc(scores, labels)
        self.stdout.write(f'AUC (discriminazione) .... '
                          f'{f"{auc:.3f}" if auc is not None else "n/d (una sola classe)"}')
        self.stdout.write(f'\nPunto operativo @ score>={alarm} (livello alto/critico):')
        self._print_confusion('  baseline regole', [s >= alarm for s in scores], labels)
        if naives:
            self.stdout.write('\nConfronto con baseline ingenue:')
            for name, preds in naives:
                self._print_confusion(f'  {name}', preds, labels)

    @staticmethod
    def _auc(scores, labels):
        pos = [s for s, l in zip(scores, labels) if l]
        neg = [s for s, l in zip(scores, labels) if not l]
        if not pos or not neg:
            return None
        wins = 0.0
        for p in pos:
            for q in neg:
                wins += 1 if p > q else (0.5 if p == q else 0)
        return wins / (len(pos) * len(neg))

    def _print_confusion(self, name, preds, labels):
        tp = sum(1 for p, l in zip(preds, labels) if p and l)
        fp = sum(1 for p, l in zip(preds, labels) if p and not l)
        fn = sum(1 for p, l in zip(preds, labels) if not p and l)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        self.stdout.write(
            f'{name}: prec {precision:.2f}  rec {recall:.2f}  F1 {f1:.2f}  '
            f'(TP {tp}, FP {fp}, FN {fn})'
        )
