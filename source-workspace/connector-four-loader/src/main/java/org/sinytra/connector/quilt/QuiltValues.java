package org.sinytra.connector.quilt;

import net.fabricmc.loader.api.metadata.CustomValue;
import org.quiltmc.loader.api.LoaderValue;

import java.util.*;

/** Immutable native metadata view; locations identify preserved JSON paths, not invented line numbers. */
public final class QuiltValues {
    private QuiltValues() {}

    public static LoaderValue from(CustomValue value, String location) {
        return switch (value.getType()) {
            case OBJECT -> {
                Map<String, LoaderValue> fields = new LinkedHashMap<>();
                for (var e : value.getAsObject()) fields.put(e.getKey(), from(e.getValue(), location + "." + e.getKey()));
                yield new ObjectValue(fields, location);
            }
            case ARRAY -> {
                List<LoaderValue> values = new ArrayList<>();
                for (CustomValue item : value.getAsArray()) values.add(from(item, location + "[" + values.size() + "]"));
                yield new ArrayValue(values, location);
            }
            case STRING -> new Scalar(LoaderValue.LType.STRING, value.getAsString(), location);
            case NUMBER -> new Scalar(LoaderValue.LType.NUMBER, value.getAsNumber(), location);
            case BOOLEAN -> new Scalar(LoaderValue.LType.BOOLEAN, value.getAsBoolean(), location);
            case NULL -> new Scalar(LoaderValue.LType.NULL, null, location);
        };
    }

    private interface ValueDefaults extends LoaderValue {
        default ClassCastException wrong(LType expected) { return new ClassCastException(location() + ": expected " + expected + ", found " + type()); }
        default LObject asObject() { throw wrong(LType.OBJECT); }
        default LArray asArray() { throw wrong(LType.ARRAY); }
        default String asString() { throw wrong(LType.STRING); }
        default Number asNumber() { throw wrong(LType.NUMBER); }
        default boolean asBoolean() { throw wrong(LType.BOOLEAN); }
    }

    private record Scalar(LoaderValue.LType type, Object data, String location) implements ValueDefaults {
        public String asString() { if (type != LType.STRING) throw wrong(LType.STRING); return (String) data; }
        public Number asNumber() { if (type != LType.NUMBER) throw wrong(LType.NUMBER); return (Number) data; }
        public boolean asBoolean() { if (type != LType.BOOLEAN) throw wrong(LType.BOOLEAN); return (Boolean) data; }
        @Override public boolean equals(Object o) {
            if (!(o instanceof LoaderValue v) || v.type() != type) return false;
            return switch(type) {
                case STRING -> data.equals(v.asString());
                case NUMBER -> data.equals(v.asNumber());
                case BOOLEAN -> data.equals(v.asBoolean());
                case NULL -> true;
                default -> false;
            };
        }
        @Override public int hashCode() { return Objects.hash(type, data); }
    }

    private static final class ObjectValue extends AbstractMap<String, LoaderValue> implements LoaderValue.LObject, ValueDefaults {
        private final Map<String, LoaderValue> fields;
        private final String location;
        ObjectValue(Map<String, LoaderValue> fields, String location) { this.fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields)); this.location = location; }
        public LType type() { return LType.OBJECT; }
        public String location() { return location; }
        public LObject asObject() { return this; }
        public Set<Entry<String, LoaderValue>> entrySet() { return fields.entrySet(); }
        public LoaderValue get(Object key) { return fields.get(key); }
    }

    private static final class ArrayValue extends AbstractList<LoaderValue> implements LoaderValue.LArray, ValueDefaults {
        private final List<LoaderValue> values;
        private final String location;
        ArrayValue(List<LoaderValue> values, String location) { this.values = List.copyOf(values); this.location = location; }
        public LType type() { return LType.ARRAY; }
        public String location() { return location; }
        public LArray asArray() { return this; }
        public LoaderValue get(int i) { return values.get(i); }
        public int size() { return values.size(); }
    }
}
