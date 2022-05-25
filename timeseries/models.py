import django.db.models as models


class Measurement(models.Model):
    # TimescaleDB requires that `timestamp` be part of every index (since data is
    # partitioned by `timestamp`).  Since an auto-incrementing primary key would
    # not satisfy this requirement we can make `timestamp` the primary key.
    # `timestamp` may not be unique though so we drop the uniqueness constraint in
    # a migration.
    timestamp = models.DateTimeField(null=False, primary_key=True)

    owner_id = models.BigIntegerField(null=False)
    repo_id = models.BigIntegerField(null=False)
    flag_id = models.BigIntegerField(null=True)
    branch = models.TextField(null=True)

    # useful for updating a measurement if needed
    commit_sha = models.TextField(null=True)

    # the name of the measurement (i.e. "coverage")
    name = models.TextField(null=False, blank=False)
    value = models.FloatField(null=False)

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "owner_id",
                    "repo_id",
                    "flag_id",
                    "branch",
                    "name",
                    "timestamp",
                ]
            ),
            # for updating measurements efficiently
            models.Index(fields=["repo_id", "commit_sha", "timestamp"]),
        ]


class MeasurementSummary(models.Model):
    timestamp_bin = models.DateTimeField(primary_key=True)
    owner_id = models.BigIntegerField()
    repo_id = models.BigIntegerField()
    flag_id = models.BigIntegerField()
    branch = models.TextField()
    name = models.TextField()
    value_avg = models.FloatField()
    value_max = models.FloatField()
    value_min = models.FloatField()
    value_count = models.FloatField()

    @classmethod
    def agg_by(cls, interval):
        model_classes = {
            "1day": MeasurementSummary1Day,
            "7day": MeasurementSummary7Day,
            "30day": MeasurementSummary30Day,
        }

        model_class = model_classes.get(interval)
        if not model_class:
            raise ValueError(f"cannot aggregate by '{interval}'")
        return model_class.objects

    class Meta:
        abstract = True
        # these are backed by TimescaleDB "continuous aggregates"
        # (materialized views)
        managed = False
        ordering = ["timestamp_bin"]


class MeasurementSummary1Day(MeasurementSummary):
    class Meta(MeasurementSummary.Meta):
        db_table = "timeseries_measurement_summary_1day"


# Timescale's origin for time buckets is Monday 2000-01-03
# Weekly aggregate bins will thus be Monday-Sunday
class MeasurementSummary7Day(MeasurementSummary):
    class Meta(MeasurementSummary.Meta):
        db_table = "timeseries_measurement_summary_7day"


# Timescale's origin for time buckets is 2000-01-03
# 30 day offsets will be aligned on that origin
class MeasurementSummary30Day(MeasurementSummary):
    class Meta(MeasurementSummary.Meta):
        db_table = "timeseries_measurement_summary_30day"
