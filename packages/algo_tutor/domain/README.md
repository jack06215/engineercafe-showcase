# algo_tutor/domain

The pure rules of algo_tutor: problem ratings, training levels, review
scheduling, the daily plan, topics, the attempt timer and solution paths.
Nothing here touches the database or the network, so the tests check every
rule with plain values. `plan_harness.py` is an in-memory library for the plan
tests.
