#!/usr/bin/env python3
"""Summarize selected JFR events; weighted allocation samples are not exact allocation."""
import collections,json,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parent.parent
name=sys.argv[1];jfr=root/'logs'/f'{name}.jfr'
raw=subprocess.check_output([str(root/'.toolchains/jdk-21.0.12.1+1/bin/jfr'),'print','--json','--stack-depth','0','--events','jdk.GCHeapSummary,jdk.ObjectAllocationSample,jdk.ThreadStart',str(jfr)])
events=json.loads(raw)['recording']['events'];heap=[];allocation=collections.Counter();threads=[]
for e in events:
 v=e['values']
 if e['type']=='jdk.GCHeapSummary':heap.append(v['heapUsed'])
 elif e['type']=='jdk.ObjectAllocationSample':allocation[v['objectClass']['name']]+=v['weight']
 elif e['type']=='jdk.ThreadStart':threads.append(v['thread']['javaName'])
result={'profile':name,'gc_heap_summary_count':len(heap),'max_heap_used_at_gc_sample_bytes':max(heap,default=None),'weighted_allocation_sample_bytes':sum(allocation.values()),'largest_weighted_allocation_classes':allocation.most_common(15),'thread_start_event_count':len(threads),'transform_thread_names':[n for n in threads if 'pool-' in n or 'infinity' in n],'limits':['GC samples are not continuous heap highwater','Allocation sample weights are estimates, not exact allocated byte counts','Thread starts differ from simultaneously live thread count','Recording overhead applies to all compared profiles']}
(root/'logs'/f'{name}-jfr-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
