#!/usr/bin/env python3
import json,pathlib
from run_unified import parse
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parents[1]
probe='f420e2021563d25931f1783f5a5744943dfbafc7557ae5c52ff2090331066b04'
native=parse((ROOT/'four-loader/quilt-native-control/logs/native-create-3.log').read_bytes(),'create',probe)
old=parse((HERE/'logs/unified-create-1.log').read_bytes(),'create',probe)
assert native['entrypoint_order_valid']
assert not old['entrypoint_order_valid']
assert native['class_defined_count']==old['class_defined_count']==1
assert all(v==1 for v in old['stage_counts'].values())
print('PASS: exact unchanged probe genuine-native order accepted; prior Unified order rejected despite all eight counts once')
