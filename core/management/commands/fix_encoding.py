"""
Management command to fix double UTF-8/Latin-1 encoding corruption in text fields.

Root cause: the Flutter app's http package decoded responses as latin1 instead of
utf8, causing text like "più" to be stored as "Ã¹". If the corrupted text was later
re-synced to the server, it went through the corruption a second time, producing
strings like "Ã\x83Â\xB9".

Fix: repeatedly re-encode as latin1 and decode as utf8 until the string stabilises.
"""

from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models as django_models


def fix_encoding(value):
    """
    Attempt to fix latin1-misinterpreted UTF-8 text.
    Iterates until the string stops changing (handles multiple corruption layers).
    Returns (fixed_value, was_changed).
    """
    if not isinstance(value, str) or not value:
        return value, False

    result = value
    for _ in range(5):
        try:
            candidate = result.encode('latin1').decode('utf8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == result:
            break
        result = candidate

    return result, result != value


class Command(BaseCommand):
    help = 'Fix latin1/utf8 encoding corruption in all text fields across all models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without saving',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Only process this model (e.g. "Regina", "ControlloArnia")',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        target_model = options.get('model')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be saved\n'))

        total_fixed = 0

        for model in apps.get_models():
            if target_model and model.__name__ != target_model:
                continue

            # Collect text fields
            text_fields = [
                f.name
                for f in model._meta.get_fields()
                if isinstance(f, (django_models.CharField, django_models.TextField))
                and not f.primary_key
            ]
            if not text_fields:
                continue

            model_fixed = 0
            for obj in model.objects.all():
                changed_fields = {}
                for field_name in text_fields:
                    raw = getattr(obj, field_name, None)
                    fixed, was_changed = fix_encoding(raw)
                    if was_changed:
                        changed_fields[field_name] = (raw, fixed)

                if changed_fields:
                    model_fixed += 1
                    total_fixed += 1
                    self.stdout.write(
                        f'  {model.__name__} id={obj.pk}:'
                    )
                    for field_name, (old, new) in changed_fields.items():
                        self.stdout.write(f'    {field_name}: {repr(old)} → {repr(new)}')
                        if not dry_run:
                            setattr(obj, field_name, new)
                    if not dry_run:
                        obj.save(update_fields=list(changed_fields.keys()))

            if model_fixed:
                verb = 'Would fix' if dry_run else 'Fixed'
                self.stdout.write(
                    self.style.SUCCESS(f'{verb} {model_fixed} {model.__name__} records')
                )

        if total_fixed == 0:
            self.stdout.write(self.style.SUCCESS('No corrupted records found.'))
        else:
            verb = 'Would fix' if dry_run else 'Fixed'
            self.stdout.write(
                self.style.SUCCESS(f'\nTotal: {verb} {total_fixed} records across all models.')
            )
