# Generated by Django 3.1.13 on 2022-05-25 20:02

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("timeseries", "0003_cagg_policies"),
    ]

    operations = [
        migrations.CreateModel(
            name="MeasurementSummary1Day",
            fields=[
                (
                    "timestamp_bin",
                    models.DateTimeField(primary_key=True, serialize=False),
                ),
                ("owner_id", models.BigIntegerField()),
                ("repo_id", models.BigIntegerField()),
                ("flag_id", models.BigIntegerField()),
                ("branch", models.TextField()),
                ("name", models.TextField()),
                ("value_avg", models.FloatField()),
                ("value_max", models.FloatField()),
                ("value_min", models.FloatField()),
                ("value_count", models.FloatField()),
            ],
            options={
                "db_table": "timeseries_measurement_summary_1day",
                "ordering": ["timestamp_bin"],
                "abstract": False,
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="MeasurementSummary30Day",
            fields=[
                (
                    "timestamp_bin",
                    models.DateTimeField(primary_key=True, serialize=False),
                ),
                ("owner_id", models.BigIntegerField()),
                ("repo_id", models.BigIntegerField()),
                ("flag_id", models.BigIntegerField()),
                ("branch", models.TextField()),
                ("name", models.TextField()),
                ("value_avg", models.FloatField()),
                ("value_max", models.FloatField()),
                ("value_min", models.FloatField()),
                ("value_count", models.FloatField()),
            ],
            options={
                "db_table": "timeseries_measurement_summary_30day",
                "ordering": ["timestamp_bin"],
                "abstract": False,
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="MeasurementSummary7Day",
            fields=[
                (
                    "timestamp_bin",
                    models.DateTimeField(primary_key=True, serialize=False),
                ),
                ("owner_id", models.BigIntegerField()),
                ("repo_id", models.BigIntegerField()),
                ("flag_id", models.BigIntegerField()),
                ("branch", models.TextField()),
                ("name", models.TextField()),
                ("value_avg", models.FloatField()),
                ("value_max", models.FloatField()),
                ("value_min", models.FloatField()),
                ("value_count", models.FloatField()),
            ],
            options={
                "db_table": "timeseries_measurement_summary_7day",
                "ordering": ["timestamp_bin"],
                "abstract": False,
                "managed": False,
            },
        ),
    ]
