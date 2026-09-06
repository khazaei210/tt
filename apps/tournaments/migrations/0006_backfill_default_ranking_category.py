from django.db import migrations

DEFAULT_RANKING_CATEGORY_NAME = "Overall"


def backfill_default_ranking_category(apps, schema_editor):
    """Every competition now defaults to the shared 'Overall' ranking
    category automatically (Competition.save()) — this attaches existing
    competitions created before that change too, so their Elo ratings and
    ranking points start counting toward the global board without a manual
    per-competition edit. Elo for matches that already completed before
    this ran doesn't get retroactively computed here (that's a one-off
    operational backfill, not a migration's job) — see apps.rankings.elo.
    """
    RankingCategory = apps.get_model("rankings", "RankingCategory")
    Competition = apps.get_model("tournaments", "Competition")

    category, _created = RankingCategory.objects.get_or_create(
        name=DEFAULT_RANKING_CATEGORY_NAME,
        defaults={"description": "Automatic global ranking across every competition."},
    )
    Competition.objects.filter(ranking_category__isnull=True).update(ranking_category=category)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rankings", "0002_elorating_eloratingevent"),
        ("tournaments", "0005_alter_competition_ranking_category"),
    ]

    operations = [
        migrations.RunPython(backfill_default_ranking_category, noop_reverse),
    ]
