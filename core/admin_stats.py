"""Statistiche aggregate mostrate nell'index dell'admin Django."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    Apiario, Arnia, Colonia, ControlloArnia, AnalisiTelaino,
)


def build_admin_stats():
    User = get_user_model()
    now = timezone.now()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    users_qs = User.objects.all()

    users = {
        'total': users_qs.count(),
        'new_7d': users_qs.filter(date_joined__gte=week_ago).count(),
        'new_30d': users_qs.filter(date_joined__gte=month_ago).count(),
        'active_7d': users_qs.filter(last_login__gte=week_ago).count(),
        'never_active': users_qs.filter(last_login__isnull=True).count(),
    }

    domain = {
        'apiari': Apiario.objects.count(),
        'arnie': Arnia.objects.count(),
        'arnie_attive': Arnia.objects.filter(attiva=True).count(),
        'colonie_attive': Colonia.objects.filter(stato='attiva').count(),
        'controlli_total': ControlloArnia.objects.count(),
        'controlli_7d': ControlloArnia.objects.filter(data_creazione__gte=week_ago).count(),
        'analisi_total': AnalisiTelaino.objects.count(),
        'analisi_7d': AnalisiTelaino.objects.filter(data__gte=week_ago.date()).count(),
    }

    growth_labels, growth_users, growth_controlli = [], [], []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        growth_labels.append(day.strftime('%d/%m'))
        growth_users.append(
            users_qs.filter(date_joined__date=day).count()
        )
        growth_controlli.append(
            ControlloArnia.objects.filter(data_creazione__date=day).count()
        )

    top_arnie = list(
        users_qs
        .annotate(n_arnie=Count('apiari_posseduti__arnie', distinct=True))
        .filter(n_arnie__gt=0)
        .order_by('-n_arnie')
        .values('username', 'n_arnie')[:5]
    )

    top_controlli = list(
        users_qs
        .annotate(
            n_controlli=Count(
                'controlloarnia',
                filter=Q(controlloarnia__data_creazione__gte=month_ago),
                distinct=True,
            )
        )
        .filter(n_controlli__gt=0)
        .order_by('-n_controlli')
        .values('username', 'n_controlli')[:5]
    )

    return {
        'users': users,
        'domain': domain,
        'growth': {
            'labels': growth_labels,
            'users': growth_users,
            'controlli': growth_controlli,
        },
        'top_arnie': top_arnie,
        'top_controlli': top_controlli,
    }
