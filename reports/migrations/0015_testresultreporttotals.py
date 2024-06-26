# Generated by Django 4.2.7 on 2024-02-08 21:30

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0014_rename_env_test_flags_hash_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TestResultReportTotals",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("external_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("passed", models.IntegerField()),
                ("skipped", models.IntegerField()),
                ("failed", models.IntegerField()),
                (
                    "report",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reports.commitreport",
                    ),
                ),
            ],
            options={
                "db_table": "reports_testresultreporttotals",
            },
        ),
    ]
