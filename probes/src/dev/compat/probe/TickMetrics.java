package dev.compat.probe;
import java.util.Arrays;
public final class TickMetrics {
 private static final long[] SAMPLES=new long[200];
 private static int seen;
 private TickMetrics() {}
 public static void record(long nanos) {
  int index=seen++-100;
  if(index>=0 && index<SAMPLES.length)SAMPLES[index]=nanos;
  if(index==SAMPLES.length-1) {
   long[] sorted=SAMPLES.clone(); Arrays.sort(sorted);
   System.out.println("COMPAT_TICK_SAMPLE_OK count=200 warmup=100 p50_ns="+sorted[99]+" p95_ns="+sorted[189]+" p99_ns="+sorted[197]+" max_ns="+sorted[199]+" scope=idle_server_no_players");
  }
 }
}
