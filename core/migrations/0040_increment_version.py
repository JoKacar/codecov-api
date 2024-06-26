# Generated by Django 4.2.7 on 2023-12-04 21:13

from django.db import migrations


def update_version(apps, schema):
    Constants = apps.get_model("core", "Constants")
    version = Constants.objects.get(key="version")
    version.value = "23.12.4"
    version.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_pull_pulls_repoid_id"),
    ]

    operations = [migrations.RunPython(update_version)]
