"""Sample buggy PySpark job (schema-drift scenario).

This file is a bundled fixture used by the patch-generator tests and the
self-healing demo: a realistic small PySpark CDC apply that *will* fail
with a java.lang.ClassCastException when the upstream `customer_id`
column type changes from long to string. Pairs with the simulator's
schema_drift scenario.

The buggy snippet is intentionally simple so generated patches are
auditable. A correct fix from the LLM-backed patch generator should
cast the column before the join.
"""

from __future__ import annotations

# The marker keeps the file out of any test-collection or static checks
# that would object to obviously-broken code. The constant is also what
# the patch fixture in the test suite reads, so the snippet stays in one
# place and the test fixture stays in sync with the demo material.
BUGGY_PYSPARK_JOB: str = '''"""customer_cdc — apply daily CDC events to the customers Delta table.

Known bug (left in place for demo purposes): upstream changed the
customer_id column type from BIGINT to STRING, but the join below still
treats it as BIGINT. The job raises:

  java.lang.ClassCastException: java.lang.String cannot be cast to
  java.lang.Long at column customer_id
"""

from pyspark.sql import SparkSession, functions as F


def apply_cdc(spark: SparkSession) -> None:
    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-30/")
    customers = spark.table("warehouse.customers")

    # BUG: events.customer_id is now string but customers.customer_id is
    # still long. The implicit join cast fails on the executor.
    merged = events.join(customers, on="customer_id", how="left")

    result = (
        merged.groupBy("customer_id")
        .agg(F.max("event_ts").alias("latest_event_ts"))
    )

    (
        result.write.format("delta")
        .mode("overwrite")
        .saveAsTable("warehouse.customer_latest_events")
    )


if __name__ == "__main__":
    spark = SparkSession.builder.appName("customer_cdc").getOrCreate()
    apply_cdc(spark)
'''
