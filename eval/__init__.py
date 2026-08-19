"""An evaluation harness for InfiniteAgent over public long-context benchmarks.

The scaffold's premise is that a fixed, small active context can do work whose
material is arbitrarily larger than it. The reconstruct task tests that on one
job; this tests it on published benchmarks whose ground truth someone else
established, at lengths the context could not hold under any configuration.
"""
