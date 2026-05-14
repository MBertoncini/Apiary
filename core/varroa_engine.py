"""
core/varroa_engine.py

Mathematical engine for Varroa destructor population dynamics.

Two-compartment model:
  - Phoretic mites: on adult bees, accessible to acaricide treatments
  - Reproductive mites: in capped brood cells, partially protected

Growth:
  - Daily growth rate ≈ 0.033/day at full brood (doubles every ~21 days)
  - Fraction phoretic: linear 0 frames → 1.0, 10 frames → 0.30
  - Between checkpoints: log-linear interpolation (no model imposed on known data)
  - Beyond last checkpoint: exponential projection at last observed rate

References: Martin (1994), Calis et al. (1999), De Guzman & Rinderer (1999)
"""

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional


class VarroaEngine:
    # ln(2)/21 ≈ 0.033  (population doubles in 21 days at full brood)
    DAILY_GROWTH_RATE_MAX = 0.033

    # With 10 brood frames: ~70% reproductive, ~30% phoretic
    PHORETIC_FRACTION_AT_MAX_BROOD = 0.30
    BROOD_FRAMES_MAX = 10.0

    # month → seasonal alarm thresholds (%, yellow / red)
    _THRESHOLDS: Dict[tuple, Dict[str, float]] = {
        (3, 4, 5, 6, 7, 8): {"giallo": 2.0, "rosso": 3.0},
        (9, 10):            {"giallo": 1.5, "rosso": 2.5},
        (11, 12, 1, 2):     {"giallo": 1.0, "rosso": 2.0},
    }

    def __init__(
        self,
        checkpoints: list,
        ispezioni: list,
        trattamenti: list,
        days_ahead: int = 60,
    ):
        """
        Args:
            checkpoints:  VarroaCheckpoint objects sorted by data_campionamento
            ispezioni:    list of dicts {data: date, telaini_covata: float}
            trattamenti:  TrattamentoSanitario objects (stato in_corso/completato/programmato)
            days_ahead:   days to project beyond today
        """
        self.checkpoints = sorted(checkpoints, key=lambda c: c.data_campionamento)
        self.ispezioni   = sorted(ispezioni, key=lambda i: i["data"])
        self.trattamenti = trattamenti
        self.days_ahead  = days_ahead
        self.today       = date.today()

    # ── Core biophysics ───────────────────────────────────────────────────────

    def fraction_foretica(self, telaini_covata: float) -> float:
        """Phoretic fraction: 0 brood → 1.0; 10 brood → 0.30 (linear)."""
        ratio = min(max(float(telaini_covata or 0), 0), self.BROOD_FRAMES_MAX) / self.BROOD_FRAMES_MAX
        return 1.0 - ratio * (1.0 - self.PHORETIC_FRACTION_AT_MAX_BROOD)

    def daily_growth_rate(self, telaini_covata: float) -> float:
        """Effective daily growth rate proportional to brood availability."""
        f_covata = 1.0 - self.fraction_foretica(telaini_covata)
        return self.DAILY_GROWTH_RATE_MAX * f_covata

    def treatment_kill_fraction(self, trattamento, telaini_covata: float) -> float:
        """
        Fraction of population killed by one treatment application.
        Accounts for phoretic/reproductive split and brood-stop override.
        """
        tipo = trattamento.tipo_trattamento
        eff_f = float(getattr(tipo, "efficacia_foretica",  0.90) or 0.90)
        eff_c = float(getattr(tipo, "efficacia_in_covata", 0.0)  or 0.0)

        # Brood stop → all mites are phoretic
        f_p = 1.0 if trattamento.blocco_covata_attivo else self.fraction_foretica(telaini_covata)
        f_c = 1.0 - f_p
        return eff_f * f_p + eff_c * f_c

    # ── Lookup helpers ────────────────────────────────────────────────────────

    def telaini_at_date(self, target: date) -> float:
        """Nearest-neighbour lookup for brood frames on a given date."""
        if not self.ispezioni:
            return 5.0
        best = min(self.ispezioni, key=lambda i: abs((i["data"] - target).days))
        return float(best.get("telaini_covata") or 5.0)

    def thresholds_for_date(self, dt: date) -> Dict[str, float]:
        m = dt.month
        for months, thr in self._THRESHOLDS.items():
            if m in months:
                return thr
        return {"giallo": 2.0, "rosso": 3.0}

    def _build_treatment_events(self, start: date, end: date) -> Dict[date, float]:
        """
        Map treatment-start-dates to cumulative survival factor.
        Multiple treatments on the same day multiply (independent efficacy assumed).
        """
        events: Dict[date, float] = {}
        valid_stati = {"in_corso", "completato", "programmato"}
        for t in self.trattamenti:
            d = t.data_inizio
            if not (start < d <= end):
                continue
            if t.stato not in valid_stati:
                continue
            kill = self.treatment_kill_fraction(t, self.telaini_at_date(d))
            events[d] = events.get(d, 1.0) * (1.0 - kill)
        return events

    # ── Main entry point ──────────────────────────────────────────────────────

    def compute_trajectory(self) -> Dict[str, Any]:
        """
        Returns:
          {
            trajectory:            [{data, percentuale, tipo, telaini_covata, trattamenti_attivi}],
            trattamenti_nel_range: [{nome, data_inizio, data_fine, metodo, blocco_covata}],
            allarme:               {livello, percentuale_attuale, soglia_gialla, soglia_rossa,
                                    data_prevista_soglia_rossa},
            statistiche:           {n_checkpoints, giorni_dall_ultimo_checkpoint, ...},
          }
        """
        if not self.checkpoints:
            return self._empty_result()

        first_cp  = self.checkpoints[0]
        last_cp   = self.checkpoints[-1]
        chart_end = self.today + timedelta(days=self.days_ahead)
        treatment_events = self._build_treatment_events(first_cp.data_campionamento, chart_end)

        trajectory: List[Dict[str, Any]] = []

        for i, cp in enumerate(self.checkpoints):
            if i < len(self.checkpoints) - 1:
                self._interpolate_segment(trajectory, cp, self.checkpoints[i + 1], treatment_events)
            else:
                # Last checkpoint point
                self._add_point(trajectory, cp.data_campionamento,
                                float(cp.percentuale_calcolata), "checkpoint")
                # Projection forward
                self._project_forward(trajectory, cp, chart_end, treatment_events)

        # Build treatment range list
        chart_start = first_cp.data_campionamento
        trattamenti_nel_range = []
        for t in self.trattamenti:
            if t.data_inizio <= chart_end and (t.data_fine is None or t.data_fine >= chart_start):
                trattamenti_nel_range.append({
                    "nome":          t.tipo_trattamento.nome,
                    "data_inizio":   t.data_inizio.isoformat(),
                    "data_fine":     t.data_fine.isoformat() if t.data_fine else None,
                    "metodo":        t.metodo_applicazione or "",
                    "blocco_covata": t.blocco_covata_attivo,
                })

        return {
            "trajectory":            trajectory,
            "trattamenti_nel_range": trattamenti_nel_range,
            "allarme":               self._compute_allarme(trajectory),
            "statistiche":           self._compute_statistiche(),
        }

    # ── Segment builders ──────────────────────────────────────────────────────

    def _interpolate_segment(self, trajectory, cp0, cp1, treatment_events):
        """Log-linear interpolation between two checkpoints (exclusive of cp1)."""
        p0    = float(cp0.percentuale_calcolata)
        p1    = float(cp1.percentuale_calcolata)
        d0, d1 = cp0.data_campionamento, cp1.data_campionamento
        n_days = (d1 - d0).days
        if n_days <= 0:
            return

        log_p0 = math.log(max(p0, 0.001))
        log_p1 = math.log(max(p1, 0.001))

        current = d0
        while current < d1:
            t_frac = (current - d0).days / n_days
            pct    = math.exp(log_p0 + t_frac * (log_p1 - log_p0))
            tipo   = "checkpoint" if current == d0 else "stima"
            self._add_point(trajectory, current, pct, tipo)
            current += timedelta(days=1)

    def _project_forward(self, trajectory, last_cp, end_date, treatment_events):
        """Exponential projection from last checkpoint using observed/theoretical rate."""
        r           = self._projection_rate(last_cp)
        current_pct = float(last_cp.percentuale_calcolata)
        current     = last_cp.data_campionamento + timedelta(days=1)

        while current <= end_date:
            if current in treatment_events:
                current_pct *= treatment_events[current]
            current_pct = max(current_pct * math.exp(r), 0.001)
            self._add_point(trajectory, current, current_pct, "proiezione")
            current += timedelta(days=1)

    def _add_point(self, trajectory, dt: date, pct: float, tipo: str):
        telaini = self.telaini_at_date(dt)
        trattamenti_attivi = [
            t.tipo_trattamento.nome for t in self.trattamenti
            if t.data_inizio <= dt
            and (t.data_fine is None or t.data_fine >= dt)
            and t.stato in {"in_corso", "completato", "programmato"}
        ]
        trajectory.append({
            "data":               dt.isoformat(),
            "percentuale":        round(pct, 3),
            "tipo":               tipo,
            "telaini_covata":     telaini,
            "trattamenti_attivi": trattamenti_attivi,
        })

    def _projection_rate(self, last_cp) -> float:
        """Last-observed rate or theoretical rate if only one checkpoint."""
        if len(self.checkpoints) >= 2:
            prev  = self.checkpoints[-2]
            days  = (last_cp.data_campionamento - prev.data_campionamento).days
            p0    = float(prev.percentuale_calcolata)
            p1    = float(last_cp.percentuale_calcolata)
            if days > 0 and p0 > 0 and p1 > 0:
                r_obs = math.log(p1 / p0) / days
                return max(min(r_obs, 0.05), -0.005)  # clamp [-0.5%, +5%]/day
        return self.daily_growth_rate(self.telaini_at_date(last_cp.data_campionamento))

    # ── Alarm & statistics ────────────────────────────────────────────────────

    def _compute_allarme(self, trajectory) -> Optional[Dict[str, Any]]:
        if not trajectory:
            return None

        now_str     = self.today.isoformat()
        real_points = [p for p in trajectory if p["data"] <= now_str] or trajectory[:1]
        latest      = real_points[-1]
        pct_now     = latest["percentuale"]
        thresh      = self.thresholds_for_date(date.fromisoformat(latest["data"]))

        if pct_now >= thresh["rosso"]:
            livello = "rosso"
        elif pct_now >= thresh["giallo"]:
            livello = "giallo"
        elif pct_now >= thresh["giallo"] * 0.7:
            livello = "arancione"
        else:
            livello = "verde"

        # First projection day where red threshold is crossed
        data_prevista_rosso = None
        if pct_now < thresh["rosso"]:
            for p in trajectory:
                if p["tipo"] == "proiezione" and p["percentuale"] >= thresh["rosso"]:
                    data_prevista_rosso = p["data"]
                    break

        return {
            "livello":                    livello,
            "percentuale_attuale":        round(pct_now, 2),
            "soglia_gialla":              thresh["giallo"],
            "soglia_rossa":               thresh["rosso"],
            "data_prevista_soglia_rossa": data_prevista_rosso,
        }

    def _compute_statistiche(self) -> Dict[str, Any]:
        if not self.checkpoints:
            return {}
        last_cp     = self.checkpoints[-1]
        giorni_da   = (self.today - last_cp.data_campionamento).days
        tasso       = None
        if len(self.checkpoints) >= 2:
            prev  = self.checkpoints[-2]
            days  = (last_cp.data_campionamento - prev.data_campionamento).days
            p0    = float(prev.percentuale_calcolata)
            p1    = float(last_cp.percentuale_calcolata)
            if days > 0 and p0 > 0:
                tasso = round(math.log(p1 / p0) / days, 4)
        return {
            "n_checkpoints":                     len(self.checkpoints),
            "giorni_dall_ultimo_checkpoint":     giorni_da,
            "ultimo_checkpoint_percentuale":     float(last_cp.percentuale_calcolata),
            "ultimo_checkpoint_data":            last_cp.data_campionamento.isoformat(),
            "tasso_crescita_giornaliero_osservato": tasso,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "trajectory":            [],
            "trattamenti_nel_range": [],
            "allarme":               None,
            "statistiche":           {},
        }
