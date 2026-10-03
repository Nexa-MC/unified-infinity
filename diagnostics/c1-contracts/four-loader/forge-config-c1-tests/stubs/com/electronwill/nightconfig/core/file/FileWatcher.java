package com.electronwill.nightconfig.core.file;
/** Test seam: records actual owner registrations; explicit callback firing, no OS timing. */
public final class FileWatcher {
 private static final FileWatcher INSTANCE=new FileWatcher(); private final java.util.Map<java.nio.file.Path,Runnable> callbacks=new java.util.concurrent.ConcurrentHashMap<>();
 public static FileWatcher defaultInstance(){return INSTANCE;}
 public void addWatch(java.nio.file.Path path,Runnable callback){if(callbacks.putIfAbsent(path,callback)!=null)throw new AssertionError("duplicate watch "+path);}
 public void removeWatch(java.nio.file.Path path){callbacks.remove(path);}
 public void fire(java.nio.file.Path path){java.util.Objects.requireNonNull(callbacks.get(path),"No owner callback: "+path).run();}
 public int count(){return callbacks.size();}
}
