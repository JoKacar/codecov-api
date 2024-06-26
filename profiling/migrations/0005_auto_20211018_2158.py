# Generated by Django 3.1.13 on 2021-10-18 21:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("profiling", "0004_auto_20211011_2047")]

    operations = [
        migrations.AddField(
            model_name="profilingcommit", name="code", field=models.TextField(null=True)
        ),
        migrations.AddConstraint(
            model_name="profilingcommit",
            constraint=models.UniqueConstraint(
                fields=("repository", "code"), name="uniquerepocode"
            ),
        ),
    ]
